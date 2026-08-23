---
name: tn-assembly
description: >
  Turns long legislative webcasts into publishable episodes and Shorts:
  detects highlights and clashes, chooses episode count, cuts on speech
  boundaries, preserves resolution and flags VIP appearances. SEO/upload go
  to head-of-marketing. Use for assembly, parliament or council sessions
  and long proceedings. Part of film-crew, normally dispatched by the
  director skill.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "1.1.0"
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
10. **A Short's length is set by the moment, not by a target.** The only hard
    limit is YouTube's 180s Shorts ceiling (`config.SHORTS_HARD_MAX`); within
    it, let the exchange run as long as it needs. Hand-cut extras added outside
    `plan.py` still bypass `max_count` and the length band, because nothing
    reads `project.json` on that path.
11. **Diagnose with impressions before touching packaging.** Near-zero
    impressions at a healthy CTR is a distribution problem; rewriting the title
    and re-cutting the thumbnail cannot fix it and burns a hard daily quota.

## Quick start

```bash
mkdir -p myproject && cd myproject
cp <skill>/examples/project.json .        # edit source.url and channel
python3 <skill>/scripts/pipeline.py .     # ingest → analyse → plan → cut → build
```

Then package and upload each result with the `head-of-marketing` skill.

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
| package | → `head-of-marketing` | Titles, thumbnails, descriptions, tags. |

Each stage reads only what earlier stages wrote to `meta/`. Pipeline re-runs
skip unchanged stages; force a boundary by using `--from plan`, or run one with
`--only cut`.

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
