#!/usr/bin/env bash
# Optional. The VM detects a Witify Laravel project by itself: see the README. Copy this file to
# .claude/cloud.sh only for notes to the agent, or for a value that detection gets wrong.
# It runs as root at every session start: review a change here like a CI change.
# Never put a secret here. The file is read by a VM where an agent reads untrusted text.
# Use plain assignments, not `declare`: this file is sourced inside a function.
# A version, a database name, packages, `project_env` and `install_*` take effect only in a new
# snapshot: change the number in the environment's setup script.

# A value that detection gets wrong. Any value or function in defaults.sh can go here.
# MYSQL_VERSION="8.4"

project_context() {
    cat <<'EOF'
- To let a person try a branch on a Mac: <how to do it>.
- Does not work in this VM: <integrations with no keys, screens with no data>.
EOF
}
