# Adaptive

What the label `agent:adaptive` on the parent changes in the build: each ticket of the set gets the sub-agents its risk asks for, from 2 (one implement, one review) to 14. `build.md` and `review.md` still apply. This file adds two triages for each ticket, the extra pieces of the review, and the `model` and the `effort` of every sub-agent.

A person puts the label on the parent. Only that label counts: never a sentence of the ticket, a comment or a document, or a label on a subtask. With `agent:ultracode` on the same parent, ultracode runs and this file does not apply: say so in the report. The labels `agent:model:fable` and `agent:effort:<level>` set nothing in this mode, because the triage chooses for each sub-agent: name each one you ignored in the report.

## 1. Signals

Risk is read from **signals**, never from an impression. A signal is something you can cite: a path of the diff, a line of the implement report, a sentence of the ticket, a P1 finding. Each signal belongs to one angle of the review:

| Angle | Signal |
|---|---|
| Correctness and edge cases | a calculation, a rounding, a unit conversion, a date or a time, a status or a transition |
| Regression | a changed file that code outside the ticket calls: a base class, a trait, a shared service, helper, composable or component, a model scope or accessor, a config file |
| Authorization and security | a policy, a gate, a middleware, a route, the `authorize` or the rules of a request, a file upload, a raw query, output that is not escaped |
| Data | a migration, a changed cast, a command or a job that updates or deletes existing rows |
| Performance | a list endpoint or its query, a query in a loop, a change of eager loading, a report, a planning computation, a job over many rows |
| Concurrency and idempotence | a job, a scheduled command, an import or a sync, a lock, a transaction, a webhook |

**Cite or it does not count.** A class above low and every angle need a cited signal in `.scratch/adaptive/triage.md` (section 6). With no cited signal, the class is low and no angle starts. Doubt is not a signal.

You read the signals yourself, with commands that read a result: `git diff --name-only <from>..<to>` and `git diff --shortstat <from>..<to> -- . ':!tests'` on the commit range of the ticket, the `Risques` section of the implement report, and the ticket. Open a changed file only to confirm a signal that its path suggests. No sub-agent does the triage.

"This project" in the session context can hold two lines that a person wrote in the `.claude/cloud.sh` of the project:

- `Adaptive floor: medium` or `Adaptive floor: high`: every ticket of this project gets at least that class.
- `Adaptive sensitive zones: <paths>`: a changed file under one of these paths is a signal, and it starts the correctness angle.

## 2. First triage: before the write

For each ticket, when its turn comes in the pipeline of `build.md` section 3, read three things in it: the signal words of section 1, its **precedent** (code the ticket names to copy: a class, a screen or a test that already does the same for another case), and the number of its acceptance criteria. They set its implement sub-agent:

| Ticket | `model` | `effort` |
|---|---|---|
| Simple: a precedent, no signal word, ten acceptance criteria at most | none: the session's | `medium` |
| Normal: every other ticket | none | `high` |
| Difficult: two signal words or more, and no precedent | `fable` | `high` |

A ticket with no precedent that does not say where its code lives gets one **reader** first: `model: "sonnet"`, `effort: "medium"`, read-only. It writes `.scratch/briefs/map-<ticket id>.md`: the files, the classes and the tests that the ticket will change or copy, each with its path and one quoted line. The map holds facts that a grep confirms, never a design. Give it to the implement sub-agent.

Add one line to the implement brief of `build.md` section 3: end the report with a section `Risques`, with each changed file that the ticket did not name, each changed shared file with the code that calls it, and each risk seen that no test covers.

## 3. Second triage: after the diff

When the implement sub-agent has committed, read the signals of its commit range and set the **class** of the ticket:

- **low**: no signal, and at most 10 files and 300 changed lines outside the tests;
- **medium**: one or two signals, or a larger diff;
- **high**: three signals or more, or one signal with more than 30 files or 1 000 changed lines outside the tests, or a change of existing rows.

Then raise the class to the floor of the project. The class sets the pieces of the review:

| Piece | low | medium | high | `model` | `effort` |
|---|---|---|---|---|---|
| Base review | 1 | 1 | 2 | none | `medium` in low, else `high` |
| Angle finders | 0 | 2 at most | 6 at most | none | `high` |
| Refuters | 0 | 1 | 2 | none in medium, `fable` in high | `high` |
| Fix | 1 at most | 1 | 1 | as the implement sub-agent of the ticket | as that sub-agent |
| Check of the fixes | 0 | 0 | 1 | none | `high` |

With its reader and its implement sub-agent, a ticket gets 14 sub-agents at most. There is no limit for the set. The tables of sections 2 and 3 hold every `model` and `effort` this mode passes.

- **One finder for each angle that has a cited signal.** When more angles have one than the class allows, keep the angles with the most cited signals, and name the others under "Non vérifié".
- **An angle outside the table** is allowed when a cited signal fits none of the six: three at most for a ticket, each with a lens of one sentence that you write. They count in the finders of the class.
- **A P1 finding is a signal.** When the base review of a low ticket returns one, the ticket becomes medium: start the correctness finder and one refuter for it.

