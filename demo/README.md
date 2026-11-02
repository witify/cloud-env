# Demo videos

A video shows a person what changed, so it is a scripted story and not a recording of your exploration.

1. Explore with the `mcp__playwright__*` tools until you know the screens and the selectors.
2. Write `.scratch/demo/<name>.cjs`. Start from `/opt/cloud-env/demo/smoke.cjs`, and change the first argument of `record()` to `<name>`: it names the output files. Keep the story under 90 seconds, on the changed behaviour only, with captions in French.
3. Run `demo-video .scratch/demo/<name>.cjs`. It writes `.scratch/demo/<name>.mp4` and `<name>.json`.
4. Read the JSON: `steps`, `consoleErrors` and `failedRequests`. A console error or a failed request on a changed screen is a finding to fix, not noise. Then extract one frame and look at it, to confirm the video shows what you claim:
   `ffmpeg -y -ss 8 -i .scratch/demo/<name>.mp4 -frames:v 1 /tmp/frame.png`
5. Stop here. Report the mp4 path, the JSON findings and what the frame shows. The agent that runs the ticket sends the video.

## The recorder

`demo` gives you: `step(title, actions)`, `caption(text)`, `signIn(email, password, landingPath)`, `goto(path)`, `click(selector)`, `type(selector, text)`, `moveTo(selector)`, `pause(ms)`, `confirmPassword(password)`, `screenshot(name)`, and `page` for raw Playwright.

`signIn()` with no argument uses the login of this project, the one in the session context. `signIn` clears the session first, so a scenario can change role.

## Before and after

When a ticket changes an existing screen, record the "before" first, from the unchanged code at the start of the work: `<name>-avant.cjs`, then `<name>-apres.cjs` with the same steps. A person compares them side by side.

## What a video cannot show

The session context names what does not work in this VM: integrations with no keys, screens with no data. Say so in the report and name them as checks for a Mac.
