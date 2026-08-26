---
name: style-stock
description: >
  Real stock-footage visual style for production-designer: searches Pexels beat
  by beat, falls back to Pixabay when configured, downloads and credits each
  clip, grades the cut to one palette and renders it to narration. Use for
  real-world, live-action, documentary, news-adjacent, travel, corporate,
  true-crime and reportage subjects — anything where real photography beats
  illustration. Requires PEXELS_API_KEY.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "1.0.0"
---

# Stock style

A live-action stock-footage cut. The compiler turns a beat plan into a shot
list of footage queries; the fetcher searches and downloads clips; the renderer
normalises, grades, captions, scores and mixes them into one film.

This is the `stock` style of the `production-designer` skill. It is for stories
where photography is the point: real places, cities, work, travel, business,
sport, nature, lifestyle, true-crime atmosphere, reportage and documentary
B-roll.

Do not choose it for fantasy, talking characters, scenes that must show a
specific named person, precise invented objects, exact historical events,
screen recordings or claims where the wrong building would be a lie. This style
never invents footage. A beat that cannot be found becomes a labelled `NO
FOOTAGE` placeholder and the stage exits non-zero.

---

## Required key

`fetch.py` requires a Pexels API key unless you are doing `--dry-run`.

Put it in the repository's gitignored `.env` file, never in the skill, the
storyboard or a committed script:

```bash
cd <repo>
echo 'PEXELS_API_KEY=...' >> .env
```

`.env` and `.env.*` are gitignored in this repository. `fetch.py` walks upward
from the working directory and reads `.env` without overwriting real environment
variables.

There is no scraping path. `pexels.com/api/v3/search/videos` returns 401, the
search HTML contains no `.mp4` URLs and no `__NEXT_DATA__`, and `robots.txt`
disallows `*q=*`, `*/api/v*` and `*/download/*` and blocks ClaudeBot/GPTBot by
name. Use the API key.

Pixabay fallback is optional and uses `PIXABAY_API_KEY`; Pexels is still the
required key declared in `style.json`.

---

## Make one

Run the stages separately. That separation is a design rule: compile is
offline, cheap and repeatable; fetch is metered, non-deterministic and where
the licence is established; render is expensive. It lets you re-cut the board
against footage already on disk without burning API quota.

```bash
S=plugins/film-crew/skills/style-stock
cd <repo>

python3 $S/scripts/compile.py beat-plan.json --check
python3 $S/scripts/compile.py beat-plan.json --motion-plan motion-plan.json -o storyboard.json
python3 $S/scripts/fetch.py storyboard.json
python3 $S/scripts/render.py storyboard.json --sheet
python3 $S/scripts/render.py storyboard.json -o film.mp4
```

Generate or replace the bed explicitly when you want to hear it before render:

```bash
python3 $S/scripts/score.py --mood tension --duration 117.1 -o bed.wav
python3 $S/scripts/render.py storyboard.json --bed bed.wav -o film.mp4
```

The registry uses these entrypoints from `style.json`:

| entrypoint | argv shape |
|---|---|
| `compile` | `python3 {style}/scripts/compile.py {beat_plan} -o {storyboard}` |
| `compile_directed` | `python3 {style}/scripts/compile.py {beat_plan} --motion-plan {motion_plan} -o {storyboard}` |
| `check` | `python3 {style}/scripts/compile.py {beat_plan} --check` |
| `fetch` | `python3 {style}/scripts/fetch.py {storyboard}` |
| `preview` | `python3 {style}/scripts/render.py {storyboard} --sheet` |
| `render` | `python3 {style}/scripts/render.py {storyboard}` |

The manifest also declares `motion_plan: 1`, aliases `footage`, `b-roll`,
`broll`, `pexels`, `live-action`, `cinematic`, and requires `ffmpeg`,
`ffprobe`, Pillow (`PIL`) and `PEXELS_API_KEY`.

---

## How it fits the crew

- `storyboard-artist` supplies the style-neutral `beat-plan.json`.
- `animation-director` may supply `motion-plan.json`; `compile_directed` passes
  it to `compile.py --motion-plan`.
- `voice-booth` supplies narration audio paths in the beat plan. Without them,
  the renderer can still make a silent picture for visual checks.
- `score.py` supplies the simple stock-style bed. `sound-designer` still owns
  the final mix decisions.
- `fetch.py` writes `assets.json` and `credits` from the resolved shots.
  `rights-manager` consumes that ledger.
- `tn-assembly` owns titles and packaging after the film exists.

---

## What compile emits

`compile.py` reads beat-plan schema `1` and emits storyboard schema `1`. Each
beat becomes a shot with `id`, `beat`, `at`, `dur`, `intent`, `subject`,
`query`, `alternates`, `move`, `move_amount`, `speed`, `grade` and optional
`keyword`. The first shot is forced to start at `0.0`; durations are derived
from the next shot so there are no black gaps.

