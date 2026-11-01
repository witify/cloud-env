#!/usr/bin/env bash
# Provisions the cloud VM. The environment's setup script calls this once per snapshot, before
# Claude Code starts. Anthropic then keeps the disk, so later sessions start with all of this in place.
#
# It always exits 0: a non-zero exit stops every session from starting. A step that fails is
# recorded in /var/lib/cloud-env/steps and session-start.sh reports it to the agent.
# The snapshot is only kept when this finishes in about five minutes, so what can run together does.

set -uo pipefail

source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib.sh"

: >"$STATE_DIR/steps"
date -u +%FT%TZ >"$STATE_DIR/setup-started-at"

IMAGE_PHP_VERSION="8.3"
IMAGE_MYSQL_VERSION="8.0"
ONDREJ_PHP_KEY_URL="https://keyserver.ubuntu.com/pks/lookup?op=get&search=0xB8DC7E53946656EFBCE4C1DD71DAEAAB4AD4CAB6"
MYSQL_KEY_URL="https://keyserver.ubuntu.com/pks/lookup?op=get&search=0xBCA43417C3B485DD128EC6D4B7B3B788A8D3785C"

php_packages() {
    local extension

    for extension in $PHP_EXTENSIONS; do
        printf 'php%s-%s ' "$PHP_VERSION" "$extension"
    done
}

add_apt_source() {
    local name="$1" key_url="$2" source="$3"

    curl -fsSL "$key_url" | gpg --dearmor --yes -o "/usr/share/keyrings/$name.gpg" || return 1
    echo "deb [signed-by=/usr/share/keyrings/$name.gpg] $source" >"/etc/apt/sources.list.d/$name.list"
}

add_version_sources() {
    if [ "$PHP_VERSION" != "$IMAGE_PHP_VERSION" ]; then
        add_apt_source ondrej-php "$ONDREJ_PHP_KEY_URL" "https://ppa.launchpadcontent.net/ondrej/php/ubuntu noble main" || return 1
    fi
    if [ "$MYSQL_VERSION" != "$IMAGE_MYSQL_VERSION" ]; then
        add_apt_source mysql "$MYSQL_KEY_URL" "http://repo.mysql.com/apt/ubuntu noble mysql-$MYSQL_VERSION-lts" || return 1
    fi
}

mysql_packages() {
    if [ "$MYSQL_VERSION" = "$IMAGE_MYSQL_VERSION" ]; then
        echo "mysql-server-$MYSQL_VERSION"
    else
        echo "mysql-community-server"
    fi
}

install_system_packages() {
    # dpkg fsyncs every file by default. The VM has nothing to protect at this point.
    echo force-unsafe-io >/etc/dpkg/dpkg.cfg.d/unsafe-io
    printf 'path-exclude=/usr/share/doc/*\npath-exclude=/usr/share/man/*\n' >/etc/dpkg/dpkg.cfg.d/no-docs

    add_version_sources || return 1
    apt-get update -qq || return 1
    # shellcheck disable=SC2046,SC2086
    apt-get install -y -qq --no-install-recommends $(php_packages) $(mysql_packages) $SYSTEM_PACKAGES $EXTRA_SYSTEM_PACKAGES || return 1
    # An image can hold another PHP, and the project's version must answer to `php`.
    update-alternatives --set php "/usr/bin/php$PHP_VERSION" || return 1

    # Debian blocks PDF reads by default; spatie/pdf-to-image needs them.
    sed -i 's/rights="none" pattern="PDF"/rights="read|write" pattern="PDF"/' /etc/ImageMagick-*/policy.xml 2>/dev/null || true
}

configure_php() {
    local directory

    for directory in "/etc/php/$PHP_VERSION/cli/conf.d" "/etc/php/$PHP_VERSION/fpm/conf.d"; do
        cp "$CLOUD_DIR/config/php.ini" "$directory/99-cloud.ini"
    done

    sed -i -E \
        -e 's/^user = .*/user = root/' \
        -e 's/^group = .*/group = root/' \
        -e 's/^listen\.owner = .*/listen.owner = root/' \
        -e 's/^listen\.group = .*/listen.group = root/' \
        -e 's/^pm\.max_children = .*/pm.max_children = 16/' \
        "/etc/php/$PHP_VERSION/fpm/pool.d/www.conf"
    mkdir -p /run/php
}

