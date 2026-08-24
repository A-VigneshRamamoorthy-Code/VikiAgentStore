# Where to get art for this style

This style ships with two complete, CC0 art libraries so that
`copilot plugin install film-crew` gives you something that renders
immediately, with nothing to download and no account anywhere.

It also knows how to *use* art you supply yourself, which is what this
document is about.

---

## The distinction that governs everything here

There are two separate questions, and they have different answers:

| | Can **you** use it in your film? | Can **this repo** ship it to everyone? |
|---|---|---|
| CC0 / public domain | yes | **yes** — so it is vendored in `assets/packs/` |
| Freepik / Magnific, Envato, Adobe Stock, most "free" stock sites | usually yes, under their terms | **no** — redistribution is explicitly forbidden |

This repository is public and MIT-licensed. Committing an asset here
sublicenses it to every person who installs the plugin, which is precisely
what stock-site terms prohibit — Freepik's forbid redistributing content "in
… a library … for distribution."

So `scripts/fetch_assets.py` **refuses to download from those hosts at all**
(see `BLOCKED_HOSTS`). That is not an oversight to work around; it is the
enforcement.

The way to use that art is to download it yourself, under your own account
and your own licence, and drop it into a directory this repo never commits.

---

## Vendored libraries (already here, nothing to do)

| Library | Author | Licence | Contents |
|---|---|---|---|
| [Open Peeps](https://openpeeps.com) | Pablo Stanley | CC0-1.0 | 172 pieces — heads, faces, hair, bodies, poses |
| [Humaaans](https://humaaans.com) | Pablo Stanley | CC0-1.0 | 47 pieces — heads, hair, bodies, legs, shoes |

Sets, buildings, vehicles and street furniture are drawn procedurally in
`components/Sets.jsx` — they are code, not files, so they scale and recolour
per pack without any asset at all.

Verify them with:

```bash
python3 scripts/fetch_assets.py --check
```

---

## Bringing your own art

### 1. Download it

**Magnific / Freepik** — the broadest single source, covering every asset
class this style can use:

<https://www.magnific.com/search?ai=excluded&format=search&last_filter=selection&last_value=1&query=2d+character&selection=1>

Set `ai=excluded` (already in that URL) to filter to human-made work. Change
the `query` parameter for the category you need:

| You need | `query=` |
|---|---|
| people | `2d character`, `flat character`, `character walk` |
| backgrounds | `flat city background`, `landscape illustration` |
| buildings | `flat buildings`, `city skyline flat` |
| vehicles | `flat car side view`, `flat vehicle` |
| props | `flat street furniture`, `flat tree` |

Prefer **SVG** downloads. This is a vector pipeline: an SVG can be recoloured
per pack, skinned to a rig, and scaled to any resolution, and a PNG can do
none of those things.

Other sources worth knowing, both genuinely redistributable:
[unDraw](https://undraw.co) (MIT) and [Blush](https://blush.design) (mixed —
check per collection).

### 2. Drop it in

```
assets/local/
├── characters/
├── backgrounds/
├── buildings/
├── vehicles/
└── props/
```

`assets/local/` is **gitignored in its entirety**. Nothing you put there will
ever be committed, which is what keeps your licence yours and this repo's
licence clean.

### 3. Point the film at it

```jsx
import {localPack} from '../lib/packs';

const pack = localPack('assets/local/characters/my-cast');
```

If a required asset is missing, `fetch_assets.py --require` reports exactly
which one and prints the search URL above rather than silently rendering a
figure with no head.

```bash
python3 scripts/fetch_assets.py --sources          # print every known source
python3 scripts/fetch_assets.py --require head/Afro body/Standing
```

---

## Checklist before you commit

- [ ] Nothing from a stock site is inside `assets/packs/`
- [ ] `git status` shows nothing under `assets/local/`
- [ ] `python3 scripts/fetch_assets.py --check` passes
- [ ] Any new **vendored** asset is CC0/MIT/public-domain, and is recorded in
      [`LICENSES.md`](LICENSES.md) with its author and source URL

The full reasoning, and the per-asset provenance record, is in
[`LICENSES.md`](LICENSES.md).
