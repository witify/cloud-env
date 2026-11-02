---
name: loom
description: Analyze a Loom video in detail — transcript with speakers, chapters, and actual frames inspected via ffmpeg. Use when the user shares a loom.com link, or when one appears inside material being worked (a ClickUp or Linear task, a grill, a spec) and its content matters to the task.
---

# Loom

Analyze a Loom video without watching it in real time: the transcript is the **map**, frames are the **evidence**. Read the map first, then look only where it points.

All API access goes through [`scripts/loom-api.sh`](./scripts/loom-api.sh) (bash + curl only; runs on linux, macOS, and Windows git-bash). Frames need `ffmpeg` on PATH — if missing, have it installed first (`brew install ffmpeg` / `winget install ffmpeg` / `apt install ffmpeg`).

## 1. Identify the video

The video ID is the 32-hex segment of `loom.com/share/<id>` or `loom.com/embed/<id>`. Keep hold of *why* the video was opened — the grill question, the ticket's bug report — that intent decides what to look for.

## 2. Map the video

Run, in parallel:

```bash
scripts/loom-api.sh meta <id>        # title, duration, resolution, owner, Loom's own AI summary
scripts/loom-api.sh chapters <id>    # "00:00 Chapter title" list — free table of contents
scripts/loom-api.sh transcript <id>  # signed URLs: captions_source_url (VTT), source_url (JSON)
```

If `meta` returns `VideoPasswordMissingOrIncorrect`, ask the user for the video password and pass it as the third argument to every call. `PrivateVideo` means it's restricted to the owner's workspace — only the user can open that one; say so instead of retrying.

Then `curl` the `captions_source_url` into a working file and read it whole. The VTT carries speaker tags (`<v Name>…</v>`) and timestamps — it is the primary source for everything *said*. No transcript (`GenericError` or null)? Say so and lean fully on frames.

## 3. Get a seekable video URL

```bash
scripts/loom-api.sh video-url <id>   # → {"url": "…mp4?Policy=…&Signature=…"}
```

This signed mp4 supports HTTP range requests, so ffmpeg can seek anywhere in it remotely — a frame costs ~2 s regardless of video length, no download. Always quote the URL (it holds `&`). Signed URLs expire after roughly an hour: a later 403 means re-run the script, not a failure.

Empty response (HTTP 204)? Fall back to `raw-video-url`. If *that* URL ends in `.m3u8` or `.mpd`, ffmpeg cannot read it (the segments need signed query params ffmpeg won't propagate) — download with `yt-dlp "<share url>"` if installed, otherwise report the limitation.

## 4. Look at frames

Targeted grab — the workhorse:

```bash
ffmpeg -hide_banner -loglevel error -ss 00:31:24 -i "<signed url>" -frames:v 1 -q:v 3 frame_3124.jpg
```

Pick timestamps from the map: every chapter start, and every transcript moment where the screen carries the content — "as you can see", "here", an error being shown, a demo step, the exact second a ticket's bug is reproduced. Read the jpgs (batch several per response); screen shares are legible at full quality, down to dialog text.

Meeting recordings (Meet/Zoom/Teams) burn a large part of every frame on webcam tiles. Read the first frame, measure where the shared screen sits, then add `-vf "crop=W:H:X:Y"` to every subsequent grab so the frames carry only the shared screen (a Meet layout at 1920×1080 typically crops to about `crop=1400:880:0:0`). Independent grabs can run in parallel (`&` … `wait`) — 17 frames land in ~5 s.

Sweep — when visuals carry more than speech, or the video is short (≲ 10 min): download once (`curl -o loom.mp4 "<signed url>"`), then

```bash
ffmpeg -hide_banner -loglevel error -i loom.mp4 -vf fps=1/30 sweep_%03d.jpg   # frame N ⇒ t = N×30 s
```

Tighten `fps` around dense passages. A sweep over a remote URL decodes the whole stream — for anything long, sweep the local file only.

## 5. Attaching frames to a tracker

When the deliverable is a ClickUp or Linear task with screenshots, budget the uploads — they cost more wall-clock than the entire video analysis. Default to the **4–6 frames** that actually carry the report; attach more only when asked.

- **Linear (MCP)**: strictly one file at a time — `prepare_attachment_upload` → raw `PUT` → `create_attachment_from_upload`. The signed URL dies in **60 s**, so the `PUT` must be the immediate next call, written as one minimal `curl -X PUT --data-binary @file -H <the exact signed headers> "<url>"` line; an `ExpiredToken` means re-prepare, not a failure. Uploaded assetUrls render inline in the description as `![…](assetUrl)`.
- **ClickUp**: `clickup_attach_task_file` takes a public URL or <200 KB base64; local files go through `clickup_request_attachment_upload`.

## 6. Report

Done when the question that opened the video is answered with **timestamped evidence** — `[hh:mm:ss]` + speaker for anything quoted, `[hh:mm:ss]` + what was on screen for anything seen — and any section deliberately not examined is declared rather than silently skipped. Distinguish what was *said* from what was *shown*; they disagree more often than expected.
