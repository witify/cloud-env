#!/usr/bin/env bash
# SessionStart hook of the cloud VM, on a new session and on a resume. A snapshot keeps files,
# not processes, so this starts the services, then brings the code in line with the checkout.
# Its stdout reaches the agent as session context.

[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0

source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib.sh"
if [ -z "$ROOT_DIR" ]; then
    echo "WARNING: this branch has no $PROJECT_FILE, so the project was not installed in this VM: no database, no site, no workers. The guard is on. Report this before you rely on the stack."
    exit 0
fi

cd "$ROOT_DIR" || exit 0

started=$(date +%s)

if [ ! -f "$STATE_DIR/setup-finished-at" ]; then
    echo "WARNING: the setup script did not finish in this VM, so tools may be missing. Read $LOG_DIR/. Fix or report this before you rely on the stack."
fi

problems=""
start_mysql || problems="$problems mysql"
start_redis || problems="$problems redis"
start_web || problems="$problems web"
start_mailpit

sync_output="$("$CLOUD_DIR/bin/cloud-sync" --no-restart 2>&1)"
start_workers
for worker in $(workers_not_up); do
    problems="$problems $worker"
done

site_status="$(curl -s -o /dev/null -m 20 -w '%{http_code}' "$SITE_URL$SITE_CHECK_PATH")"
[ "$site_status" = "200" ] || problems="$problems site(http-$site_status)"

failed_steps="$(awk '$2 != 0 {print $1}' "$STATE_DIR/steps" 2>/dev/null | tr '\n' ' ')"

sed \
    -e "s#__ROOT_DIR__#$ROOT_DIR#g" \
    -e "s#__SITE_URL__#$SITE_URL#g" \
    -e "s#__PHP_VERSION__#$PHP_VERSION#g" \
    -e "s#__MYSQL_VERSION__#$MYSQL_VERSION#g" \
    -e "s#__APP_DATABASE__#$APP_DATABASE#g" \
    -e "s#__TEST_DATABASE__#$TEST_DATABASE#g" \
    "$CLOUD_DIR/session-context.md"

echo
echo "## This project"
if [ -n "$SITE_LOGIN_EMAIL" ]; then
    echo "- Sign in as \`$SITE_LOGIN_EMAIL\` / \`$SITE_LOGIN_PASSWORD\`. The landing path is \`$SITE_LANDING_PATH\`."
fi
project_context

echo
echo "## State of this VM"
echo "- Started in $(($(date +%s) - started)) s. Snapshot made at $(cat "$STATE_DIR/setup-finished-at" 2>/dev/null || echo unknown)."
echo "- Checkout: $(git rev-parse --short HEAD) on $(git branch --show-current 2>/dev/null | grep . || echo 'detached HEAD')."
[ -n "$sync_output" ] && echo "- Sync: $sync_output"
[ -n "$problems" ] && echo "- PROBLEM, not up:$problems. Logs in $LOG_DIR/."
[ -n "$failed_steps" ] && echo "- PROBLEM, setup steps that failed: $failed_steps. Logs in $LOG_DIR/."
[ -z "$problems$failed_steps" ] && echo "- All services answer."

exit 0