configure_nginx() {
    sed -e "s#__ROOT_DIR__#$ROOT_DIR#" -e "s#__PHP_VERSION__#$PHP_VERSION#" "$CLOUD_DIR/config/nginx-site.conf" >/etc/nginx/sites-available/cloud
    rm -f /etc/nginx/sites-enabled/default
    ln -sf /etc/nginx/sites-available/cloud /etc/nginx/sites-enabled/cloud
    sed -i 's/^user www-data;/user root;/' /etc/nginx/nginx.conf
    nginx -t
}

configure_mysql() {
    cp "$CLOUD_DIR/config/mysql.cnf" /etc/mysql/mysql.conf.d/zz-cloud.cnf
    service mysql restart || { rm -f /etc/mysql/mysql.conf.d/zz-cloud.cnf; service mysql start; } || return 1

    # The site and the tests connect as root with no password over TCP.
    mysql -uroot <<SQL
ALTER USER 'root'@'localhost' IDENTIFIED WITH caching_sha2_password BY '';
CREATE USER IF NOT EXISTS 'root'@'127.0.0.1' IDENTIFIED WITH caching_sha2_password BY '';
GRANT ALL PRIVILEGES ON *.* TO 'root'@'127.0.0.1' WITH GRANT OPTION;
CREATE DATABASE IF NOT EXISTS \`$APP_DATABASE\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS \`$TEST_DATABASE\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
FLUSH PRIVILEGES;
SQL
}

install_mailpit() {
    local version archive

    version="$(curl -fsSL -o /dev/null -w '%{url_effective}' https://github.com/axllent/mailpit/releases/latest | sed 's#.*/##')"
    archive="$(mktemp)"
    curl -fsSL -o "$archive" "https://github.com/axllent/mailpit/releases/download/$version/mailpit-linux-amd64.tar.gz" || return 1
    tar -xzf "$archive" -C /usr/local/bin mailpit
    rm -f "$archive"
}

install_browser_tools() {
    local failed=0

    npm install -g --no-audit --no-fund @playwright/mcp@0.0.84 || failed=1
    pip install --quiet --break-system-packages yt-dlp pyyaml || failed=1

    return "$failed"
}

link_commands() {
    local name

    for name in herd cloud-sync composer-install demo-video; do
        chmod +x "$CLOUD_DIR/bin/$name"
        ln -sf "$CLOUD_DIR/bin/$name" "/usr/local/bin/$name"
    done
    ln -sf /usr/bin/php "/usr/local/bin/php${PHP_VERSION//./}"
    chmod +x "$CLOUD_DIR"/git-hooks/*
    git config --system core.hooksPath "$CLOUD_DIR/git-hooks"
}

link_skill() {
    local directory="$1" name

    name="$(basename "$directory")"
    # The repository's own skills load anyway and win on a name collision.
    [ -e "$ROOT_DIR/.claude/skills/$name" ] && return 0
    [ -e "/root/.claude/skills/$name" ] && return 0
    ln -s "$directory" "/root/.claude/skills/$name"
}

install_skills() {
    local entry repository folders folder directory target failed=0

    mkdir -p /root/.claude/skills

    for directory in "$CLOUD_DIR"/skills/*/; do
        link_skill "${directory%/}"
    done

    for entry in $SKILL_REPOSITORIES; do
        repository="${entry%%|*}"
        folders="${entry##*|}"
        target="/opt/skills/$repository"

        rm -rf "$target"
        git clone --quiet --depth 1 "https://github.com/$repository" "$target" || { failed=1; continue; }

        for folder in ${folders//,/ }; do
            while IFS= read -r directory; do
                link_skill "$directory"
            done < <(find "$target/$folder" -mindepth 2 -maxdepth 4 -name SKILL.md -not -path '*/node_modules/*' -not -path '*/deprecated/*' -not -path '*/in-progress/*' -printf '%h\n')
        done
    done

    return "$failed"
}

# ~/.claude holds what only the VM needs, so the repository's settings stay the same on a Mac.
configure_claude() {
    python3 -I - "$CLOUD_DIR" <<'PYTHON'
import json, os, sys

cloud_dir = sys.argv[1]
settings_path = '/root/.claude/settings.json'
existing = json.load(open(settings_path)) if os.path.exists(settings_path) else {}
wanted = json.load(open(f'{cloud_dir}/config/claude-settings.json'))

for key, value in wanted.items():
    if key == 'hooks':
        hooks = existing.setdefault('hooks', {})
        for event, entries in value.items():
            hooks.setdefault(event, []).extend(entries)
    elif key == 'permissions':
        existing.setdefault('permissions', {}).setdefault('allow', []).extend(value.get('allow', []))
    elif key == 'env':
        existing.setdefault('env', {}).update(value)
    else:
        existing[key] = value

text = json.dumps(existing, indent=2).replace('__CLOUD_DIR__', cloud_dir)
open(settings_path, 'w').write(text)

config_path = '/root/.claude.json'
config = json.load(open(config_path)) if os.path.exists(config_path) else {}
config.setdefault('mcpServers', {})['playwright'] = json.load(open(f'{cloud_dir}/config/mcp-playwright.json'))
json.dump(config, open(config_path, 'w'), indent=2)
PYTHON
}

# Project lines come first, and only the first line of a key stays.
write_env_file() {
    {
        project_env
        sed -e "s#__SITE_URL__#$SITE_URL#" -e "s#__APP_DATABASE__#$APP_DATABASE#" "$CLOUD_DIR/env.defaults"
    } | awk -F= '/^[A-Za-z_][A-Za-z0-9_]*=/ { if (seen[$1]++) next } { print }' >"$ROOT_DIR/.env"
}

install_php_dependencies() {
    "$CLOUD_DIR/bin/composer-install" --setup
}

install_js_dependencies() {
    npm ci --no-audit --no-fund
}

prepare_application() {
    cd "$ROOT_DIR" || return 1

    command -v mailpit >/dev/null || sed -i 's/^MAIL_MAILER=.*/MAIL_MAILER=log/' .env
    php artisan key:generate --force --no-interaction

    install_application || return 1
    DB_DATABASE="$TEST_DATABASE" APP_ENV=testing php artisan migrate:fresh --force --no-interaction
}

seed_demo_data() {
    cd "$ROOT_DIR" || return 1
    install_demo_data
}

build_assets() {
    cd "$ROOT_DIR" || return 1
    rm -f public/hot
    npm run build -- --minify false
}

step_succeeded() {
    grep -q "^$1 0 " "$STATE_DIR/steps"
}

# A step that failed keeps no fingerprint, so cloud-sync repairs it. Composer is the exception:
# a repair through git takes about 13 minutes on every session start, and the agent sees the failed step.
remember_fingerprints() {
    remember_state composer "$(fingerprint composer.lock composer.json)"
    remember_state frontend "$(frontend_fingerprint)"
    step_succeeded install-js-dependencies && remember_state npm "$(fingerprint package-lock.json)"
    step_succeeded prepare-application && remember_state migrations "$(migrations_fingerprint)"
    return 0
}

# Stops cleanly so the snapshot holds a consistent data directory.
stop_services() {
    # Over the socket, mysqladmin waits for the server to be gone. Over TCP it does not.
    mysqladmin -uroot shutdown 2>/dev/null || service mysql stop
    service redis-server stop
    pkill -x nginx 2>/dev/null
    pkill -x "php-fpm$PHP_VERSION" 2>/dev/null
    return 0
}

# The guard comes first: a VM with no project file must still have it.
step link-commands link_commands
step configure-claude configure_claude

if [ -z "$ROOT_DIR" ]; then
    # Happens on a branch that does not have the file yet. The snapshot stays bare until the
    # environment's setup script changes, and session-start.sh tells the agent.
    echo "cloud-env: no repository under /home/user has $PROJECT_FILE, so the project was not installed." | tee "$LOG_DIR/no-project-file.log"
    exit 0
fi

printf '%s\n' "$ROOT_DIR" >"$ROOT_DIR_FILE"

cd "$ROOT_DIR" || exit 0

# Agents keep their scratch work here, and a project's .gitignore may not know it.
grep -qx '.scratch/' .git/info/exclude 2>/dev/null || echo '.scratch/' >>.git/info/exclude

step install-browser-tools install_browser_tools &
step install-skills install_skills &
step install-mailpit install_mailpit &
step install-system-packages install_system_packages
step configure-php configure_php
step configure-nginx configure_nginx
step configure-mysql configure_mysql
step start-redis start_redis
wait

# .env must exist before composer: its post-install script boots the framework.
[ -f .env ] || step write-env-file write_env_file
step install-php-dependencies install_php_dependencies &
step install-js-dependencies install_js_dependencies &
wait

step build-assets build_assets &
step prepare-application prepare_application && step seed-demo-data seed_demo_data
wait

step remember-fingerprints remember_fingerprints
step stop-services stop_services

date -u +%FT%TZ >"$STATE_DIR/setup-finished-at"
git -C "$ROOT_DIR" status --short >"$LOG_DIR/git-status-after-setup.log" 2>&1

exit 0
