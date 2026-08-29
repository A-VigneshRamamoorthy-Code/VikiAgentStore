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

### Sources proven on a finished film

The three-minute film this style was hardened on was cast entirely from the
libraries below. They are listed in the order you should try them, because the
first group is CC0 or credit-free — the same standing as the vendored packs,
so it may be committed as well as used.

**Redistributable — no attribution required**

| Source | What it gives you |
|---|---|
| [Kenney](https://kenney.nl/assets) (CC0) | [background elements](https://kenney.nl/assets/background-elements) and their [remaster](https://kenney.nl/assets/background-elements-redux) — tileable parallax hills, trees, clouds, rocks; plus a [modular character pack](https://kenney.nl/assets/modular-characters) of swappable parts on a grid |
| [OpenGameArt](https://opengameart.org) (CC0) | [modular animated vector characters](https://opengameart.org/content/free-cc0-modular-animated-vector-characters-2d) with per-part frames, and a [bone-rigged puppet](https://opengameart.org/content/2d-puppet-character) with a joint-placement guide |
| [Okay Samurai](https://okaysamurai.com/puppets/) (free to use and edit, no credit) | Character Animator puppets — **the cheapest route to a full viseme set**, because a puppet already ships every mouth shape cut and named |

**Usable in your film, not committable** — these need `$FILM_CREW_ASSETS`:

| Source | What it gives you |
|---|---|
| [Vecteezy](https://www.vecteezy.com) (Free License, attribution) | finished background plates and modular kits, including a [woman body constructor](https://www.vecteezy.com/vector-art/2920510) and a [lip-sync set](https://www.vecteezy.com/vector-art/1008545) |
| [Freepik](https://www.freepik.com) (Free License, attribution) | character turnarounds and motion kits — front/back/side with expressions and separated limb poses; the [young woman animation set](https://www.freepik.com/free-vector/young-cute-woman-character-animated-creation-people-with-emotions-face-animation-mouth-flat-vector-design_20075948.htm) carries a full mouth chart |

Two lessons from using them, both expensive to relearn:

- **A turnaround or "motion kit" sheet is worth more than a finished
  illustration.** It gives one head drawing plus separated limbs and
  expressions, which is exactly what a rig wants. A finished pose gives you one
  frame.
- **Check for a mouth chart before casting anybody who speaks.** A character
  with no viseme set has to have one drawn or cut by hand, and that decision is
  hard to reverse once the rig is baked — see
  [`../reference/lip-sync.md`](../reference/lip-sync.md).

Keep a machine-readable index next to the art — source name, source URL,
licence, `attribution_required` — rather than trusting directory names. It is
what makes the committable/not-committable split above checkable instead of
remembered, and it is what a credits roll is generated from.

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

```python
import sys; sys.path.insert(0, "scripts")
from asset_library import find

head = find("characters/my-cast/head.png", required=True)
```

`find()` walks `$FILM_CREW_ASSETS`, the saved config, `assets/local/` and
`assets/packs/` in that order and returns the first hit, so the same film runs
against bundled art or a bought kit with no edit. Pass `required=True`
wherever a missing file means the shot is wrong — see
[`../reference/asset-library.md`](../reference/asset-library.md).

If a required asset is missing, `fetch_assets.py --require` reports exactly
which one and prints the search URL above rather than silently rendering a
figure with no head.

```bash
python3 scripts/asset_library.py                   # show the resolved chain
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
