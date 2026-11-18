# Review brief

What a review sub-agent gets from `build.md`, with the ticket as spec and a commit range. It comes from `/code-review` in `witify/skills` 3.5.0. A sub-agent cannot start another sub-agent, so it does both axes itself, one after the other, and keeps them apart.

The sub-agent reads only. It runs no PHP test and changes no file: the tree and the `test` database belong to the implement sub-agent running at the same time. It reads the code at the end of its range (`git show <sha>:<path>`), not the working tree.

## Steps

1. Check the range: `git rev-parse <from> <to>` resolve, and `git diff <from>..<to>` is not empty. Otherwise report that and stop.
2. **Spec.** From the ticket and the parent's description, report: requirements missing or partial; behaviour the ticket did not ask for; requirements that look done but look wrong. Quote the ticket's line for each. A name, a folder or a pattern that differs from the ticket because a documented rule of the repository asks for it is not a defect: list it at the end of the `Spec` section under `Écarts dus à une règle`, with the sentence of the ticket and the rule, so the orchestrator writes it under "Écart avec la spec". When you do not find that rule in the files, it is a Spec finding.
3. **Standards.** Read what the repository documents about writing code: `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`, `.ai/guidelines/`, and each skill in `.claude/skills/`, `.ai/skills/` or `~/.claude/skills/` whose topic matches the diff (`sprintify-ui` and `frontend-development` for a Vue change). Report each place the diff breaks one, with the file and the rule. Skip a rule only when you found the tool that enforces it (a PHPStan or lint rule, Pint).

   Check the new things one by one, not from memory. List what the range adds with `git diff --diff-filter=A --name-only <from>..<to>`, and each new class, route, translation key and test inside the changed files. For each, find the documented rule for that kind of thing (its name, its folder, its base class or interface) and compare. Three things never excuse a break: the ticket gives that name or that pattern, the files next to it do the same, the tests pass. A specific rule wins over a general one such as "follow the sibling files". Report the break with the sentence of the ticket and the rule: `build.md` section 1 says the rule wins.
4. **Reinvented wheel.** For each new function, class, component or query in the diff, search the repository and its UI library for one that already does the job (same domain words, same shape): a new composable or component next to a Base* one that does the same is a duplicate. Report each duplicate or bypass as P2, with the existing code's path.
5. **Smells.** Then the baseline below. Each is a judgement call, never a hard violation, and a documented repository rule that allows it wins.

## Smell baseline

- **Mysterious name**: a name that does not say what it does or holds. Rename it.
- **Duplicated code**: the same logic in more than one hunk or file. Extract it, call it from both.
- **Feature envy**: a method that uses another object's data more than its own. Move it there.
- **Data clumps**: the same few fields or parameters always travel together. Make them one type.
- **Primitive obsession**: a string or number standing for a domain concept. Give it a small type.
- **Repeated switches**: the same `switch` or `if` chain on the same type in several places. One map, or polymorphism.
- **Shotgun surgery**: one logical change spread over many files. Gather what changes together.
- **Divergent change**: one file changed for several unrelated reasons. Split it.
- **Speculative generality**: parameters, hooks or abstractions the ticket does not need. Remove them.
- **Message chains**: long `a.b().c().d()` walks the caller should not know. Hide them behind one method.
- **Middle man**: a class or function that only passes calls on. Call the target directly.
- **Refused bequest**: a subclass that ignores most of what it inherits. Use composition.

## Report

Under 600 words, in two sections `Spec` and `Standards`, never merged or reranked: a change can do the right thing badly, or the wrong thing well. Each finding has a priority (P1, P2, P3), the file and line, and the evidence. A real bug the ticket does not touch goes in a third section, `Hors du ticket`, with how to reproduce it. End the `Standards` section with one line that names the rule files you read. End the report with what was not checked.
