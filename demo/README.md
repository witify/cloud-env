# Demo videos

A video shows a person what changed, so it is a scripted story and not a recording of your exploration.

1. Explore with the `mcp__playwright__*` tools until you know the screens and the selectors.
2. Write `.scratch/demo/<name>.cjs`. Start from `/opt/cloud-env/demo/smoke.cjs`, and change the first argument of `record()` to `<name>`: it names the output files. Set `startPath` to the screen where the story starts, such as `/admin/clients/12`. Keep the story under 90 seconds, on the changed behaviour only, with captions in French.
3. Run `demo-video .scratch/demo/<name>.cjs`. It writes `.scratch/demo/<name>.mp4` and `<name>.json`.
4. Read the JSON: `steps`, `consoleErrors` and `failedRequests`. A console error or a failed request on a changed screen is a finding to fix, not noise. Then extract two frames and look at them: the first must already show the start screen, loaded, and the second confirms the video shows what you claim:
   `ffmpeg -y -ss 0.2 -i .scratch/demo/<name>.mp4 -frames:v 1 /tmp/frame-start.png`
   `ffmpeg -y -ss 8 -i .scratch/demo/<name>.mp4 -frames:v 1 /tmp/frame.png`
5. Stop here. Report the mp4 path, the JSON findings and what the frames show. The agent that runs the ticket sends the video.

## The recorder

The video opens on `startPath`, already signed in and already loaded. The sign-in, the cold first load and any `offCamera()` span happen off camera, and `demo-video` cuts them out of the mp4 (`cuts` in the JSON). Never show the login page, a spinner or a landing page the ticket does not change.

`record(name, scenario, { startPath, signedIn, email, password })`. With no `email`, it uses the login of this project, the one in the session context.

`demo` gives you: `step(title, actions)`, `caption(text)`, `goto(path)`, `click(selector)`, `type(selector, text)`, `moveTo(selector)`, `pause(ms)`, `confirmPassword(password)`, `screenshot(name)`, `offCamera(actions)`, `signIn(email, password, landingPath)`, `signInOnCamera(email, password)`, and `page` for raw Playwright.

- `offCamera(actions)`: setup the person does not need to see, such as opening a second record. Keep the story itself on camera.
- `signIn(email, password, landingPath)`: changes role off camera and opens `landingPath`. Only to show a second role.
- A ticket that changes the sign-in itself (login form, two-factor, password reset, redirect after login): record with `{ signedIn: false, startPath: '/login' }` and sign in on camera with `signInOnCamera()`. This is the only case where the video shows the login page.

## Before and after

When a ticket changes an existing screen, record the "before" first, from the unchanged code at the start of the work: `<name>-avant.cjs`, then `<name>-apres.cjs` with the same steps. A person compares them side by side.

## What a video cannot show

The session context names what does not work in this VM: integrations with no keys, screens with no data. Name them in the report under "Non vérifié", with the reason.
