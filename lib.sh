#!/usr/bin/env bash
# Shared by setup.sh, session-start.sh and the commands in bin/. All of them run from /opt/cloud-env.
#
# The project's values come from .claude/cloud.sh in its repository. A copy stays in the state
# folder: a session can check out a branch that does not have the file yet, and the services must
# still start. Each script refreshes the copy from the checkout when the checkout has the file.

CLOUD_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
STATE_DIR="/var/lib/cloud-env"
LOG_DIR="/var/log/cloud-env"
PROJECT_FILE=".claude/cloud.sh"
INSTALLED_PROJECT_FILE="$STATE_DIR/project.sh"
ROOT_DIR_FILE="$STATE_DIR/root-dir"

mkdir -p "$STATE_DIR" "$LOG_DIR"

export COMPOSER_ALLOW_SUPERUSER=1
export COMPOSER_NO_INTERACTION=1
export DEBIAN_FRONTEND=noninteractive

# A cloud session has one repository, under /home/user.
find_root_dir() {
    local candidate

    if [ -s "$ROOT_DIR_FILE" ]; then
        cat "$ROOT_DIR_FILE"
        return 0
    fi

    for candidate in /home/user/*/"$PROJECT_FILE"; do
        if [ -f "$candidate" ]; then
            dirname "$(dirname "$candidate")"
            return 0
        fi
    done

    return 1
}

ROOT_DIR="$(find_root_dir)"

# shellcheck source=defaults.sh
source "$CLOUD_DIR/defaults.sh"

if [ -n "$ROOT_DIR" ] && [ -f "$ROOT_DIR/$PROJECT_FILE" ]; then
    cp "$ROOT_DIR/$PROJECT_FILE" "$INSTALLED_PROJECT_FILE"
fi

if [ -f "$INSTALLED_PROJECT_FILE" ]; then
    # shellcheck disable=SC1090
    source "$INSTALLED_PROJECT_FILE"
fi

log() {
    printf '[%s] %s\n' "$(date -u +%H:%M:%S)" "$*"
}

# Runs a step, keeps its output in a log and records the elapsed seconds, so a
# failed or slow step can be read after the setup script is over.
step() {
    local name="$1" started status elapsed
    shift

    started=$(date +%s)
    log "start $name"

    "$@" >"$LOG_DIR/$name.log" 2>&1
    status=$?

    elapsed=$(($(date +%s) - started))
    printf '%s %s %ss\n' "$name" "$status" "$elapsed" >>"$STATE_DIR/steps"
    log "end $name status=$status ${elapsed}s"

    return "$status"
}

mysql_answers() {
    mysqladmin -uroot -h127.0.0.1 --connect-timeout=1 ping >/dev/null 2>&1
}

# MySQL's own package has a systemd unit and no init script, and the VM has no systemd.
start_mysql_server() {
    if [ -x /etc/init.d/mysql ]; then
        service mysql start >/dev/null 2>&1
        return
    fi

    mkdir -p /var/run/mysqld
    chown mysql:mysql /var/run/mysqld
    [ -d /var/lib/mysql/mysql ] || mysqld --initialize-insecure --user=mysql >>"$LOG_DIR/mysqld.log" 2>&1
    setsid nohup mysqld --user=mysql >>"$LOG_DIR/mysqld.log" 2>&1 </dev/null &
}

# Over the socket, mysqladmin waits for the server to be gone. Over TCP it does not.
stop_mysql_server() {
    mysqladmin -uroot shutdown 2>/dev/null || service mysql stop >/dev/null 2>&1
    return 0
}

start_mysql() {
    mysql_answers && return 0

    # A paused VM can leave a stale lock behind.
    rm -f /var/run/mysqld/mysqld.sock.lock
    start_mysql_server

    local attempt
    for attempt in $(seq 1 60); do
        mysql_answers && return 0
        sleep 0.5
    done

    return 1
}

redis_answers() {
    [ "$(timeout 2 redis-cli ping 2>/dev/null)" = "PONG" ]
}

start_redis() {
    redis_answers && return 0
    service redis-server start >/dev/null 2>&1

    local attempt
    for attempt in $(seq 1 20); do
        redis_answers && return 0
        sleep 0.25
    done

    return 1
}

# php-fpm runs as root: the agent and the site write the same storage/ files, and the VM is single-use.
start_web() {
    mkdir -p /run/php
    pgrep -x "php-fpm$PHP_VERSION" >/dev/null || "php-fpm$PHP_VERSION" --allow-to-run-as-root --daemonize
    pgrep -x nginx >/dev/null || nginx
}

start_mailpit() {
    command -v mailpit >/dev/null || return 0
    pgrep -x mailpit >/dev/null && return 0
    setsid nohup mailpit --smtp 127.0.0.1:1025 --listen 127.0.0.1:8025 >"$LOG_DIR/mailpit.log" 2>&1 </dev/null &
}

start_workers() {
    local name command

    while IFS='|' read -r name command _; do
        pgrep -f "$command" >/dev/null && continue
        # The redirect is on the whole subshell: anything left holding the caller's stdout makes
        # `cloud-sync | tail` wait for as long as the worker lives.
        (
            cd "$ROOT_DIR" || exit
            exec setsid nohup $command
        ) >"$LOG_DIR/$name.log" 2>&1 </dev/null &
    done < <(background_workers)
}

# Long-lived workers keep the old code in memory.
restart_workers() {
    local name command attempt

    while IFS='|' read -r name command _; do
        pkill -f "$command" >/dev/null 2>&1
        for attempt in $(seq 1 20); do
            pgrep -f "$command" >/dev/null || break
            sleep 0.5
        done
        pkill -9 -f "$command" >/dev/null 2>&1
    done < <(background_workers)

    start_workers
}

# Prints the name of each worker that is not up. A worker that dies at boot tells nobody, and one
# still booting refuses connections, so a caller waits here before it goes on.
workers_not_up() {
    local workers name command port attempt

    workers="$(background_workers)"
    [ -n "$workers" ] || return 0

    # A new process does not show its command yet, and a boot that fails needs time to fail.
    sleep 2

    while IFS='|' read -r name command port; do
        for attempt in $(seq 1 40); do
            pgrep -f "$command" >/dev/null || break
            if [ -z "$port" ] || (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
                continue 2
            fi
            sleep 0.25
        done
        echo "$name"
    done <<<"$workers"
}

# Hash of what decides whether a dependency install or a build must run again.
fingerprint() {
    (cd "$ROOT_DIR" && cat "$@" 2>/dev/null | sha256sum | cut -d' ' -f1)
}

frontend_fingerprint() {
    (
        cd "$ROOT_DIR" || exit
        local paths=(resources modules custom lang vite.config.ts tailwind.config.js tsconfig.json package-lock.json)
        local files=('*.vue' '*.ts' '*.js' '*.css' '*.scss' '*.json' '*.svg' '*.blade.php')
        {
            git ls-files -s -- "${files[@]}" | grep -E " 0\s+(resources|modules|custom|lang|vite\.config|tailwind\.config|tsconfig|package-lock)"
            git diff HEAD -- "${paths[@]}"
            git ls-files --others --exclude-standard -z -- "${paths[@]}" | xargs -0 -r sha256sum
        } 2>/dev/null | sha256sum | cut -d' ' -f1
    )
}

migrations_fingerprint() {
    (
        cd "$ROOT_DIR" || exit
        {
            git ls-files -s -- database/migrations database/schema 'modules/*/migrations/*' 'modules/*/Database/migrations/*'
            git ls-files --others --exclude-standard -- database/migrations 'modules/*/migrations/*' 'modules/*/Database/migrations/*'
        } 2>/dev/null | sha256sum | cut -d' ' -f1
    )
}

state_changed() {
    [ "$(cat "$STATE_DIR/$1" 2>/dev/null)" != "$2" ]
}

remember_state() {
    printf '%s' "$2" >"$STATE_DIR/$1"
}
