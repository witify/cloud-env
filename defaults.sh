#!/usr/bin/env bash
# Defaults for a Witify Laravel project. The project's .claude/cloud.sh overrides what it needs:
# see templates/cloud.sh.

PROJECT_NAME="$(basename "${ROOT_DIR:-project}")"
APP_DATABASE="$PROJECT_NAME"
TEST_DATABASE="test"

SITE_URL="http://localhost"
# curl checks this page at every session start. It must answer 200 with no session.
SITE_CHECK_PATH="/login"
SITE_LOGIN_EMAIL=""
SITE_LOGIN_PASSWORD=""
SITE_LANDING_PATH="/"

# The image is Ubuntu 24.04, and its apt sources ship PHP 8.3. Another version needs its own source.
PHP_VERSION="8.3"
# Composer stops without imagick in most Witify projects.
PHP_EXTENSIONS="fpm cli mysql redis gd imagick intl bcmath zip soap mbstring xml curl sqlite3 opcache gmp"
SYSTEM_PACKAGES="mysql-server-8.0 nginx ffmpeg imagemagick jq lsof"
EXTRA_SYSTEM_PACKAGES=""

# Skills that exist only as plugins on a developer machine: cloud sessions install no plugin.
# Format: <github repo>|<comma-separated folders searched for SKILL.md>. On a name collision the first one wins.
SKILL_REPOSITORIES="witify/skills|skills/engineering,skills/productivity mattpocock/skills|skills/engineering,skills/productivity pbakaus/impeccable|."

# Fills the application database. Runs with the services up and .env in place.
install_application() {
    php artisan migrate --seed --force --no-interaction
}

# Records for screens to show. The app must be usable without them.
install_demo_data() {
    return 0
}

# Long-running workers, one per line: <name>|<command>
background_workers() {
    return 0
}

# .env lines that replace the ones in env.defaults.
project_env() {
    return 0
}

# Markdown the agent reads at every session start, after session-context.md.
project_context() {
    return 0
}
