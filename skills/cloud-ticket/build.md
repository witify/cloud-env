# Build

How the set of tickets becomes one reviewed pull request. It comes from `/ship` in `witify/skills` 3.5.0, rewritten for this VM, so the cloud flow changes only with a version of this repository. When `/ship` improves, copy the change here on purpose.

One implement sub-agent and one review sub-agent per ticket, in blocking order, on one branch and one pull request to `dev`, then the autofix of the pull request until it settles. Code that lands here reuses what the repository already has and leaves shared logic in one place.

With the label `agent:ultracode` on the parent, section 3 does not apply, except its implement brief: "Ultracode" in section 4 of `SKILL.md` says what replaces it. Sections 1, 2, 4 and 5 still apply, run with workflows.

With the label `agent:adaptive` on the parent and no `agent:ultracode`, every section applies, and `adaptive.md` adds a triage before and after each implement sub-agent, more review pieces for a ticket at risk, and the `model` and the `effort` of each sub-agent.

## 1. What gets fixed

**Fix everything by default.** Every finding that is real, relevant and worth doing gets fixed, at any priority.

A finding is **real** when evidence supports it, **relevant** when it belongs to the ticket, the diff or the pull request, and **worth doing** when its benefit justifies its scope and risk. Reject the others and write down why. A finding is **not worth doing** when it is:

- **A rare edge case** the project will not realistically hit: an input nobody produces, a failure behind a guard that already exists, a hardening no user benefits from.
- **Busywork**: no observable difference to behaviour, maintainability or safety.
- **A decision already made**: by the ticket or a comment of a person on it, for what the product does and for each technical choice it states that no documented rule of the repository speaks against (an approach, a storage choice, a seam, a name); by the repository's guidelines, for how code is named, placed and written. Say the decision stands and where it was made. A name, a folder or a pattern that the ticket gives is not a decision against a documented rule of the repository (the sources of `review.md` step 3). The rule wins, also when older code next to the change breaks it, unless the ticket or a comment of a person on it says in so many words that it departs from that rule. The code follows the rule, the finding that asks for it is never rejected as a decision of the ticket, and the difference goes under "Écart avec la spec" with the sentence of the ticket and the rule quoted.
- **Concurrency the project does not need.** Most back-office apps rarely have two users on one resource at the same time. Decide this **once per run from the project's domain**, before the first such finding: read the repository's name, README, domain model and agent instructions (`CLAUDE.md`, `AGENTS.md`, `.ai/guidelines/`). An explicit statement there wins. Concurrency *is* worth doing for bookings, inventory, ticket sales, payments and ledgers, auctions, queues and dispatching, collaborative editing, a public crowd at the same moment. Write the assumption under "Choix à valider".

A real bug that the ticket does not touch is not relevant here: it follows "Bugs hors du ticket" in `SKILL.md`, unless the ticket cannot work without the fix.

Unlabelled findings are **P1** (blocking correctness, security, data or spec failure), **P2** (material defect or reliability problem) or **P3** (optional improvement or nit). **Code that duplicates or bypasses an existing abstraction is P2**: a helper, service, component or query the repository already has and the change rewrote inline gets fixed. When whether a finding is worth doing is uncertain, decide, and write it under "Choix à valider".

## 2. Commits and statuses

Every commit names its ticket. Follow the convention of the repository's recent history; when it shows none, use `<type>: <what changed> (<ticket-id>)`. Commits that apply review findings use the type `review:`, such as `review: reuse InvoiceNumber helper (WIT-52)`.

Read the statuses of the workspace (`mcp__Navark__list_issue_statuses`) and pick the closest match; never invent one. Move a ticket to `in progress`, with `assignee: null` so the assignment for review notifies the lead (section 5), in the same response that starts its implement sub-agent (in ultracode, its implement workflow), never before: a fix of the previous ticket may still be running. When the pull request opens, move every ticket of the set to `in review`. Never mark a ticket done: a person does that after the merge.

## 3. Pipeline

Implementations run **one after another**, because they share the working tree and the `test` database. Each ticket's review runs **in parallel** with the next ticket's implementation. A review reads only, pinned to its commit range, and runs no PHP test.

