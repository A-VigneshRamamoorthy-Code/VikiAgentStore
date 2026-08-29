# Your own art library

Most of what a film needs is committed under `assets/packs/`. This document is
about the rest: commercial character kits, EPS/AI packs bought from a stock
site, a studio's own library. That material is perfectly usable in a film and
**not** redistributable inside an MIT-licensed skill, so it is pointed at from
outside rather than copied in.

```bash
export FILM_CREW_ASSETS=/path/to/your/assets          # this shell
python3 scripts/asset_library.py --set /path/to/your/assets   # remembered
```

## Ask once, on first use

The first time this style runs for a user, ask where their art lives:

```bash
python3 scripts/asset_library.py --prompt
```

The command is idempotent — it prints nothing to answer if the question has
already been settled, either by an answer or by a decline — so it is safe to
run at the top of any workflow.

**Declining is a complete answer.** Say so, and carry on. With no external
library the style still has 172 CC0 Open Peeps assets, 47 Humaaans, four style
packs and everything the user drops into `assets/local/`; that is the
configuration every bundled example film was made with. A user who skips the
prompt must not be left believing the skill is now degraded, and nothing in
the pipeline may treat a missing external root as an error.

If they do name a directory, record it with `--set` so the question is not
asked again on the next film.

## Resolution order

First hit wins. `find()` walks these in order:

| | Source | Notes |
|---|---|---|
| 1 | `$FILM_CREW_ASSETS` | absolute path, or `:`-separated list, highest priority first |
| 2 | `~/.config/film-crew/assets.json` | whatever `--set` last wrote |
| 3 | `<skill>/assets/local/` | gitignored scratch dir inside the skill |
| 4 | `<skill>/assets/packs/` | the committed CC0 packs |

The environment variable outranks the saved config deliberately: it lets one
render be pointed somewhere else without editing state, which is what makes
this work from a batch job or a rented render box. Levels 3 and 4 always
exist, which is what makes level 1 optional.

```bash
python3 scripts/asset_library.py                 # show the resolved chain
python3 scripts/asset_library.py --check         # exit 1 if no external root
python3 scripts/asset_library.py --find characters/emma/head.png
python3 scripts/asset_library.py --forget        # back to bundled art
```

In code:

```python
from asset_library import find

head = find("characters/emma/head.png", required=True)
```

Pass `required=True` anywhere a missing file means the shot is wrong. A silent
`None` becomes a figure with no head several hundred frames later, and by then
nothing points back at the lookup that returned it — the same failure mode
[`lip-sync.md`](lip-sync.md) is a post-mortem of.

### A cached plate hides a broken path indefinitely

Sets are expensive, so they are baked once and cached. That cache will happily
outlive the art it was built from, and this is the resulting bug:

> A film rendered correctly for weeks. Its forest set pointed at
> `Assets/kenney_background-elements/PNG/`. The library had since been
> reorganised into `Assets/backgrounds/element-kits/background-elements/PNG/`,
> so that directory no longer existed. Nothing failed, because no set was ever
> rebuilt. The defect surfaced only when the frame cache was cleared during
> housekeeping — at which point the finished film could not be reproduced from
> its own source.

The cache was not the problem; it was the anaesthetic. Two habits prevent it:

- **Resolve a kit directory once, at import, against a file you know is in
  it** — and raise naming every candidate path tried when none match. An
  import-time failure is loud on the next run. A render-time one waits for a
  cache miss.
- **Periodically render with the plate cache deleted.** Nothing else proves the
  film is still made of the art it claims. Reproducing from source is a
  property that decays silently, so it has to be re-established rather than
  assumed.

```python
ASSETS = os.environ.get("FILM_CREW_ASSETS") or DEFAULT_LIBRARY

def kit_root(probe, *candidates):
    tried = []
    for rel in candidates:
        root = os.path.join(ASSETS, rel)
        tried.append(root)
        if os.path.exists(os.path.join(root, probe)):
            return root
    raise FileNotFoundError(
        f"Cannot locate kit holding {probe!r}. Tried:\n  " + "\n  ".join(tried)
    )
```

Listing the old location as a later candidate keeps existing installs working
while the canonical path leads.

## What belongs outside, and what belongs in

`asset_library.py` never downloads anything. `fetch_assets.py` owns the network
and the licence gate, and the two do not overlap. The split is the licence
boundary:

- **Committed** (`assets/packs/`) — CC0/MIT/public-domain only, pinned by
  sha256 in `manifest.json`, recorded in `LICENSES.md`. This skill ships inside
  a public MIT repository, so a source must be *redistributable*, not merely
  usable.
- **Outside** (`$FILM_CREW_ASSETS`) — everything else. Freepik/Magnific and the
  other stock marketplaces forbid including their content in "a database,
  archive or library, for distribution" and forbid sublicensing; their terms
  also forbid scripted access, which is why `fetch_assets.py` refuses those
  hosts before any network call. Buying a kit and using it in your film is
  fine. Committing it here is not, and neither is asking this skill to scrape
  it.

Pointing at a directory does not copy it, so nothing about this arrangement
puts unlicensed art into the repository. That is the entire reason it is a
path and not a vendoring step.

## Using a bought character kit well

If a kit is the reason for the external library, two rules from the golden list
decide whether it works.

**Cast the whole film out of one kit.** Mixing an illustrator's character with
another's is the failure; using one coherent pack for everybody is not. The
film this was hardened on drew a girl, a wizard and its bystanders from a
single pack — one head drawing, recoloured and re-cut — and that is why the
cast reads as one production.

**Check the resolution you actually need before re-cutting anything.** The
temptation on seeing a soft close-up is to re-rasterise the source and rebuild
the rig, which invalidates the face measurements, every baked variant, and
every pivot and socket, in that order. Measure first:

```
on-screen head width  =  head art width x character scale x max shot zoom
```

If that number is below the art's own pixel width, the art is being
*downscaled* and re-cutting buys nothing. On the film in question Emma's head
peaked at ~316px on screen against 346px of drawing, so the entire "low
resolution" complaint was fixed by raising the **output** from 720p to 1080p —
one config line — and not by touching the art at all. Renderers that
supersample internally have usually been drawing at the higher resolution the
whole time.

Kits are usually vector. Rasterise at the size you need rather than upscaling a
preview:

```bash
gs -dNOPAUSE -dBATCH -sDEVICE=pngalpha -r288 -sOutputFile=/tmp/kit.png kit.eps
```

That produced a 13923×10757 sheet in six seconds. There is no reason to work
from the thumbnail.
