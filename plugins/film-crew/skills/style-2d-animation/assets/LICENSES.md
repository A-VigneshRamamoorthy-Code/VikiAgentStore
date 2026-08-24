# Asset licences

Everything under `assets/` is provisioned by `../scripts/fetch_assets.py` from
the sources declared in `manifest.json`. This file is the human-readable
version of that manifest: what is here, whose it is, and under what licence.

## Open Peeps -- `assets/packs/peeps/`

- **Author:** Pablo Stanley
- **Licence:** CC0 1.0 Universal (public domain dedication)
- **Homepage:** <https://www.openpeeps.com/>

Open Peeps' own site states it plainly: "The library is in the public domain
under the CC0 License. This means you can copy, modify, distribute, remix,
burn, and use the work, even for commercial purposes, without asking
permission." CC0 requires no attribution at all -- we credit Pablo Stanley
here anyway, because the work is worth naming even when the licence does not
ask for it.

The 172 assets extracted into `packs/peeps/` (heads, faces, beards,
accessories and bodies -- standing, sitting and the combined `effigy` figure)
are pulled from the compiled build of the **`@opeepsfun/open-peeps`** npm
package, version `1.0.6`, an MIT-licensed repackaging of the same CC0
artwork as installable React components:

```
https://registry.npmjs.org/@opeepsfun/open-peeps/-/open-peeps-1.0.6.tgz
```

`fetch_assets.py` downloads that exact tarball, checks it against the sha256
pinned in `manifest.json`, and runs it through `../scripts/extract-peeps.mjs`,
which lifts the geometry out of the compiled components into flat JSON so
this skill has no npm/React dependency of its own. Re-running the fetcher
reproduces the committed files byte for byte.

Two licences are in play and both permit exactly what this repository does
with them: CC0 covers the artwork itself, MIT covers the packaging it is
distributed through. Neither restricts redistribution, modification or
commercial use, which is why this is the only source in the manifest.

## Humaaans -- `assets/packs/humaaans/`

- **Author:** Pablo Stanley
- **Licence:** CC0 1.0 Universal (public domain dedication)
- **Homepage:** <https://www.humaaans.com/>

humaaans.com states the terms in one line: "Free for commercial or personal
use. CC0 Public Domain License. Made by Pablo Stanley." As with Open Peeps,
CC0 asks for no attribution and we credit the author anyway.

**Do not take a licence from a mirror.** The two most-linked GitHub copies of
this artwork disagree with each other -- one declares MIT, the other
CC-BY-4.0 -- and neither is the copyright holder, so neither is authoritative.
The CC0 above comes from Pablo Stanley's own site. Whatever a re-uploader
writes in their README has no bearing on the terms the work is actually
offered under; check the source, every time.

The 47 assets in `packs/humaaans/` (18 heads, 10 bodies, 8 standing bottoms,
4 sitting bottoms, 3 seats and 4 scene pieces) are extracted from the `Flat
Assets` directory of the upstream repository, pinned to commit
`818f184343b884123e08e531ffd62c5b2f9ffef4` and checked against the sha256 in
`manifest.json`. `../scripts/extract-humaaans.mjs` turns the Sketch-exported
SVGs into the same flat JSON shape the Peeps extractor produces.

Only identity-carrying fills are tokenised -- `@skin`, `@hair`, `@clothing`,
`@shoe`, `@ink`, `@shade`. The rest keep the artist's literal hexes on
purpose: Humaaans garments are two-tone, and flattening every fill to one
palette role would throw away the shading that makes the art read as folded
cloth rather than a silhouette.

## Why not Freepik / Magnific

The project this skill serves once considered sourcing character art from
`magnific.com`. Magnific was acquired by Freepik Company S.L. in 2024 and
rebranded, so `magnific.com` today is Freepik under a different name and the
same Terms of Use apply.

Those terms say no. Freepik's Terms of Use, §8.1, list what a downloaded
asset may not be used for, including being "included (in whole or in part) in
a database, archive or in any other media/stock product, collection, set of
clips, or library, for distribution", and forbid you to "resell, assign,
transfer or sublicense" it. This repository is public and MIT-licensed, so
committing a Freepik asset to it would do precisely that -- distribute it as
part of a library and sublicense it to everyone who installs this skill. §2
separately forbids using "robots, spiders or any other mechanism" to fetch
from the site, which rules out an automated fetcher even if the redistribution
clause did not already settle the question.

So the asset never enters the repository, and the fetcher does not go looking
for it. `fetch_assets.py` keeps a `BLOCKED_HOSTS` list that includes
`magnific.com` and `freepik.com` (and their common subdomains) and refuses to
fetch from them before any network request is made, quoting this reasoning
back at whoever configured it. The same check requires every source in
`manifest.json` to declare a licence from an explicit allow-list -- CC0-1.0,
MIT, Unlicense, PDDL-1.0, CC-BY-4.0 -- so a source cannot slip through by
simply omitting the question. This is a statement about Freepik's terms, not
a judgement on the artwork; the fix, if the film needs that specific look, is
a licence that actually grants redistribution, not a workaround for this one.

## Adding another source

Add an entry to `manifest.json` with `license` on the allow-list and `url`
pointed at a host that is not blocked, then run `fetch_assets.py`. If the
source fails either check, the fetcher explains which one and why -- that is
the point of enforcing it in code rather than in a document someone has to
remember to read.
