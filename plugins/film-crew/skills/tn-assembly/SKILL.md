---
name: tn-assembly
description: >
  Turns long legislative webcasts into publishable episodes and Shorts:
  detects whether the source is live or recorded, and for a live sitting cuts
  and uploads as it runs, tracking the stream to completion. Detects
  highlights and clashes, chooses episode count, cuts on speech boundaries,
  preserves resolution and flags VIP appearances. Given no URL it checks the
  configured channel for a live stream. SEO/upload go to head-of-marketing.
  Use for assembly, parliament or council sessions and long proceedings.
  Part of film-crew, normally dispatched by the director skill.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "1.3.0"
---

# TN Assembly

An assembly session is seven or eight hours of procedure containing perhaps
forty minutes anyone would watch. This skill finds that forty minutes, decides
how many videos it is worth, and cuts them properly.

It handles **segmentation only**. Titles, thumbnails, descriptions, tags and
upload belong to the sibling **`head-of-marketing`** skill, so the same packaging
logic serves any video, not just assemblies.

One caveat learned from the first published session, before you plan anything:
on a channel without an existing audience the episodes are effectively
invisible — the best of them earned **ten impressions** — while a single Short
earned 1,325 views from the Shorts feed. Plan and publish accordingly.
`reference/distribution.md` has the measurements.

## Non-negotiables

0. **Never publish a video without a real title and a real thumbnail.**
   `publishgate.py` runs before every upload and its refusal is final — there
   is no override and no "ship it now, fix it later". A generic fallback
   title, a title another video already carries, a missing thumbnail, or a
   thumbnail whose text does not survive the crop the platform actually
   serves are each a hard stop. Speed is never a reason to waive this: an
   unpublished moment costs one video, a channel page of identical generic
   titles costs the channel.

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
8. **Resume is content-based, not hope-based.** Re-runs skip cached stages only
   when their input hashes, settings and toolchain fingerprint still match.
9. **A rendered queue is a schedule, not a batch.** Shorts go out one at a
   time, spaced by hours. Publishing a session's whole Shorts queue in an
   afternoon means one of them gets tested and the rest are ignored — measured,
   not theorised. See `reference/distribution.md`.
10. **A Short's length is set by the moment, within a 60–120s band.** The
    platform ceiling is 180s (`config.SHORTS_HARD_MAX`). The floor matters as
    much: the first session shipped a median Short of **44 seconds** because
    `min_len` was 20s and acoustic moments simply come out that long, so
    almost every Short was a fragment of a row rather than the row. Hand-cut
    extras added outside `plan.py` still bypass `max_count` and the length
    band, because nothing reads `project.json` on that path.
11. **Diagnose with impressions before touching packaging.** Near-zero
    impressions at a healthy CTR is a distribution problem; rewriting the title
    and re-cutting the thumbnail cannot fix it and burns a hard daily quota.
12. **On a live source, the first video ships within 15 minutes.** The audience
    for a sitting arrives while it is still sitting. Nothing that merely
    *improves* a video may block the first one — transcription, quote mining
    and title polish run after publishing and are applied in place. The
    opening cycle publishes a Short, not an episode. Measured once at **2h
    33m**, of which 39 min was transcription that could have run later and 84
    min was finished videos sitting on disk with no uploader alive. See
    `reference/live-sessions.md`.
13. **A title should be what someone actually said.** Prefer the words
    themselves, and prefer the moment they were said with force, over a
    description of the footage. A viewer searches for the claim, not for
    "Assembly Session Highlights".
14. **One Short is one moment.** Never split a highlight into "Part 1 / Part
    2" — a viewer in a scrolling feed will not go and find the rest. If the
    moment outruns the Shorts ceiling, cut the strongest self-contained
    section and link to the long-form for the remainder.
15. **The footage fills the vertical frame.** No blurred, mirrored or
    duplicated backdrop standing in for picture. See `reference/shorts.md`.
16. **A Short is packaged like its episode.** Same thumbnail text style, same
    story. Two styles for one story looks like two unrelated uploads.
17. **Confirm the rendered file, not the setting.** A stale title card and
    thumbnail text sitting across a subject's face both shipped while the
    configuration looked correct. Look at the output.
18. **The thumbnail frame is chosen, not assumed.** Never the midpoint, and
    never a frame from the built episode — its opening seconds are branding.
    Scout the raw footage for a large, sharp, well-exposed face
    (`head-of-marketing/scripts/thumbframe.py`). A batch shipped with the
    episode's own intro card as its thumbnail, which also pushed the headline
    to mid-picture, because a frame with no face has nothing to position
    against.
19. **A Short's thumbnail is checked cropped to 9:16, by looking at it.**
    Portrait surfaces keep only the centre 405 of 1280 pixels. 43 of 43
    Shorts in one session served `மானியக் கோரிக்கை` as `ரிக்கை` above an
    empty red band. Set `portrait_safe` and open the cropped file — a pixel
    metric passed 42 of those 43, because a fragment of a word is still ink.
    See `head-of-marketing/reference/thumbnails.md`.

