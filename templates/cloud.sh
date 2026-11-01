#!/usr/bin/env bash
# Copy this file to .claude/cloud.sh in a Witify Laravel project, and keep only what differs
# from defaults.sh. It runs as root at every session start: review a change here like a CI change.
# Never put a secret here. The file is read by a VM where an agent reads untrusted text.

APP_DATABASE="my_project"
SITE_LOGIN_EMAIL="demo@example.test"
SITE_LOGIN_PASSWORD="demo-password-from-the-seeder"
SITE_LANDING_PATH="/admin"
EXTRA_SYSTEM_PACKAGES=""

install_application() {
    php artisan migrate --seed --force --no-interaction
}

install_demo_data() {
    php artisan db:seed --class=DemoSeeder --force --no-interaction
}

# <name>|<command>|<port>. Leave the port out for a worker that does not listen on one.
background_workers() {
    cat <<'EOF'
horizon|php artisan horizon
EOF
}

project_env() {
    cat <<'EOF'
APP_NAME="My project (cloud)"
EOF
}

project_context() {
    cat <<'EOF'
- The admin lives under `/admin`.
- To let a person try a branch on a Mac: <how to do it>.
- Does not work in this VM: <integrations with no keys, screens with no data>.
EOF
}
