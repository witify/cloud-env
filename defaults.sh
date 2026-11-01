#!/usr/bin/env bash
# Values for a Witify Laravel project. detect.py replaces most of them from the project's own files,
# and the optional .claude/cloud.sh of the project replaces what it needs: see templates/cloud.sh.

APP_DATABASE="app"
TEST_DATABASE="test"

SITE_URL="http://localhost"
# curl checks this page at every session start. It must answer 200 with no session.
SITE_CHECK_PATH="/login"
# Found in the database after the install: see detect_login in setup.sh.
SITE_LOGIN_EMAIL=""
SITE_LOGIN_PASSWORD=""
SITE_LANDING_PATH="/"

# The image is Ubuntu 24.04, and its apt sources ship PHP 8.3 and MySQL 8.0. Another version comes
# from its vendor's apt source, which costs about a minute more in the setup script.
PHP_VERSION="8.3"
MYSQL_VERSION="8.0"
# Composer stops without imagick in most Witify projects.
PHP_EXTENSIONS="fpm cli mysql redis gd imagick intl bcmath zip soap mbstring xml curl sqlite3 opcache gmp"
# Also PDF work, Loom frames and QR checks.
SYSTEM_PACKAGES="nginx ffmpeg imagemagick jq lsof ghostscript poppler-utils zbar-tools"
EXTRA_SYSTEM_PACKAGES=""

HAS_INSTALL_COMMAND="false"
HAS_DEMO_SEEDER="false"
USES_HORIZON="false"
USES_REVERB="false"

# Skills that exist only as plugins on a developer machine: cloud sessions install no plugin.
# Format: <github repo>|<comma-separated folders searched for SKILL.md>. On a name collision the first one wins.
SKILL_REPOSITORIES="witify/skills|skills/engineering,skills/productivity pbakaus/impeccable|."

# Videos and captions are for a French reader. The tests use their own database.
use_french_interface() {
    mysql -uroot "$APP_DATABASE" -e "UPDATE users SET locale = 'fr'" 2>/dev/null || true
}

# Fills the application database. Runs with the services up and .env in place.
install_application() {
    if [ "$HAS_INSTALL_COMMAND" = "true" ]; then
        php artisan install --seed --no-interaction || return 1
    else
        php artisan migrate --seed --force --no-interaction || return 1
    fi

    php artisan storage:link --no-interaction || true
    use_french_interface
}

# Records for screens to show. The app must be usable without them.
install_demo_data() {
    [ "$HAS_DEMO_SEEDER" = "true" ] || return 0

    timeout 180 php artisan db:seed --class=DemoSeeder --force --no-interaction || return 1
    use_french_interface
}

# Long-running workers, one per line: <name>|<command>|<port>. The command must show in `ps` as written,
# and must not be a part of another worker's command. Give the port of a worker that listens on
# 127.0.0.1: the check waits about 10 s for it. A worker with no port is checked once, 2 s after it starts.
background_workers() {
    [ "$USES_HORIZON" = "true" ] && echo "horizon|php artisan horizon"
    [ "$USES_REVERB" = "true" ] && echo "reverb|php artisan reverb:start --host=127.0.0.1 --port=8080|8080"
    return 0
}

# .env lines that replace the ones in env.reverb and env.defaults.
project_env() {
    return 0
}

# Markdown the agent reads at every session start, after session-context.md.
project_context() {
    return 0
}
