# Packaging and the handoff to head-of-marketing

This skill produces **rendered videos**. It does not write titles, thumbnails or
descriptions — that is the `head-of-marketing` skill's job, so the same packaging
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
Y=../../head-of-marketing/scripts
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

Everything else about uploading is in `head-of-marketing/reference/upload.md`.

## Publishing order

1. Long-form episodes first, left **private**.
2. Review each one — especially any clash claim.
3. Publish the long-form.
4. Publish the Shorts, whose CTAs point at videos that are now live —
   **one at a time, spaced by hours**, not as a batch. This is the single
   highest-leverage rule in the whole pipeline; the evidence is in
   `reference/distribution.md`.

Never publish a Short before its parent episode.

## Thumbnails cost quota

Custom thumbnails are capped at roughly **17 applications per rolling 24
hours**, and a thumbnail attached during the upload wizard spends the same
allowance as one changed afterwards. Publishing nine videos with thumbnails
therefore leaves little room for corrections, and a failed correction leaves
the wrong image live for a day.

Get the thumbnail right *before* upload, and proofread any burned-in text at
full size first — a single wrong word is nearly invisible to an automated
image diff. Details and the verification method are in
`reference/publishing-limits.md`.

## Text never sits over a face

Burned-in thumbnail text goes **above or below** the subject, never across
them. A face covered by a caption loses the one thing that makes a political
thumbnail work: the viewer recognising who is speaking before they read
anything. This shipped once — the headline landed across the speaker's eyes
and nose — and the quota rule above is what made it expensive, because the
correction could not simply be re-uploaded.

Practically, that means the layout has to be chosen *from the frame*, not
fixed in advance:

1. Detect the largest face in the candidate still (`faces.py` already does
   this for VIP matching).
2. Put the text block in whichever horizontal band — above or below — has more
   clear pixels between the face box and the frame edge.
3. If neither band fits the text at a readable size, pick a different still.
   Shrinking the type until it fits is the wrong trade: unreadable text at
   thumbnail scale is the same as no text.

The same layout then applies to the Short, per non-negotiable #16.

Retrofitting existing thumbnails is governed by the quota, so treat a
back-catalogue fix as a scheduled job of ~17 per day, newest first, rather
than a single sweep.