A beat with `assets: []` holds the previous shot instead of cutting. If it is
the first beat, that is blocking because the film would open on nothing.

Shot lengths are reported when they fall outside the working band:

- under `1.2s` reads as a flash;
- over `5.0s` a stock clip has run out of things to show. This is the rule
  ColdFusion states for its own films, and rather than only warning, the
  compiler cuts away to one of the beat's alternate queries — a second angle
  on the same subject, never the same clip twice. A beat with no alternate is
  reported instead. `--no-cutaways` turns the splitting off.

A beat whose query reduces to abstractions runs on **atmosphere** — weather,
traffic, defocused light chosen to match the mood — rather than stopping the
film with a placeholder. Those shots are flagged `"atmosphere": true` and
raise a note, so it stays obvious which pictures are evidence and which are
mood. See [`reference/documentary-rhythm.md`](reference/documentary-rhythm.md).

Adjacent identical queries warn because they can make the cut look like a
dropped frame. Clip deduplication in `fetch.py` is global, so one clip cannot
answer two beats.

### Query fallback chain

`query_from()` asks in this order:

1. `assets[].hint`, because the boarder wrote it as a search query;
2. subject nouns, after removing stop words;
3. progressively shorter widenings;
4. nouns from the narration line.

`searchable()` refuses queries that reduce to abstractions. Searching
`moment`, `story` or `silence` returns confident irrelevant stock, which is
worse than no result. Rewrite the beat to name a thing a camera could point at,
or give it a better `assets[].hint`.

### Grade and mood are chosen from the story

The grade and music mood are scored from the story's own words, on distinct word
matches so one repeated word cannot carry the vote. The heist demo correctly
chooses `noir` and `tension`.

Grades:

| grade | reads as |
|---|---|
| `clinical` | neutral, bright, high-key product film |
| `ember` | warm highlights, amber midtones, lifted blacks |
| `faded` | lifted blacks, low saturation, memory |
| `noir` | cool, desaturated, milky blacks — film noir, not darkness |
| `oceanic` | cyan highlights, deep blue shadows, cool and wide |
| `reportage` | cool, desaturated, lifted blacks — the tech-documentary look |
| `verdant` | deep greens, cool shadows, natural saturation |

Moods:

| mood | use |
|---|---|
| `curious` | discovery, questions, secrets |
| `dread` | disaster, danger, loss of control |
| `elegy` | grief, farewell, memory |
| `reflective` | quiet, old, alone, winter, home |
| `tension` | chase, police, alarm, crime, heist |
| `triumph` | win, launch, success, first, rise |

Force them only when the automatic choice is wrong:

```bash
python3 $S/scripts/compile.py beat-plan.json --grade noir --mood tension -o storyboard.json
```

### Motion plan

`apply_motion_plan()` maps the animation-director tiers into this style's
camera vocabulary. `hold` and `impact` get no added camera move; `limited`,
`full` and `sakuga` scale `move_amount`, with `sakuga` multiplied by `1.6`.
`impact` also records `impact_at`. If more than half the planned shots name
beats that do not exist, the compiler refuses the stale plan.

---

## Fetching footage

Pexels is searched first; Pixabay is tried only when configured and Pexels
returns no candidates for a query. Searches are serial and cached under
`footage/.search-cache`; downloads run in parallel.

Pexels API details that matter:

- endpoint: `GET https://api.pexels.com/v1/videos/search`;
- the bare `https://api.pexels.com/videos/` path is deprecated;
- auth header: `Authorization: <RAW_KEY>`, not `Bearer <KEY>`;
- params used here: `query`, `orientation`, `page`, `per_page`;
- Pexels also accepts `size` and `locale` on search; `per_page` max is `80`;
- `min_duration` and `max_duration` exist on `/videos/popular`, not on
  `/videos/search`;
- quota headers appear on 2xx only:
  `X-Ratelimit-Limit`, `X-Ratelimit-Remaining`, `X-Ratelimit-Reset`;
- a typical key is `25000` requests/month; HTTP `429` means it is exceeded;
- `video_files[].quality` is frequently `null`, not only `hd`, `sd` or `uhd`.
  Never branch on it; pixel area is the trustworthy field;
- `link` values are signed, time-limited Vimeo CDN URLs. They expire. Never
  cache them into the storyboard; `fetch.py` deletes `clip["url"]` after
  download.

Pixabay fallback:

- endpoint: `GET https://pixabay.com/api/videos/?key=...&q=...`;
- the key is a query parameter, not a header;
- quality tiers are `large`, `medium`, `small`, `tiny`.

A candidate is scored by resolution, whether it is long enough, aspect-ratio
fit and not being vastly longer than needed. The downloaded file is the smallest
file that still covers the delivery frame; if none does, the largest available
is used and marked `upscaled`.

`in_point()` never starts at `0` when there is room, because stock clips often
open on slates or fades and end on watermarks. Short clips are looped later
with `-stream_loop -1`; a plain `-t` freezes the final frame and reads as a
hung video.

