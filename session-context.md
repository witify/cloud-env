# This session runs in a Witify cloud VM

Where this differs from `CLAUDE.md`, this text is right: `CLAUDE.md` describes a Mac with Herd.

## Stack
- Repository: `__ROOT_DIR__`. Plain `php`, `composer` and `npm` work; `herd php` and `herd composer` also work through a shim.
- Site: `__SITE_URL__` (nginx, php-fpm, PHP __PHP_VERSION__).
- Also running: MySQL 8.0 (`root`, no password, databases `__APP_DATABASE__` and `__TEST_DATABASE__`), Redis, Mailpit (`http://localhost:8025`) and the workers of this project.
- After any `git checkout`, `pull` or `rebase`: run `cloud-sync`. It installs dependencies, migrates both databases and rebuilds assets, only for what changed, and restarts the workers.
- Assets are built, no Vite server runs. After a Vue change, `cloud-sync` or `npm run build -- --minify false`.

## Checks
- The checks in `CLAUDE.md` apply: `php artisan test --compact --filter=...`, `herd composer larastan`, `vendor/bin/pint --dirty`, `npm run test`, `npm run lint`, `npm run build`.
- Run the relevant tests by default. Run the full suite only when a person or a skill you follow, such as `/ship`, asks for it, and in the background: `php artisan test --parallel --recreate-databases --compact`.

## Browser and video
- Tools `mcp__playwright__*` drive a headless Chromium. Use them to explore and to check a screen.
- To send a person a video of what changed: write a scenario, then run `demo-video <scenario.cjs>`. Read `/opt/cloud-env/demo/README.md`. Outputs go in `.scratch/demo/`, which git ignores.

## GitHub
- `gh pr`, `gh issue` and `gh api graphql` fail here: the proxy blocks GraphQL. Use the `mcp__github__*` tools, including `resolve_review_thread`, or `gh api repos/<owner>/<repo>/...` for REST.
- A push to `dev`, `main` or a `deploy` branch, a merge, a branch deletion, a direct file write through the GitHub API and a change in `.github/workflows` are refused by hooks. Those stay with a person. Do not look for a way around the hooks.
- Files you leave untracked make the session's stop hook ask you to commit them. Put scratch work in `.scratch/`.

## Tickets
- A ClickUp ticket to do from A to Z: follow the `cloud-ticket` skill, in `/opt/cloud-env/skills/cloud-ticket/SKILL.md`.
- Skills that are plugins on the Mac are linked in `~/.claude/skills` under their short name: `ship`, not `witify-skills:ship`. If a skill cannot be invoked because it has `disable-model-invocation`, read its `SKILL.md` and follow it.
