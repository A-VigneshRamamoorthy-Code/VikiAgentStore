# Highlight detection and how many videos to make

## The scoring

`analyse.py` streams the session's audio at 16 kHz mono in 120-second chunks
and reduces it to **one feature row per second**. A full session as float32 is
over a gigabyte, so it is never held in memory at once.

Per second:

| Feature | What it captures |
|---|---|
| `db` | Loudness |
| `peak_db` | Peaks — shouting, gavel strikes |
| `min_db` | The **noise floor**: does the room ever fall quiet? |
| `flat` | Spectral flatness — overlapping voices push it toward noise |
| `flux` | Positive spectral flux — onset density |

Sliding windows are then scored for energy, continuity, flatness and onsets,
combined into a single `highlight` score, and the top windows are emitted as
candidates.

Measured distributions on a real session, for calibration context:

- `flat`: p10 0.0036, p50 0.0138, p90 0.037, max 1.0 — very skewed
- `db`: p10 −45.7, p50 −35.9, max −22.9 (a `min` of −180 is digital silence)

## Everything is relative to this session

`plan.py` selects publishable moments with `select_strong()`, which takes
clashes unconditionally and everything else against a bar derived from **this
session's own score distribution** (`longform.keep_fraction`, default 0.45).

The reason is the same one described in `clash-detection.md`. On a quiet day
every moment scores well relative to nothing happening; an absolute bar would
therefore pass the entire session and inflate a procedural sitting into five
episodes of filler. Observed on real data: an absolute floor passed **40 of 40**
candidates; the relative bar passed **19**, yielding three episodes with the
clash leading the first.

## How the counts are derived

```
moments  → merge overlapping windows       (one flashpoint ≠ four clips)
         → rank: clashes first, then score
         → select_strong()                 (relative bar; clashes exempt)
         → ceil(strong / max_clips) episodes, capped by longform.max_episodes
```

Then:

- Moments are dealt **round-robin** across episodes, so episode 3 is not the
  leftovers. Every episode needs a hook of its own.
- Within an episode, clips are re-sorted **chronologically** — a session tells
  its story in order.
- An episode below `longform.min_clips` is **dropped** unless it contains a
  clash. Its moments remain available as Shorts. Padding an episode to reach a
  count is the failure mode this exists to prevent.

## Merging overlaps

The scorer slides a window, so a single flashpoint routinely produces three or
four overlapping candidates. `merge_overlaps()` collapses anything within 8
seconds into one segment, keeping the higher score and the union of the bounds,
and preserving a `clash` label if either side had one. Without this the viewer
sees the same argument three times.

## Clip lengths

`clamp_clip()` fits each moment to a publishable length:

- Shorter than `min_clip` → grown symmetrically.
- Longer than `max_clip` → **truncated from the end**, keeping the front,
  because the flashpoint is at the onset, not the tail.

These are only targets. `cut.py` then snaps both ends to real speech
boundaries, so final clips vary — 36 to 58 seconds is typical against a 45
second target.

## Improving the labels

Acoustics tell you *where* something happened, never *what*. To get real
labels, transcribe the shortlisted candidates only — not the whole session —
and write `meta/labels.json`:

```json
[{"start": 2485, "end": 2530,
  "label": "native-language label",
  "gloss": "English gloss"}]
```

`plan.py` attaches these to clips and Shorts, and they become the lower-thirds
and chapter titles. Without them the lower-thirds are blank.