### Synthetic-footage rejection

Stock libraries contain vector animations and motion-graphics templates. One
landed in the demo film: a flat cyan cartoon of a bank among rainy night clips,
right at the twist.

`looks_synthetic()` samples two frames one second apart and measures the
fraction of bit-identical pixels. Camera sensors never repeat exactly because
of grain, dither and compression noise; rendered artwork does. Threshold:
`0.85`. Measured on the real film: cartoon `0.921`, highest legitimate clip
`0.667`, median `0.112`.

Two cheaper tests were tried and failed:

- distinct colour count: cartoon `83`, genuine dark clips `28`, `30`, `32`;
- noise floor in flat blocks: cartoon `0.000`, but four genuine night clips
  were also `0.000` because h264 crushes dark flat regions to zero variance.

Rejection triggers an automatic re-shoot of that beat, bounded to two rounds.
The rejected clip stays in the `used` set so it cannot be handed back.

---

## Rendering

Render normalises each shot into a segment, then joins segments with the concat
demuxer. It does not build one giant `filter_complex`.

That is required because clips arrive with different resolutions, frame rates
(24, 25 and 29.97 have all appeared), pixel formats and audio tracks. The
concat demuxer silently produces broken output unless every segment has already
been normalised: fps, SAR, pix_fmt and `-an`.

This ffmpeg build has no `drawtext` because it was built without `libfreetype`.
All text is rendered by PIL to transparent PNGs and composited with `overlay`.
Never suggest `drawtext` for this style.

Push-ins use `scale` with `eval=frame`, not `zoompan`. `zoompan` computes an
integer crop window per frame, so a slow push judders on hard edges. `scale`
resamples sub-pixel and visibly improves stock footage.

Auto-exposure is a partial gamma correction applied before the grade:

- `EXPOSURE_STRENGTH = 0.5`;
- gamma clamped to `[0.78, 1.30]`;
- luma measured with `signalstats`/`YAVG` at `3fps`;
- median luma is used, not mean, so one blown frame cannot drag the correction;
- gamma is used, not brightness, because brightness lifts blacks and highlights
  together and turns the image milky;
- full correction was tried and turned a dark vault interior into flat grey.

Audio places narration on the storyboard clock, synthesises a bed if needed,
ducks the bed with `sidechaincompress` keyed off the voice track, then applies
`loudnorm=I=-14`.

---

## The gate

The contact sheet is the gate:

```bash
python3 $S/scripts/render.py storyboard.json --sheet
```

It writes one labelled frame per shot. Look at it before committing to a full
render. It is the practical way to catch the two failures that matter: the same
clip answering two beats, and a grade that has flattened a run of shots to one
colour.

After a full render, inspect the `.timeline.json` sidecar and `assets.json`.
They are written from the rendered/resolved cut, not reconstructed later.

---

## Quick reference

| task | command |
|---|---|
| validate only | `python3 scripts/compile.py beat-plan.json --check` |
| compile | `python3 scripts/compile.py beat-plan.json -o storyboard.json` |
| compile directed | `python3 scripts/compile.py beat-plan.json --motion-plan motion-plan.json -o storyboard.json` |
| compile different aspect | `python3 scripts/compile.py beat-plan.json --aspect 9:16 -o storyboard.json` |
| force look | `python3 scripts/compile.py beat-plan.json --grade noir --mood tension -o storyboard.json` |
| fetch footage | `python3 scripts/fetch.py storyboard.json` |
| dry-run fetch | `python3 scripts/fetch.py storyboard.json --dry-run` |
| re-resolve shots | `python3 scripts/fetch.py storyboard.json --only s07 s08 --refetch` |
| custom footage dir | `python3 scripts/fetch.py storyboard.json --footage footage` |
| contact sheet | `python3 scripts/render.py storyboard.json --sheet` |
| named contact sheet | `python3 scripts/render.py storyboard.json --sheet sheet.jpg` |
| preview render | `python3 scripts/render.py storyboard.json --preview -j 8 -o preview.mp4` |
| one frame | `python3 scripts/render.py storyboard.json --frame 42.0 -o frame.png` |
| no music | `python3 scripts/render.py storyboard.json --no-music -o film.mp4` |
| skip exposure matching | `python3 scripts/render.py storyboard.json --no-auto-exposure -o film.mp4` |
| keep work folder | `python3 scripts/render.py storyboard.json --keep -o film.mp4` |
| make a bed | `python3 scripts/score.py --mood tension --duration 117.1 -o bed.wav` |

See also: [`reference/storyboard.md`](reference/storyboard.md),
[`reference/searching.md`](reference/searching.md),
[`reference/documentary-rhythm.md`](reference/documentary-rhythm.md),
[`reference/licensing.md`](reference/licensing.md) and
[`reference/verification.md`](reference/verification.md).