For each ticket, in blocking order:

1. Move the ticket to `in progress`, then start its **implement sub-agent**. Give it the ticket in full, the parent's description, the branch, what section 4 of `SKILL.md` says a sub-agent needs, and this brief:
   - **Look before you build.** Before writing anything, search the repository for code that already does something close: grep the ticket's domain words across services, helpers, actions, components and queries, and read the guidelines (`CLAUDE.md`, `AGENTS.md`, `.ai/guidelines/`) and the skills in `.claude/skills/`, `.ai/skills/` and `~/.claude/skills/` that match the change: for a Vue screen, `sprintify-ui` and `frontend-development` list the Base* components and composables that already exist. Extend what exists rather than writing a parallel version.
   - **A new screen or a layout overhaul goes through `impeccable`.** A new screen is a page that a new route or a new tab shows, or a modal or a drawer that holds a whole form or a whole view. A layout overhaul is a ticket that rearranges an existing screen: where its sections sit, its grid, its navigation, its visual hierarchy. A field, a column, a button or a label added to a screen that keeps its structure is neither. For either case, load the `impeccable` skill before the first UI edit and follow its setup, `reference/craft-floor.md` included, and look at the rendered screen before you commit. Four limits for this VM: the screen is in the Operate mode unless the ticket says otherwise; the existing app is the visual world to keep, so the work is never a redesign of its look (no new palette, font or design system, no Base* component replaced by a custom one); never run `init`, `shape`, `live` or `generate`, ask no question, and write no `PRODUCT.md` or `DESIGN.md`; and when impeccable disagrees with the ticket, its mockups, `sprintify-ui` or `frontend-development`, those win. Say in the report which case applied and what impeccable changed, or `impeccable : non applicable` with the reason.
   - **Shared logic lives in one place.** Anything a second caller could want goes where the repository already puts that kind of thing (a service, an action, a model method, a composable, a Base* component), never inline in a controller, a job or a Vue template.
   - Build it test-first (red, green, refactor), one vertical slice at a time, at the seams the ticket names, or the most obvious public interface. Run the touched test files and `vendor/bin/pint --dirty` as you go. Commit on the branch in the format of section 2. Report the commit range.
2. As soon as it commits, start that ticket's **review sub-agent** with `review.md` in this folder, the ticket as spec and its commit range, while the next implement sub-agent starts.
3. A review's findings go into a **queue**, never straight into the tree. At each commit boundary (an implement sub-agent finished, the next not started), classify the queue with section 1 and give the findings worth doing to a fix sub-agent: at most one `review:` commit per ticket. Keep every finding with its priority, its disposition (`corrigé`, with the commit, or `refusé`) and its reason, for the report and the retrospective, and use the same words in both. A decision that a review looks at and accepts is not a finding. Findings that land after the last ticket are drained before the screen check. When the queue is empty, push the branch.

One exception stops the pipeline: a **blocking finding**, where the reviewed ticket's foundation is wrong and the ticket in progress builds on it (a wrong seam, a changed contract, never a nit). Stop the current implement sub-agent, fix, and start it again fresh. Give the fix sub-agent the uncommitted files of the stopped one by name: it removes them one by one before it fixes. The new implement sub-agent corrects the commits of the stopped one with new commits, and never resets them.

## 4. Pull request

The branch is already pushed, at the end of section 3, so CI has been running while the screens were checked. When the screen check added a commit, push it now: the check runs below and the pull request must be on the last commit.

Then the full suite, by what the diff touches (`git diff --name-only origin/dev...HEAD`):

