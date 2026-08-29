# Your own art goes here

This is **level 3** of the four places this style looks for art. Nothing in
this directory is committed — see `.gitignore`.

```
characters/   backgrounds/   buildings/   vehicles/   props/
```

## Use this directory, or point outside it?

Both work, and they resolve in a fixed order (first hit wins):

| | Source | Use it for |
|---|---|---|
| 1 | `$FILM_CREW_ASSETS` | a library you already have somewhere else |
| 2 | `~/.config/film-crew/assets.json` | the same, remembered between sessions |
| 3 | **this directory** | a handful of files for one film |
| 4 | `../packs/` | the committed CC0 art |

Drop files here when it is a few assets for the film you are making now. Point
`$FILM_CREW_ASSETS` at a directory instead when you have a real library — a
bought character kit, a studio collection, something shared between projects:

```bash
python3 ../../scripts/asset_library.py --set /path/to/your/assets
```

That is also the only correct home for anything from a stock site. See
[`../SOURCES.md`](../SOURCES.md) for which sources may be committed and which
may not, and [`../../reference/asset-library.md`](../../reference/asset-library.md)
for the licence reasoning.

## Point a film at it

Whichever level the file lives at, one call finds it:

```python
import sys; sys.path.insert(0, "scripts")
from asset_library import find

head = find("characters/my-cast/head.png", required=True)
```

Paths are **relative to the root**, not to this directory — that is what lets
the same film run against bundled art or against a bought kit without an edit.

Always pass `required=True` where a missing file means the shot is wrong.
Without it `find` returns `None`, and a `None` becomes a figure with no head a
few hundred frames later, by which point nothing points back at the lookup
that returned it.

```bash
python3 ../../scripts/asset_library.py                    # show the resolved chain
python3 ../../scripts/asset_library.py --find characters/my-cast/head.png
```
