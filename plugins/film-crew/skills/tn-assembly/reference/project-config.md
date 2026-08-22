# project.json reference

Everything the pipeline needs, in one file at the project root. Nothing in this
skill hardcodes a URL, a channel or a person's name.

Every setting and its default live in `DEFAULTS` in `scripts/config.py` — one
source of truth, so a setting cannot exist without a documented default and a
known type. Check a project before spending time on it:

```bash
python3 scripts/pipeline.py <project> --doctor
```

That reports three different things:

- **missing tools** — `ffmpeg`, `yt-dlp`, `PIL`, and so on
- **wrong types** — `"fps": "sixty"` would otherwise reach ffmpeg as a filter
  argument and fail minutes into a render; ranges are checked too
  (`shorts.min_len` above `shorts.max_len`, a landscape frame in `video`)
- **dead keys** — a misspelled `"short"` section is not an error, it is
  *ignored*, so the setting someone believed they had changed never applies.
  `--doctor` lists any key nothing reads.

It exits non-zero on the first two.

```json
{
  "source": {
    "url": "https://www.youtube.com/watch?v=...",
    "session_date": "2026-01-15",
    "format": "137+140",
    "duration": 0,
    "note": ""
  },
  "channel": {"handle": "politainment", "name": "Politainment"},
  "brand": {
    "name": "POLITAINMENT",
    "crimson": [206, 22, 30],
    "gold": [255, 205, 60],
    "ink": [8, 10, 18],
    "paper": [247, 245, 240]
  },
  "language": {"primary": "ta", "secondary": "en"},
  "audio": {"noise_db": -38, "min_silence": 0.30},
  "vip": {
    "enabled": false,
    "name": "", "name_local": "", "honorific": "",
    "ref_images": [],
    "match_threshold": 0.45, "review_threshold": 0.38,
    "step": 3.0, "min_face": 42
  },
  "video": {"width": 1920, "height": 1080, "fps": 30},
  "shorts": {
    "width": 1080, "height": 1920, "fps": 30,
    "min_len": 20, "max_len": 58, "max_count": 6,
    "cta": "Full video on the channel"
  },
  "longform": {
    "min_clip": 34, "max_clip": 95,
    "min_clips": 4, "max_clips": 8,
    "max_episodes": 6,
    "keep_fraction": 0.45,
    "min_highlight": 0.55,
    "target_runtime": 480
  },
  "publish": {"privacy": "private", "category_id": "25",
              "made_for_kids": false}
}
```

## source

| Field | Notes |
|---|---|
| `url` | The only required field. |
| `format` | yt-dlp format. `137+140` is 1080p + m4a. Use `299+140` for 1080p60. |
| `duration` | Filled by `ingest.py`; used for scan progress reporting. |

## audio

Tuning for boundary snapping. `noise_db` **−38 dB** suits a chamber floor near
−24 dB mean. Raise it toward −30 for a quiet source, lower it for a hot one.
See `cutting.md`.

## longform

The fields that actually change the output:

| Field | Effect |
|---|---|
| `keep_fraction` | **The main dial.** Fraction of non-clash candidates treated as publishable. Lower = fewer, stronger videos. |
| `max_episodes` | Hard cap regardless of how much was found. |
| `min_clips` | Episodes below this are dropped unless they contain a clash. |
| `min_clip` / `max_clip` | Target clip length before boundary snapping. |
| `min_highlight` | Absolute floor, applied *in addition to* the relative bar. Rarely binding. |

`max_clips` also determines how many episodes are created:
`ceil(strong_moments / max_clips)`.

## shorts

`max_count` caps how many Shorts are planned. `cta` is the default text burned
over the last seconds; a per-Short `cta` in the plan overrides it.

## vip

Off by default. See `vip-packaging.md`. `ref_images` paths are relative to the
project root.

## Project layout

```
myproject/
├── project.json
├── src/           audio.m4a, scan_360p.mp4    (ingest)
├── meta/          features, candidates, plan, labels, vip_hits, stage_cache, failures
├── clips/         cut source segments, per episode
├── work/          intermediates (safe to delete)
├── assets/        intro.mp4, outro.mp4        (head-of-marketing/stings.py)
├── out/           rendered episodes and shorts
└── publish/<id>/  one publish project per video (see packaging.md)
```

`src/` and `work/` are large and reproducible — delete them freely. `meta/` is
small and is the record of every decision, so keep it.
