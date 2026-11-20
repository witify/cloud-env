#!/usr/bin/env bash
# Shared by setup.sh, session-start.sh and the commands in bin/. All of them run from /opt/cloud-env.
#
# The project's values come, in this order, from defaults.sh, from what setup.sh detected once for
# this snapshot, and from the optional .claude/cloud.sh in its repository. A copy of that file stays
# in the state folder: a session can check out a branch that does not have it, and the services must
# still start. Each script refreshes the copy from the checkout when the checkout has the file.

CLOUD_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
STATE_DIR="/var/lib/cloud-env"
LOG_DIR="/var/log/cloud-env"
PROJECT_FILE=".claude/cloud.sh"
INSTALLED_PROJECT_FILE="$STATE_DIR/project.sh"
DETECTED_FILE="$STATE_DIR/detected.sh"
ROOT_DIR_FILE="$STATE_DIR/root-dir"
# The values the tools of a flow read (README, "The flow"). Its path and its keys are a contract with Navark.
VALUES_FILE="$STATE_DIR/values.sh"

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

    for candidate in /home/user/*/artisan; do
        if [ -f "$candidate" ]; then
            dirname "$candidate"
            return 0
        fi
    done

    return 1
}

ROOT_DIR="$(find_root_dir)"

load_project_values() {
    # shellcheck source=defaults.sh
    source "$CLOUD_DIR/defaults.sh"

    if [ -f "$DETECTED_FILE" ]; then
        # shellcheck disable=SC1090
        source "$DETECTED_FILE"
    fi

    if [ -n "$ROOT_DIR" ] && [ -f "$ROOT_DIR/$PROJECT_FILE" ]; then
        cp "$ROOT_DIR/$PROJECT_FILE" "$INSTALLED_PROJECT_FILE"
    fi

    if [ -f "$INSTALLED_PROJECT_FILE" ]; then
        # An unset variable in a project's file must not stop setup.sh before the guard is installed.
        local shell_flags="$-"
        set +u
        # shellcheck disable=SC1090
        source "$INSTALLED_PROJECT_FILE"
        [[ "$shell_flags" == *u* ]] && set -u
    fi

    return 0
}

load_project_values

log() {
    printf '[%s] %s\n' "$(date -u +%H:%M:%S)" "$*"
}

# Single quotes, inside which a shell interprets nothing; a single quote itself is closed, escaped, reopened.
shell_quote() {
    printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
}

# Writes the values the tools of a flow read, in place of sourcing this file: the flow comes from Navark
# (`get_flow`) and must not depend on how cloud-env is laid out. One `KEY='value'` line per key, for any
# POSIX shell to source. Rewritten at every session start, so a change in .claude/cloud.sh reaches it.
# Adding a key is compatible; renaming or removing one needs a new CLOUD_ENV_VALUES_VERSION and a flow that
# reads both.
write_flow_values() {
    local CLOUD_ENV_VALUES_VERSION=1
    # require('playwright') resolves from here, as in the agent's own environment (config/claude-settings.json).
    local NODE_PATH="${NODE_PATH:-/opt/node22/lib/node_modules}"
    local name temporary

    temporary="$(mktemp "$STATE_DIR/values.XXXXXX")" || return 1
    {
        echo "# Written by cloud-env at every session start, for the tools of the flow. Do not edit."
        for name in CLOUD_ENV_VALUES_VERSION ROOT_DIR SITE_URL SITE_LOGIN_PATH SITE_LOGIN_EMAIL SITE_LOGIN_PASSWORD SITE_LANDING_PATH NODE_PATH; do
            printf '%s=%s\n' "$name" "$(shell_quote "${!name-}")"
        done
    } >"$temporary" && chmod 600 "$temporary" && mv -f "$temporary" "$VALUES_FILE"
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
    # In a subshell, or the `wait` of setup.sh waits for the server forever.
    (setsid nohup mysqld --user=mysql >>"$LOG_DIR/mysqld.log" 2>&1 </dev/null &)
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

# The test goes through a variable: `grep -q` stops reading first, and pipefail then sees a failure.
has_worker() {
    grep -Eq "$1" <<<"$(background_workers)"
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

# Hashes the files as they are on disk, tracked or not, so a commit of code that was
# already built does not ask for a second build.
frontend_fingerprint() {
    (
        cd "$ROOT_DIR" || exit
        local paths=(resources modules custom lang vite.config.ts tailwind.config.js tsconfig.json package-lock.json)
        git ls-files -z --cached --others --exclude-standard -- "${paths[@]}" 2>/dev/null \
            | grep -zE '\.(vue|ts|js|css|scss|json|svg|blade\.php)$' \
            | sort -zu \
            | xargs -0 -r sha256sum 2>/dev/null \
            | sha256sum | cut -d' ' -f1
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

# A PWA plugin can refuse the larger files of an unminified build, and only stops the build at the end.
build_frontend() {
    npm run build -- --minify false || npm run build
}

state_changed() {
    [ "$(cat "$STATE_DIR/$1" 2>/dev/null)" != "$2" ]
}

remember_state() {
    printf '%s' "$2" >"$STATE_DIR/$1"
}