## Start here: is it live?

**Always answer this first.** A live sitting and a finished recording are the
same footage and a different job, and both mistakes cost real work — treat a
live stream as a recording and the session ends before anything is published;
treat a recording as live and the loop waits for a stream that already ended.

```bash
python3 <skill>/scripts/source_state.py <project> [--url URL]
```

| Result | What it means | Do this |
|---|---|---|
| `live` | Still broadcasting | **`live.py`** — cut and upload as it runs, keep following until it ends |
| `recorded` | Finished | **`pipeline.py`** — one pass, no tracking |
| `upcoming` | Scheduled, not started | Nothing to cut yet |
| `none` | No URL given and the channel has no live stream | Tell the user **"no live session yet"** — do not invent work |

With no URL supplied, the configured channel is checked for a live broadcast,
so "find whatever is on now" is a valid way to invoke this.

`reference/live-sessions.md` has the loop, the flags and the reasoning.

## Quick start

```bash
mkdir -p myproject && cd myproject
cp <skill>/examples/project.json .        # edit source.url and channel
cp <skill>/examples/shortlist.json meta/ # who is worth publishing (see below)
python3 <skill>/scripts/source_state.py . # live or recorded?

# recorded:
python3 <skill>/scripts/pipeline.py .     # ingest → analyse → plan → cut → build

# live:
python3 <skill>/scripts/live.py . --marketing ./scripts/publish_one.py
```

`--marketing` takes **a per-item adapter you supply**: a script called as
`<script> <project> --only <id>` that packages and uploads that one item and
exits non-zero if it did not. There is no ready-made script for this in
`head-of-marketing` — its tools (`metadata.py`, `brand.py`, `thumb_doc.py`)
are per-project stages, not a per-item pipeline. Without `--marketing`, items
are cut and rendered but nothing is uploaded, which is the safe default.

Then package and upload each result with the `head-of-marketing` skill.

## Pipeline

| Stage | Script | What it does |
|---|---|---|
| state | `source_state.py` | **First.** Live, recorded, upcoming or nothing on air. |
| live | `live.py` | Live sources only. Follows the stream, publishing as it runs. |
| ingest | `ingest.py` | Probes the source; pulls audio and a small scan video. Never downloads the full session. |
| analyse | `analyse.py` | Streams per-second acoustic features; scores highlight windows; flags clashes. |
| vip | `faces.py` | Optional. Finds a configured public figure on camera. |
| plan | `plan.py` | Decides episode and Short counts, assigns moments, applies clash and VIP priority. |
| cut | `cut.py` | Fetches each segment at full resolution, snapped to speech boundaries. |
| build | `build.py` | Assembles intro → clips with lower-thirds → outro, loudness-normalised. |
| shorts | `shorts.py` | Renders 9:16 verticals with a burned hook and a CTA back to the episode. |
| package | → `head-of-marketing` | Titles, thumbnails, descriptions, tags. |
| gate | `publishgate.py` | Refuses any item whose title or thumbnail is not fit to publish. Runs before every upload. |

Each stage reads only what earlier stages wrote to `meta/`. Pipeline re-runs
skip unchanged stages; force a boundary by using `--from plan`, or run one with
`--only cut`.

## Reference

Load only what the task needs.

- **`reference/project-config.md`** — every `project.json` field.
- **`reference/live-sessions.md`** — live vs recorded, the tracking loop, the
  live edge margin, and why speed and search matter more on a live source.
  **Read this before touching a live URL.**
- **`reference/highlight-detection.md`** — how moments are scored, and why the
  thresholds are relative to each session rather than absolute.
- **`reference/clash-detection.md`** — how fights are found acoustically, the
  calibration that made it work, and the confirmation rule.
- **`reference/cutting.md`** — the desync trap, boundary snapping, sync
  verification.
- **`reference/vip-packaging.md`** — detecting a public figure and pivoting the
  episode around them.
- **`reference/shorts.md`** — vertical framing, hooks, and routing to long-form.
- **`reference/distribution.md`** — what the first fourteen videos actually did,
  measured: why long-form gets ~10 impressions on a cold channel, why Shorts
  are the only mechanism that pays out, and the publishing cadence that
  follows. **Read this before optimising any packaging.**
- **`reference/publishing-limits.md`** — the daily custom-thumbnail cap, what
  spends it, and how to verify a write actually went live.
- **`reference/packaging.md`** — the handoff to `head-of-marketing`, including the
  Politainment channel setup.
- **`reference/editorial-ethics.md`** — covering a legislature without
  fabricating drama.
- **`reference/resume-and-safety.md`** — content-hash resume, pre-flight
  doctor checks, failures and artifact-bound overwrite approvals.

## Requirements

`yt-dlp`, `ffmpeg` (with `overlay`; `drawtext` is not required), `numpy`,
`Pillow`. VIP detection additionally needs `insightface` and `onnxruntime`.
Text is rendered through CoreText, so **rendering is macOS-only**; analysis,
planning and cutting are portable.