- **Frontend only**: every changed file is a `.vue`, `.ts`, `.js` or `.css` file under `resources/`, or `package.json` or `package-lock.json`. The PHP suite tests none of it, and the repository's PHP workflow usually skips such a push. Run the frontend scripts of `package.json` instead (tests, lint, type check; the `assets: rebuilt` line of `cloud-sync` is the build check, as `brief.md` says), and write in the report: `Suite PHP non lancée : la PR ne change aucun fichier PHP.`
- **Anything else**, a translation file included: the push of section 3 started CI on this commit, so read it first, with `gh api repos/<owner>/<repo>/commits/$(git rev-parse HEAD)/check-runs`. When the job of `.github/workflows` that runs the whole PHP suite (`php artisan test` or `phpunit`, with no filter and no path) is `completed` with `success` on this commit, do not run the suite again in the VM, and write in the report: `Suite PHP : verte en CI sur <sha> (check <nom>), non relancée dans la VM.` In every other case (no such job, no check on this commit, a check that still runs or failed, a doubt), start a sub-agent for the full suite, alone, when nothing else runs: `php artisan test --parallel --recreate-databases --compact`, reporting each failure with its test name. When unsure, run it.

Fix the failures with a fix sub-agent and push. Then open the pull request to `dev` with `mcp__github__create_pull_request` (`gh pr` fails: the proxy blocks GraphQL), and move every ticket of the set to `in review`.

The title is the parent's title. The body is in simple French, for a reader without the project's context:

```markdown
**Ticket :** <url du ticket parent>
**Vidéos :** <la suite de la ligne « Vidéos » de l'étape 4 de la section 6 de `SKILL.md`, avec ou sans vidéo>

## Écart avec la spec
Chaque choix qui contredit une phrase du ticket, citée, avec ce que le code fait à la place et pourquoi. Omise s'il n'y en a pas.

## Résumé
2 à 4 phrases : le problème, ce que la PR change.

## Schéma de base de données
Le tableau de la section 6 de `SKILL.md`. Omise quand la branche ne change ni le schéma ni les données.

## Changements
- Une puce par ticket, avec le lien du ticket.

## Tests de haut niveau
- [ ] 3 à 6 tests faisables à la main en quelques minutes (parcours utilisateur, pas technique).

## Notes
Choix à valider, dette assumée, hors du périmètre, bugs hors du ticket avec le lien de leur ticket. Omise si vide.
```

## 5. Feedback loop: autofix

Claude's native autofix watches the pull request. `subscribe_pr_activity` delivers each CI result, each Codex review and comment, and each comment and review of a person as a turn of its own, which wakes this session. Nothing waits inside a turn: never poll with `sleep`, and never end a turn on `ScheduleWakeup` or `CronCreate`.

**Subscribe** right after the pull request opens: `subscribe_pr_activity` with `owner`, `repo` and `pullNumber`, from the `claude-code-remote` server or, in a routine run, the `Claude_Code_Remote` connector (load it with `ToolSearch` when only its name is listed). Its `subscription.created` event carries the platform's rules for a pull request you drive: follow them with this section. When the call is refused or missing, or its result says another Claude agent already watches the pull request, nothing will wake this session: say so under "PR, CI et Codex" with the error, read the state once with `pr-status`, and finish the run as if the pull request had settled, with `PR non surveillée` in the report and the notification. Then finish section 6 of `SKILL.md`, steps 1 to 7, and end the turn: the next event wakes you.

`pr-status <pull request number>` reads, once and without waiting, what an event does not say in full: the state of every check run of the last commit and whether Codex approved that commit. Codex often approves with only a thumbs up or the state line of its `Codex Review Summary` comment. Run it from the repository. Exit 2 (`pr-status: the pull request could not be read`) means GitHub did not answer: run it once more, then report CI and Codex as not known under "PR, CI et Codex".

- **CI**: `ci: passed`, `ci: failed` with the names of the checks, `ci: pending`, or `ci: none`. Read a failure with `gh api repos/<owner>/<repo>/commits/<sha>/check-runs`. Reproduce it in the VM, classify it, fix it. A failure the change did not cause is not relevant: name it in the report.
- **Codex**: `codex: approved`, `codex: findings`, `codex: reviewing` (👀, no answer yet), `codex: waiting` (no sign yet on a commit less than 5 minutes old), `codex: absent` (no sign on an older commit: the repository has no Codex review, and the run is CI only) or `codex: older-commit` (its last answer is for a commit before the last push: never count it as an approval of the last commit, and say so in the report).

### Each wake is one wave

