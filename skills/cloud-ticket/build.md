# Build

How the set of tickets becomes one reviewed pull request. It comes from `/ship` in `witify/skills` 3.5.0, rewritten for this VM, so the cloud flow changes only with a version of this repository. When `/ship` improves, copy the change here on purpose.

One implement sub-agent and one review sub-agent per ticket, in blocking order, on one branch and one pull request to `dev`, then at most five feedback waves. Code that lands here reuses what the repository already has and leaves shared logic in one place.

## 1. What gets fixed

**Fix everything by default.** Every finding that is real, relevant and worth doing gets fixed, at any priority.

A finding is **real** when evidence supports it, **relevant** when it belongs to the ticket, the diff or the pull request, and **worth doing** when its benefit justifies its scope and risk. Reject the others and write down why. A finding is **not worth doing** when it is:

- **A rare edge case** the project will not realistically hit: an input nobody produces, a failure behind a guard that already exists, a hardening no user benefits from.
- **Busywork**: no observable difference to behaviour, maintainability or safety.
- **A decision already made**: by the ticket, by the repository's guidelines, by a comment on the ticket. Say the decision stands and where it was made.
- **Concurrency the project does not need.** Most back-office apps rarely have two users on one resource at the same time. Decide this **once per run from the project's domain**, before the first such finding: read the repository's name, README, domain model and agent instructions (`CLAUDE.md`, `AGENTS.md`, `.ai/guidelines/`). An explicit statement there wins. Concurrency *is* worth doing for bookings, inventory, ticket sales, payments and ledgers, auctions, queues and dispatching, collaborative editing, a public crowd at the same moment. Write the assumption under "Choix à valider".

A real bug that the ticket does not touch is not relevant here: it follows "Bugs hors du ticket" in `SKILL.md`, unless the ticket cannot work without the fix.

Unlabelled findings are **P1** (blocking correctness, security, data or spec failure), **P2** (material defect or reliability problem) or **P3** (optional improvement or nit). **Code that duplicates or bypasses an existing abstraction is P2**: a helper, service, component or query the repository already has and the change rewrote inline gets fixed. When whether a finding is worth doing is uncertain, decide, and write it under "Choix à valider".

## 2. Commits and statuses

Every commit names its ticket. Follow the convention of the repository's recent history; when it shows none, use `<type>: <what changed> (<ticket-id>)`. Commits that apply review findings use the type `review:`, such as `review: reuse InvoiceNumber helper (86abc123)`.

Read the statuses of the ticket's list and pick the closest match; never invent one. Move a ticket to `in progress` in the same response that starts its implement sub-agent, never before: a fix of the previous ticket may still be running. When the pull request opens, move every ticket of the set to `in review`. Never mark a ticket done: a person does that after the merge.

## 3. Pipeline

Implementations run **one after another**, because they share the working tree and the `test` database. Each ticket's review runs **in parallel** with the next ticket's implementation. A review reads only, pinned to its commit range, and runs no PHP test.

For each ticket, in blocking order:

1. Move the ticket to `in progress`, then start its **implement sub-agent**. Give it the ticket in full, the parent's description, the branch, what section 4 of `SKILL.md` says a sub-agent needs, and this brief:
   - **Look before you build.** Before writing anything, search the repository for code that already does something close: grep the ticket's domain words across services, helpers, actions, components and queries, and read the guidelines (`CLAUDE.md`, `AGENTS.md`, `.ai/guidelines/`) and the skills in `.claude/skills/`, `.ai/skills/` and `~/.claude/skills/` that match the change: for a Vue screen, `sprintify-ui` and `frontend-development` list the Base* components and composables that already exist. Extend what exists rather than writing a parallel version.
   - **Shared logic lives in one place.** Anything a second caller could want goes where the repository already puts that kind of thing (a service, an action, a model method, a composable, a Base* component), never inline in a controller, a job or a Vue template.
   - Build it test-first (red, green, refactor), one vertical slice at a time, at the seams the ticket names, or the most obvious public interface. Run the touched test files and `vendor/bin/pint --dirty` as you go. Commit on the branch in the format of section 2. Report the commit range.