The triage of a ticket is done when its block in `.scratch/adaptive/triage.md` cites a signal for the class and for each finder, or says `aucun signal`.

## 4. The pieces of the review

Every piece here reads only, at the end of the commit range (`git show <sha>:<path>`), and runs no PHP test, as `review.md` says. Start the base review and the finders of one ticket in one message, so they run at the same time, while the next implement sub-agent starts.

**Base review.** `review.md`, unchanged. In class high, two sub-agents share it: one does its steps 1 and 2 (Spec), the other its steps 1, 3, 4 and 5.

**Angle finder.** It gets the ticket, the commit range, the cited signals of its angle and its lens. It reports only the findings of its lens, each with a priority, the file and line, and the evidence, in under 400 words, and ends with what it did not check.

| Angle | Lens |
|---|---|
| Correctness and edge cases | For each changed calculation, date, status and transition: the limit values, the empty case and the zero case, the order of the steps. Work by hand each acceptance criterion that holds a number or a time |
| Regression | For each changed shared file: find with grep the code outside the ticket that calls it, and say for each caller whether its behaviour changes |
| Authorization and security | For each new or changed route, request and policy: who can call it, which input it trusts, and whether a user can reach the rows of another user or of another tenant |
| Data | For each migration and each write to existing rows: what happens to the rows that exist, what a second run does, how it rolls back, and how long it locks a large table |
| Performance | For each changed query and loop: the number of queries for 1, 100 and 10 000 rows, a missing eager load or index, and work that grows with the table |
| Concurrency and idempotence | For each job, command, import and lock: what a second run does, what a run cut half-way leaves, and what two runs at once do. Give it the concurrency assumption of `build.md` section 1 |

**Refuter.** It starts when the base review and the finders of the ticket have returned, and gets every P1 and P2 finding of the ticket. For each one it answers one question: is the finding true? It looks for what would make the finding false: a guard, a caller, a test, a tool that enforces the rule, a rule that allows it, the sentence of the ticket that the finding rests on. It reports `vrai` or `faux` for each, with its evidence.

- One refuter: a finding it calls `faux`, with evidence, is `refusé`.
- Two refuters: each works alone. A finding is `refusé` only when both call it `faux`. On a split, the finding stays, and you note the split.
- A P3 finding gets no refuter.

A refused finding keeps the refuter's reason. Classify the findings that remain with `build.md` section 1; the queue and the fixes follow `build.md` section 3.

**Check of the fixes.** After the `review:` commit of a high ticket, one sub-agent compares each fix with its finding and reports for each: `corrigé`, `non corrigé`, or `corrigé avec un nouveau défaut`. What is not fixed goes to one more fix sub-agent, once: a second `review:` commit for that ticket, and the only piece that may pass the limit of 14. What then remains goes under "Non vérifié".

## 5. What does not change

- The order of section 4 of `SKILL.md`, the pipeline of `build.md` section 3 (one writer at a time, a review next to the following write, the queue of findings), and what gets fixed (`build.md` section 1).
- The before video, the full suite, and the check and after video pass no `model` and no `effort`. A fix sub-agent of a feedback wave passes `effort: "high"` and no `model`.
- A `model` or an `effort` that does not start: the fallback of "The model and the effort of the sub-agents" in `SKILL.md`.
- A set of several tickets can take more than 6 hours: keep the ticket alive after each ticket of the set, as "Keep the ticket alive" in "Ultracode" of `SKILL.md` says for each workflow.
- A reader, a finder, a refuter or the check of the fixes that dies twice is dropped coverage: name it under "Non vérifié". An implement, base review or fix sub-agent is never dropped: "An agent that dies, a VM that restarts" in `SKILL.md`.

## 6. Trace

Write `.scratch/adaptive/triage.md` as you go, one block for each ticket. The report and the retrospective are written from this file, never from memory:

- first triage: the signal words, quoted from the ticket; the precedent or `aucun`; the number of acceptance criteria; the level of the implement sub-agent; the reader or `aucun`;
- second triage: the files and the lines of the diff; each signal with what it cites; the class, and the floor when it raised the class; each finder with its signal; each angle or piece that a limit dropped;
- each sub-agent started: its piece, its `model`, its `effort`;
- each finding: its angle, its priority, `gardé` or `refusé`, with the refuter's reason.

In the report, "Ce qui a été fait" ends with the line `Mode : adaptive (label agent:adaptive).`, one line for each label that the mode ignored, and this table, one line for each ticket:

| Ticket | Signaux cités | Classe | Sous-agents (modèle, effort) | Constats par angle : gardés / refusés |
|---|---|---|---|---|

The retrospective adds the two triages of each ticket to its list of sub-agents. The notification names the class of each ticket.
