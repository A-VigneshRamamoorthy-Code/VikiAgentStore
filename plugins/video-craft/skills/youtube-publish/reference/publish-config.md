# publish.json and the spec files

## `publish.json`

Lives at the root of a publish project. Everything channel- and brand-specific.

```json
{
  "channel": {
    "handle": "politainment",
    "name": "Politainment",
    "channel_id": ""
  },
  "brand": {
    "wordmark": "POLITAINMENT",
    "tagline": "",
    "crimson": [206, 22, 30],
    "gold": [255, 205, 60],
    "ink": [8, 10, 18],
    "paper": [247, 245, 240],
    "subscribe_label": "SUBSCRIBE",
    "subscribed_label": "SUBSCRIBED"
  },
  "video": "out/episode_1080p.mp4",
  "thumbnail": "out/thumbnail.jpg",
  "metadata": "meta/youtube_metadata.json",
  "privacy": "private",
  "category_id": "25",
  "made_for_kids": false,
  "language": {"primary": "en", "secondary": ""}
}
```

| Field | Notes |
|---|---|
| `channel.handle` | Compared **exactly** against the active Studio channel. Leave empty to disable the check (not recommended). |
| `brand.*` | Colours are RGB triples, used by the stings and the thumbnail. |
| `metadata` | The uploader reads this path and nothing else. Changing it means changing what `metadata.py` writes too. |
| `privacy` | Keep `private`. Publishing is a human decision. |
| `category_id` | `25` is News & Politics. |

Derived paths: `.chrome-profile/` holds the signed-in browser session,
`assets/` receives the rendered stings.

## `meta/metadata_spec.json`

Input to `metadata.py`. Everything editorial.

```json
{
  "hook": "the reason to click, in the spoken language",
  "title_tails": ["Topic In English", "Place / Session"],
  "lead": "one or two lines; repeats the title's keywords",
  "chapters_heading": "நேரக்குறிப்பு | Chapters",
  "intro_file": "clips/intro_n.mp4",
  "intro_label": "தொடக்கம் | Intro",
  "chapters": [
    {"label": "native label", "gloss": "English gloss",
     "file": "clips/ep01/seg_01.mp4"}
  ],
  "summary_heading": "In English",
  "summary_secondary": "a real paragraph, not keyword soup",
  "topics": ["Assembly", "Budget"],
  "source": {"name": "Official webcast", "url": "https://..."},
  "cta": "closing line",
  "tags": {"primary": [], "secondary": [], "extra": []},
  "hashtags": ["TNAssembly"],
  "category_id": "25",
  "privacy": "private"
}
```

Notes:

- `chapters[].file` must point at the **rendered** segment. Offsets are probed
  from the files, so the timestamps cannot drift out of step with the edit.
- `title_tails` are appended only while the title stays within 100 characters,
  in order. Put the most valuable one first.
- `tags.primary` is consumed first when fitting the 500-character budget;
  `extra` is what gets dropped.
- Omit `intro_file` if the video has no intro — chapter one then starts at 0:00.

## `meta/thumbnail.json`

Input to `thumbnail.py`. See `thumbnails.md` for the layout.

```json
{
  "bg": "meta/frames/left.jpg",
  "bg_right": "meta/frames/right.jpg",
  "line1": "first line",
  "line2": "second line",
  "kicker": "small label",
  "vs": true,
  "badge": "",
  "out": "out/thumbnail.jpg"
}
```

`badge` defaults to `brand.wordmark`. `bg_right` is optional; omitting it gives
a single full-width still with no `VS` burst.