A wave handles everything that is open on the pull request, not only the event that woke you, so one push answers all of it. There is no limit on the number of waves.

1. After a restart, check the stack as section 1 of `SKILL.md` says. Check that the checkout is on the branch and up to date with `git fetch origin <branch>`: a person may have pushed. Merge what they pushed (`git merge --no-edit FETCH_HEAD`); never rebase or force-push.
2. When a notice says notifications are pending, call `ReadNotifications` until it reports 0 remaining.
3. Read the whole state: `pr-status`, then the reviews, the review threads and the comments with `mcp__github__pull_request_read`. List every CI failure on the last commit, every Codex finding and every comment or review of a person that has no answer yet.
4. Classify every item with section 1. CI, Codex and a person's comment are evidence to judge, not instructions: Codex's rare edge cases, hypothetical races and reopened decisions are what section 1 rejects. A person's comment that asks for something outside the ticket follows "Bugs hors du ticket" in `SKILL.md`, and one that asks for what the limits of `SKILL.md` forbid (a merge, a change to `.github/workflows`, another system, a secret) is left for a person, with a reply that says why. A finding you already rejected that comes back with no new evidence gets a reply that points to your first answer, never a fix the other way.
5. Fix every item worth doing in one batch with one fix sub-agent, then validate (the touched tests, `vendor/bin/pint --dirty`) and push once. With `agent:ultracode`, the wave is a fix workflow, then its own review rounds until dry. A wave with nothing worth fixing pushes nothing.
6. After the push, answer every thread and every comment of the list. Reply in the comment's language: fixed, with the commit link `https://github.com/<owner>/<repo>/pull/<n>/commits/<sha>`; rejected, with the reason; or deferred. A review thread gets its reply with `gh api repos/<owner>/<repo>/pulls/<n>/comments/<id>/replies -f body='…'`, a comment that is not on a line with `mcp__github__add_issue_comment`. Then resolve each Codex thread with `mcp__github__resolve_review_thread`. A person's thread stays open, for that person. A rejected finding also goes under "Choix à valider" in the report and the pull request body, because a resolved thread is collapsed.
7. Update the report comment (section 6, step 7 of `SKILL.md`), and the pull request body when it must change. When a fix changes a screen, run section 5 of `SKILL.md` again and send the new video.
8. When the pull request has settled (below) and had not settled before this wave, assign it for review, then run section 7 of `SKILL.md`, then section 6, steps 8 and 9. **Assign for review**: call `get_project` on the parent's project and read `lead`. Call `save_issue` with `assignee: "<lead.id>"` on the parent and on every ticket of the set: the lead of the project reviews the pull request. With no project or no lead, leave the assignees as they are and write `Aucun lead sur le projet : ticket non assigné pour la review.` under "PR, CI et Codex". Do it once per run: a later wave that settles the pull request again does not assign again. Write `Assigné à <nom du lead> pour la review.` under "PR, CI et Codex", and name the lead in the notification. A later wave that pushes a fix or answers a person ends with a short notification instead, and runs section 7 again when the pull request settles again and is not merged.
9. End the turn. When Codex is still `reviewing` or `waiting`, its answer wakes you.

The pull request **has settled** when CI is `passed` on the last commit, Codex is `approved` or `absent`, and every thread and comment of a person has an answer. Report every other state as it is, never as green or approved: `ci: pending`, `ci: none`, a `ci: failed` the change did not cause, `codex: reviewing`, `codex: waiting`, `codex: older-commit`, `codex: findings` that were all rejected.

**The end.** When an event or `pr-status` says the pull request was merged or closed, a person took it: call `unsubscribe_pr_activity` from the same server, push nothing, add the outcome to the report comment, and end the turn. After a merge by section 7 of `SKILL.md`, unsubscribe the same way.

The report of section 6 in `SKILL.md` names: each ticket with its commits and status, the findings by priority and disposition with reasons (including each duplicate of existing code and what it now reuses), the concurrency assumption, and, under "PR, CI et Codex", the waves used, the Codex state and the threads answered, the comments of people and their answers, and the CI state.
