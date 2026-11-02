# Review brief

What a review sub-agent gets from `build.md`, with the ticket as spec and a commit range. It comes from `/code-review` in `witify/skills` 3.5.0. A sub-agent cannot start another sub-agent, so it does both axes itself, one after the other, and keeps them apart.

The sub-agent reads only. It runs no PHP test and changes no file: the tree and the `test` database belong to the implement sub-agent running at the same time. It reads the code at the end of its range (`git show <sha>:<path>`), not the working tree.

## Steps

1. Check the range: `git rev-parse <from> <to>` resolve, and `git diff <from>..<to>` is not empty. Otherwise report that and stop.
2. **Spec.** From the ticket and the parent's description, report: requirements missing or partial; behaviour the ticket did not ask for; requirements that look done but look wrong. Quote the ticket's line for each.
3. **Standards.** Read what the repository documents about writing code: `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`, `.ai/guidelines/`, and each skill in `.claude/skills/` or `.ai/skills/` whose topic matches the diff. Report each place the diff breaks one, with the file and the rule. Skip what tooling already enforces.
4. **Reinvented wheel.** For each new function, class, component or query in the diff, search the repository for one that already does the job (same domain words, same shape). Report each duplicate or bypass as P2, with the existing code's path.
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

Under 600 words, in two sections `Spec` and `Standards`, never merged or reranked: a change can do the right thing badly, or the wrong thing well. Each finding has a priority (P1, P2, P3), the file and line, and the evidence. A real bug the ticket does not touch goes in a third section, `Hors du ticket`, with how to reproduce it. End with what was not checked.