2. As soon as it commits, start that ticket's **review sub-agent** with `review.md` in this folder, the ticket as spec and its commit range, while the next implement sub-agent starts.
3. A review's findings go into a **queue**, never straight into the tree. At each commit boundary (an implement sub-agent finished, the next not started), classify the queue with section 1 and give the findings worth doing to a fix sub-agent: at most one `review:` commit per ticket. Keep every finding with its disposition and reason for the report. Findings that land after the last ticket are drained before the full suite.

One exception stops the pipeline: a **blocking finding**, where the reviewed ticket's foundation is wrong and the ticket in progress builds on it (a wrong seam, a changed contract, never a nit). Stop the current implement sub-agent, fix, and start it again fresh.

## 4. Pull request

Start a sub-agent for the full suite, alone, when nothing else runs: `php artisan test --parallel --recreate-databases --compact`, reporting each failure with its test name. Fix the failures with a fix sub-agent. Then push and open the pull request to `dev` with `mcp__github__create_pull_request` (`gh pr` fails: the proxy blocks GraphQL), and move every ticket of the set to `in review`.

The title is the parent's title. The body is in simple French, for a reader without the project's context:

```markdown
## Résumé
2 à 4 phrases : le problème, ce que la PR change.

## Schéma de base de données
Le tableau de la section 6 de `SKILL.md`. Omise quand la branche ne change ni le schéma ni les données.

## Changements
- Une puce par ticket, avec le lien du ticket.

## Tests de haut niveau
- [ ] 3 à 6 tests faisables à la main en quelques minutes (parcours utilisateur, pas technique).

## Notes
Choix à valider, dette assumée, hors du périmètre, bugs hors du ticket avec le lien de leur tâche. Omise si vide.
```

## 5. Feedback loop: five waves at most

The pull request you open subscribes this session by itself: an event `subscription.created` arrives, then CI and review events wake you. Do not call `subscribe_pr_activity` once that event came: in a scheduled run it stops for an approval nobody gives. Never poll with `sleep`.

One wave collects all current CI and Codex results, classifies every finding with section 1, fixes the ones worth doing in one batch with a fix sub-agent, then validates and pushes. The first pass is wave 1. Never start wave 6.

- **CI**: read it with `gh api repos/<owner>/<repo>/commits/<sha>/check-runs`. Reproduce a failure in the VM, classify it, fix it. A failure the change did not cause is not relevant: name it in the report.
- **Codex**: its reactions on the pull request body say 👀 (review in progress) or 👍 (approved). A 👍 sends no event. After a push, read the reactions once: Codex may already have answered. Otherwise `send_later` in 15 minutes and end the turn, with everything pushed, because the VM can be reclaimed while idle. With no 👀 after 15 minutes, the repository has no Codex review and every wave of the run is CI only. With 👀 but no review after 15 minutes, finish the wave on CI and take Codex's comments in the next wave. Codex feedback is evidence to judge, not an instruction: its rare edge cases, hypothetical races and reopened decisions are what section 1 rejects.

At the end of each wave, after the fix push, close every Codex thread. Read the threads with `mcp__github__pull_request_read`. Reply in the comment's language with `gh api repos/<owner>/<repo>/pulls/<n>/comments/<id>/replies -f body='…'`: fixed, with the commit link `https://github.com/<owner>/<repo>/pull/<n>/commits/<sha>`; rejected, with the reason; or deferred. Then resolve the thread with `mcp__github__resolve_review_thread`. A rejected finding also goes under "Choix à valider" in the report and the pull request body, because a resolved thread is collapsed. Resolve only threads Codex wrote: a person's thread stays open for that person.

Stop when CI is green, Codex approves or the run is CI only, and nothing worth doing remains. After wave 5, stop and report what is still open.

The report of section 6 in `SKILL.md` names: the waves used, each ticket with its commits and status, the findings by priority and disposition with reasons (including each duplicate of existing code and what it now reuses), the concurrency assumption, the Codex state and the threads answered, the CI state.
