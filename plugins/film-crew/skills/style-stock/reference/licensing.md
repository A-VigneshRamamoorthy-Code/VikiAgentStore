# Licensing and credits

The licence is established during fetch, not after render. `fetch.py` writes
credits into the storyboard and writes a flat `assets.json` beside it on every
non-dry run. That file is the ledger `rights-manager` reads.

## Pexels

Pexels permits free commercial use and modification. Attribution is not
required, but it is recommended. This style records the recommended form:

```text
Video by <author> on Pexels
```

with the author's URL and the clip page URL when the API supplies them.

Do not use Pexels footage to:

- redistribute the clips as stock;
- build a competing stock service;
- imply the author, Pexels or an identifiable person endorses the film;
- show identifiable people in a bad light;
- put the footage in a trademark, logo or service mark.

Those restrictions matter most for true-crime, scandal and corporate pieces.
Stock B-roll can set atmosphere; it must not imply a real person in the shot did
something alleged by the narration.

## Pixabay

Pixabay fallback is recorded as `license: "Pixabay"` and credited as:

```text
Video by <author> on Pixabay
```

The API key is passed as `key=...` in the query string. Pixabay video quality
tiers are `large`, `medium`, `small`, `tiny`; do not expect Pexels-style
`hd`/`sd` values.

## The ledger

A credit entry looks like this:

```json
{
  "file": "footage/pexels-3727447-1920x1080.mp4",
  "license": "Pexels",
  "credit": "Video by German Korb on Pexels",
  "author": "German Korb",
  "author_url": "https://www.pexels.com/@german-korb-1920614",
  "page": "https://www.pexels.com/video/time-lapse-video-of-traffic-on-a-main-road-at-night-3727447/",
  "source": "pexels"
}
```

It is flat on purpose. A rights check should not need to parse the storyboard's
shot model.

`fetch.py` regenerates the ledger from resolved shots every run. If you re-cut,
re-fetch or replace footage, the ledger follows the cut and cannot drift.

## What not to commit

Commit documentation, storyboards, contact sheets and small sidecars when they
belong in the demo. Do not commit API keys. Put keys in a gitignored `.env`:

```bash
echo 'PEXELS_API_KEY=...' >> .env
```

Do not cache signed Pexels `link` URLs into the storyboard. They are temporary
Vimeo CDN URLs and expire. `fetch.py` removes `clip["url"]` after download for
that reason.

## Shipping check

Before publication, compare:

1. the final film;
2. the `.timeline.json` sidecar from render;
3. the current `assets.json`;
4. the storyboard `credits` array.

Every clip visible in the timeline should have a ledger entry, and every ledger
entry should correspond to a resolved shot. If a provider page is missing or an
author is `unknown`, flag it for rights review rather than silently polishing it
away.

## Never ship the footage

The prohibition on redistributing clips as stock is the reason this skill
commits a lockfile instead of media. Bundling downloaded mp4s into a plugin
that other people install is redistribution on a standalone basis, whatever
the intent.

`storyboard.json` therefore pins the provider and clip id for every shot, and
`fetch.py --` restores them by asking the API for a fresh signed URL per id.
The expiring URL itself is stripped before the storyboard is written, so a
committed storyboard can never carry a credential-bearing link.

This keeps the repository small, keeps the licence clean, and still makes the
example bit-for-bit reproducible: on an empty `footage/`, all 44 pinned clips
restore to the same ids.
