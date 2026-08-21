# Packaging and the handoff to youtube-publish

This skill produces **rendered videos**. It does not write titles, thumbnails or
descriptions — that is the `youtube-publish` skill's job, so the same packaging
logic serves any video.

## The handoff

For each rendered episode or Short, create a publish project:

```
<project>/publish/<id>/
├── publish.json                  ← channel + brand (copy per episode)
├── meta/metadata_spec.json       ← the editorial content
├── meta/thumbnail.json           ← thumbnail layout
├── out/episode_1080p.mp4         ← or a symlink to the render
└── out/thumbnail.jpg
```

Then:

```bash
Y=../../youtube-publish/scripts
python3 $Y/metadata.py  <project>/publish/ep01
python3 $Y/seocheck.py  <project>/publish/ep01
python3 $Y/thumbnail.py <project>/publish/ep01
python3 $Y/upload.py recon  <project>/publish/ep01
python3 $Y/upload.py upload <project>/publish/ep01
```

`pipeline.py --only package` runs the metadata and lint steps for every episode
that already has a `metadata_spec.json`.

## What this skill supplies

From `meta/plan.json`, each item carries what packaging needs:

| Field | Use |
|---|---|
| `theme` | `clash` or `digest` — decides the hook formula |
| `vip` | If true, package around the person (`vip-packaging.md`) |
| `clips[].label` / `.gloss` | Chapter titles, bilingual |
| `clips[].file` | Chapter offsets are probed from these |
| `shorts[].parent` | The episode a Short must link back to |
| `render` | The finished file to upload |

## Writing metadata_spec.json for an assembly episode

```json
{
  "hook": "<the moment, in the spoken language>",
  "title_tails": ["TN Assembly Highlights", "Tamil Nadu Assembly 2026"],
  "lead": "<1–2 lines repeating the title keywords, both languages>",
  "chapters_heading": "நேரக்குறிப்பு | Chapters",
  "intro_file": "clips/intro_n.mp4",
  "chapters": [{"label": "…", "gloss": "…", "file": "…"}],
  "summary_heading": "In English",
  "summary_secondary": "<a real paragraph for English search>",
  "source": {"name": "TN Legislative Assembly official webcast", "url": "…"},
  "tags": {"primary": ["<native terms>"], "secondary": ["<English terms>"]}
}
```

Fill `label` and `gloss` from `meta/labels.json` (see
`highlight-detection.md`). Without labels the chapters and lower-thirds are
blank, which is the most common reason an episode looks unfinished.

## Channel setup: Politainment

The channel this skill was built for. Put this in each `publish.json`:

```json
{
  "channel": {"handle": "politainment", "name": "Politainment"},
  "brand": {
    "wordmark": "POLITAINMENT",
    "crimson": [206, 22, 30],
    "gold": [255, 205, 60],
    "ink": [8, 10, 18],
    "paper": [247, 245, 240]
  },
  "privacy": "private",
  "category_id": "25",
  "language": {"primary": "ta", "secondary": "en"}
}
```

Two things to know before uploading to it:

- **The login owns several lookalike channels** (`Politainment Re-defined`,
  `Politainment Gamer`). The handle is matched exactly and the upload is refused
  otherwise. Run `upload.py recon` first and read the reported channel name.
- **Category 25** is News & Politics.

Everything else about uploading is in `youtube-publish/reference/upload.md`.

## Publishing order

1. Long-form episodes first, left **private**.
2. Review each one — especially any clash claim.
3. Publish the long-form.
4. Publish the Shorts, whose CTAs point at videos that are now live.

Never publish a Short before its parent episode.
