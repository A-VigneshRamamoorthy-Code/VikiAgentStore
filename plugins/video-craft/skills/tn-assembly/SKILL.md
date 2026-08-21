---
name: tn-assembly
description: >
  Turns one long legislative assembly webcast into a set of publishable videos.
  Given a YouTube URL of a multi-hour session, it finds the moments worth
  watching, detects heated exchanges acoustically, decides how many videos the
  session actually justifies rather than a fixed number, cuts each segment on
  natural speech boundaries at full resolution, and assembles branded long-form
  episodes plus vertical Shorts that route viewers back to them. Confirmed
  clashes lead their episode and always get a Short. If a configured public
  figure appears on camera, that episode is packaged around them. Packaging,
  SEO and upload are delegated to the youtube-publish skill. Use when asked to
  cut up an assembly, parliament or council session, to make highlights or
  Shorts from a long recorded proceeding, or to turn a legislature webcast into
  channel content.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "1.0.0"
---

# TN Assembly

An assembly session is seven or eight hours of procedure containing perhaps
forty minutes anyone would watch. This skill finds that forty minutes, decides
how many videos it is worth, and cuts them properly.

It handles **segmentation only**. Titles, thumbnails, descriptions, tags and
upload belong to the sibling **`youtube-publish`** skill, so the same packaging
logic serves any video, not just assemblies.

## Non-negotiables

1. **The number of videos is derived, not configured.** A session with six
   flashpoints yields several episodes; a procedural sitting yields one digest
   or none. Never pad a quiet session to hit a target count.
2. **A clash label is a candidate, not a fact.** The detector finds *acoustic*
   turmoil. Applause, laughter and a chorus of desk-thumping look identical to
   a shouting match on a spectrogram. Confirm by watching or transcribing
   before any title claims a fight.
3. **Never cut mid-sentence.** Every in and out point snaps to a speech onset
   and a following pause.
4. **Verify sync after any cutting change.** Audio-video desync is invisible in
   a container probe. Run `checks.py` on at least one clip.
5. **Nothing is published automatically.** Videos are rendered and left private
   for a human to approve.
6. **Never hardcode a person, channel or URL.** Everything comes from
   `project.json`.
7. **Report what the session contained**, including "nothing much". The value
   of a session channel is that viewers trust the highlight to be a highlight.

## Quick start

```bash
mkdir -p myproject && cd myproject
cp <skill>/examples/project.json .        # edit source.url and channel
python3 <skill>/scripts/pipeline.py .     # ingest → analyse → plan → cut → build
```

Then package and upload each result with the `youtube-publish` skill.

## Pipeline

| Stage | Script | What it does |
|---|---|---|
| ingest | `ingest.py` | Probes the source; pulls audio and a small scan video. Never downloads the full session. |
| analyse | `analyse.py` | Streams per-second acoustic features; scores highlight windows; flags clashes. |
| vip | `faces.py` | Optional. Finds a configured public figure on camera. |
| plan | `plan.py` | Decides episode and Short counts, assigns moments, applies clash and VIP priority. |
| cut | `cut.py` | Fetches each segment at full resolution, snapped to speech boundaries. |
| build | `build.py` | Assembles intro → clips with lower-thirds → outro, loudness-normalised. |
| shorts | `shorts.py` | Renders 9:16 verticals with a burned hook and a CTA back to the episode. |
| package | → `youtube-publish` | Titles, thumbnails, descriptions, tags. |

Each stage reads only what earlier stages wrote to `meta/`, so any stage can be
re-run alone. Resume with `--from plan`, or run one with `--only cut`.

## Reference

Load only what the task needs.

- **`reference/project-config.md`** — every `project.json` field.
- **`reference/highlight-detection.md`** — how moments are scored, and why the
  thresholds are relative to each session rather than absolute.
- **`reference/clash-detection.md`** — how fights are found acoustically, the
  calibration that made it work, and the confirmation rule.
- **`reference/cutting.md`** — the desync trap, boundary snapping, sync
  verification.
- **`reference/vip-packaging.md`** — detecting a public figure and pivoting the
  episode around them.
- **`reference/shorts.md`** — vertical framing, hooks, and routing to long-form.
- **`reference/packaging.md`** — the handoff to `youtube-publish`, including the
  Politainment channel setup.
- **`reference/editorial-ethics.md`** — covering a legislature without
  fabricating drama.

## Requirements

`yt-dlp`, `ffmpeg` (with `overlay`; `drawtext` is not required), `numpy`,
`Pillow`. VIP detection additionally needs `insightface` and `onnxruntime`.
Text is rendered through CoreText, so **rendering is macOS-only**; analysis,
planning and cutting are portable.
