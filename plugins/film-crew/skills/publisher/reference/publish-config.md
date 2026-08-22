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
  "language": {"primary": "en", "secondary": ""},
  "profile": ".chrome-profile",
  "shorts": {"comment": "Full film: {film_url}"}
}
```

| Field | Notes |
|---|---|
| `channel.handle` | Compared **exactly** against the active Studio channel. Leave empty to disable the check (not recommended). |
| `channel.channel_id` | Written by `channels`/`switch` into `meta/channel.json`; every Studio URL is built from it so a stage can never act on a decoy channel. |
| `brand.*` | Colours are RGB triples, used by the stings, the thumbnails, the Shorts surround and the channel art. |
| `metadata` | The uploader reads this path and nothing else. Changing it means changing what `metadata.py` writes too. |
| `privacy` | Keep `private`. `upload` always leaves the video private; going public is the separate `publish` stage, after `verify`. |
| `category_id` | `25` is News & Politics, `27` Education, `22` People & Blogs. |
| `profile` | Signed-in Chrome profile. **Relative paths resolve inside the project**; give several projects the same absolute path to share one sign-in (a profile is ~700 MB, and re-authenticating per film is pure friction). Only one process may hold a profile at a time. |
| `shorts.comment` | Optional. The comment `promote` posts on each Short; `{film_url}` is substituted. Defaults to a "Full film — …" line. |

### The profile path trap

`profile` is resolved by `Publish.profile`, **not** by reading the raw JSON
string. A helper script that takes `json.load(open("publish.json"))["profile"]`
literally and runs from a different working directory will silently create a
brand-new empty profile there and land on the Google sign-in page — which looks
exactly like "the session expired". Always go through `Publish`.

Derived paths: the profile directory holds the signed-in browser session,
`assets/` receives the rendered stings, `meta/` holds every spec and result.

## Files the stages generate

| File | Written by | Holds |
|---|---|---|
| `meta/channel.json` | `channels`, `switch` | handle, name and channel id of the confirmed channel |
| `meta/youtube_metadata.json` | `metadata.py` | the only metadata the uploader reads |
| `meta/upload_result.json` | `upload` | the live link; `shorts`/`promote`/`thumbnail` resolve `auto` from it |
| `meta/shorts_result.json` | `shorts`, `promote` | per-Short video id, link, and whether the comment and pin succeeded |

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
  "sources_heading": "Sources",
  "sources": [{"name": "…", "url": "https://…"}],
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
- **A single rendered film has no per-clip files.** Use explicit timestamps
  instead — `{"at": 1.6, "label": "…"}`, accepting seconds or `"1:33"` /
  `"1:33.4"`. The first chapter is forced to `0:00`, and the list is checked
  against the film's real duration and YouTube's silent rules: at least three
  chapters, each at least 10 seconds, and the last not inside the final 10
  seconds. A chapter list that breaks any of these is simply not rendered by
  YouTube, with no error anywhere.
- Timestamps must be measured on the **final** file. If the renderer trims
  silence per clip, the raw narration durations do not sum to the runtime — on
  one 12-minute film the difference was 17 seconds, enough to put every chapter
  in the wrong place.
- `source` is a single credit; `sources` is a list, which is what a factual or
  sensitive film needs. Both may be present. Label each one for what the link
  actually is — a third-party case summary is not "the Court's judgment".
- `title_tails` are appended only while the title stays within 100 characters,
  in order. Put the most valuable one first.
- `tags.primary` is consumed first when fitting the 500-character budget;
  `extra` is what gets dropped.
- Omit `intro_file` if the video has no intro — chapter one then starts at 0:00.

## `meta/thumbnail.json`

Two renderers read this file. **Which one runs is decided by which script you
invoke**, not by the file — `style: "doc"` is a marker for the reader, not a
switch. See `thumbnails.md` for how to choose.

**`thumbnail.py`** — news-debate style (red band, `VS` burst):

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

**`thumb_doc.py`** — documentary style, drawn from the paper style artwork
rather than from video stills:

```json
{
  "style": "doc",
  "headline": ["SIXTY", "HOURS"],
  "kicker": "MUMBAI · 26 NOV 2008",
  "kicker_size": 36,
  "stamp": "CASE FILE",
  "subject": {"fn": "grand_hotel", "w": 660, "h": 380, "x": 600, "y": 320},
  "smoke": {"w": 480, "h": 560, "density": 0.8, "x": 830, "y": -30},
  "seed": 7,
  "top": 168,
  "headline_width": 510,
  "tape": [[-30, 44, 240, 62]]
}
```

- `subject.fn` names any function in paper style's `illustrations.py`
  (`grand_hotel`, `mumbai_map`, `figure`, `boat`, …), so a different film
  repoints it without touching the renderer. An unknown name is a hard error.
- `headline_width` and `subject.x` are the two knobs that matter: if the text
  would run into the illustration the renderer **refuses**, because that
  collision is invisible at preview size and fatal at 168px.
- Text below a 96px cap height is likewise refused — at the 7.6x reduction to a
  168px search result that floor lands at about 12px on screen.
- JPEG quality steps down only as far as the 2 MB cap requires.

## `meta/shorts_spec.json`

Input to `shorts.py` — what to cut, from the finished film.

```json
{
  "shorts": [
    {"id": "s1", "start": 8.1, "end": 40.0,
     "hook": "A business school\nstill teaches\nthis question",
     "cta": "FULL FILM IN DESCRIPTION"}
  ]
}
```

- `start`/`end` are seconds into the rendered film. `hook` uses real newlines;
  it is baked into a PNG surround, not drawn by ffmpeg.
- Any entry of 60 seconds or more **fails the whole batch before rendering**.
  A long vertical file uploads as an ordinary video, and discovering that after
  rendering and uploading is a far more expensive mistake.
- `python3 shorts.py <project> --only s2` re-renders one entry.

## `meta/shorts_publish.json`

Input to the `shorts` and `promote` stages — how to publish what was cut.

```json
{
  "privacy": "public",
  "related_video": "auto",
  "shorts": [
    {"id": "s1", "file": "out/short_s1.mp4",
     "title": "… #shorts",
     "description": "hook first …\n\nFull film — …:\n{film_url}\n\n#Mumbai",
     "tags": ["26/11", "Mumbai"]}
  ]
}
```

- `related_video: "auto"` resolves the film from `meta/upload_result.json`.
- `{film_url}` is substituted into every description. Put it on its own
  labelled line — it is the link that survives every feature gate.
- `id` and `file` must match the `shorts_spec.json` entries.

