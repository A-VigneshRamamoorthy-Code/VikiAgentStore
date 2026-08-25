# Searching footage

Search is the hard part of this style. The board says what the line needs to
show; `compile.py` turns that prose into queries; `fetch.py` asks stock-video
APIs and chooses one local clip per shot.

## Query derivation

`query_from()` uses a deliberate fallback chain:

1. `assets[].hint` from the beat plan. Treat it as a query, not a label. The
   storyboard artist put it there because they knew a camera had to have
   pointed at the thing.
2. `subject` nouns, with stop words removed.
3. Shorter widenings of the subject or primary query. A shorter query matches
   more.
4. Nouns from the narration line, only as a last resort.

The output is `shot.query` plus up to four `shot.alternates`. `fetch.py` tries
them in order and records the query that actually won in `clip.query`.

## What makes a good hint

Write the thing a camera could have photographed:

| weak | better |
|---|---|
| `distraction` | `empty bank corridor` |
| `moment of panic` | `crowd running night` |
| `records are gone` | `open filing cabinet documents` |
| `truth revealed` | `police empty road dawn` |

A hint can be more literal than the narration. If the line says "the street
folds open", the hint can be `street driving night`.

## Abstractions are rejected

`searchable()` rejects a query that reduces to stop words or abstractions:
`moment`, `time`, `thing`, `story`, `silence`, `nothing`, `fear`, `hope`,
`plan`, and the rest of the `ABSTRACT` table. Searching `moment` returns
confident irrelevant footage, which is worse than no footage because it looks
plausible.

Fix it by changing the beat's `subject` or adding `assets[].hint`:

```json
{
  "subject": "the case behaving like ballast",
  "assets": [{ "kind": "footage", "hint": "briefcase closeup car" }]
}
```

Do not hide the failure by using a generic query that does not match the line.
The style contract is: never invent a picture.

## API facts

Pexels:

- endpoint: `GET https://api.pexels.com/v1/videos/search`;
- `https://api.pexels.com/videos/` is deprecated;
- auth header: `Authorization: <RAW_KEY>`, not `Bearer <KEY>`;
- accepted search params include `query`, `orientation`, `size`, `locale`,
  `page`, `per_page`; `per_page` max is `80`;
- `fetch.py` sends `query`, `orientation`, `per_page=15`, `page=1`;
- `min_duration` and `max_duration` are not search params; they exist on
  `/videos/popular` only;
- quota headers are present on 2xx responses only:
  `X-Ratelimit-Limit`, `X-Ratelimit-Remaining`, `X-Ratelimit-Reset`;
- a typical key is `25000` requests/month; HTTP `429` means the quota is
  exceeded;
- `video_files[].quality` is often `null`. Use width and height, not quality;
- `video_files[].link` values are signed, time-limited Vimeo CDN URLs. They
  expire and must not be stored as storyboard truth.

Pixabay fallback:

- endpoint: `GET https://pixabay.com/api/videos/?key=...&q=...`;
- the API key is a query parameter, not a header;
- quality tiers are `large`, `medium`, `small`, `tiny`.

There is no key-free Pexels path. The internal API returns 401, search HTML has
no `.mp4` URLs and no `__NEXT_DATA__`, and robots.txt disallows search, API and
download paths.

## Choosing a candidate

`fetch.py` normalises provider results, then scores candidates:

- covering the target width and height is strongly rewarded;
- being too small is penalised and marked `upscaled` if selected;
- the clip should be long enough for `shot.dur * abs(speed)` plus a little
  spare;
- aspect ratio near the delivery frame wins;
- very long clips are mildly penalised because they waste bandwidth and often
  contain one useful second in a static shot.

`pick_file()` downloads the smallest file that still covers the delivery frame,
not the largest original. A 4K original for a 1080p film is usually just
bandwidth.

Clip deduplication is global. Once `source:id` is used, it cannot answer another
shot in the same fetch run.

## Cache and re-cutting

Search responses are cached under `footage/.search-cache`, keyed by provider,
query and orientation. Downloads are cached by provider, clip id and file size.

Use targeted re-resolution when one beat is bad:

```bash
python3 scripts/fetch.py storyboard.json --only s40 --refetch
```

Use `--footage DIR` to put clips somewhere else. Use `--dry-run` to report
planned fetches without writing or touching the network.

## Synthetic footage

`looks_synthetic()` is a temporal test. It samples two frames one second apart
and measures the fraction of bit-identical pixels. Real camera footage changes
slightly even when locked off; vector animation and templates often repeat
exactly. Threshold: `0.85`.

Measured on the demo film:

- bad cartoon bank: `0.921`;
- highest legitimate clip: `0.667`;
- film median: `0.112`.

Two earlier tests failed and should not be repeated:

- distinct colour count: cartoon `83`, real dark clips `28`, `30`, `32`;
- flat-block noise floor: cartoon `0.000`, but four real night clips were also
  `0.000` because h264 crushes dark flat regions.

When a clip is rejected, the beat is automatically re-shot for up to two rounds.
The rejected clip remains in `used`, so it cannot come back.
