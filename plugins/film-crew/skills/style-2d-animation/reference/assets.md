# Assets

Characters in this skill are **real illustrated artwork**, not shapes drawn in
code. The difference is the difference between the two videos this rebuild
replaced and the one it produces.

Everything here is **CC0** and committed to the repository, so a render works
offline and produces the same frames on every machine.

---

## What is bundled

| Set | Count | Licence | Source |
|-----|-------|---------|--------|
| Open Peeps heads | 53 | CC0-1.0 | Pablo Stanley |
| faces | 33 | CC0-1.0 | ” |
| beards | 16 | CC0-1.0 | ” |
| accessories | 9 | CC0-1.0 | ” |
| bodies (standing / sitting / effigy) | 61 | CC0-1.0 | ” |

Stored as flat JSON under `assets/packs/peeps/<category>/<Name>.json`, plus:

- `index.json` — what exists, by category
- `layout.json` — the composition offsets that put a face on a head correctly,
  including 44 per-hairstyle nudges lifted from the original artwork

Full provenance and the CC0 text: [`assets/LICENSES.md`](../assets/LICENSES.md).

---

## Why not the requested source

The brief pointed at **magnific.com** for characters and props. Those assets
are not bundled, and it is worth being precise about why, because the site
looks free.

Magnific was acquired by **Freepik Company S.L.** in 2024 and its content is
served under Freepik's Terms of Use. Two clauses decide it:

- **§8.1(3)–(4)** — you may not include the content in "a database, archive or
  … library, for distribution", and you may not sublicense it.
- **§2** — automated access by robots or spiders is prohibited.

This repository is a public, MIT-licensed asset library. Committing Freepik
content would do exactly the two things §8.1 forbids: build a redistributable
library, and sublicense it onward to everyone who clones the repo. Fetching it
with a script would breach §2 on the way in.

So the fetcher refuses. `BLOCKED_HOSTS` in `scripts/fetch_assets.py` rejects
`magnific.com`, `freepik.com`, `mixkit.co`, `craftwork.design` and `icons8.com`
**before any network call**, and prints the governing clause rather than a bare
error. `ALLOWED_LICENSES` independently refuses any source not declared
CC0-1.0, MIT, Unlicense, PDDL-1.0 or CC-BY-4.0.

You can still use Freepik art in your own local project under your own Freepik
licence. It cannot live in this repository.

---

## Fetching

Assets are committed, so nothing is needed for a normal render. The fetcher
exists to prove they are what they claim to be, and to restore them.

```bash
python3 scripts/fetch_assets.py --check          # verify what is on disk
python3 scripts/fetch_assets.py                  # fetch anything missing
python3 scripts/fetch_assets.py --force          # re-download and re-verify
python3 scripts/fetch_assets.py --list           # print every available asset
python3 scripts/fetch_assets.py --require head/Afro
```

`--require` is the one to call from a film: it exits non-zero with a readable
message if a named asset is absent, which is better than a render that silently
draws a headless figure.

The manifest records a real sha256 of the upstream tarball. It was produced by
downloading and hashing it, and re-extraction was confirmed to reproduce the
committed 172 assets byte-for-byte.

> One upstream quirk, handled in `_safe_extract`: the Open Peeps tarball stores
> directories as mode `0o666` — no execute bit — so a plain `tarfile.extractall()`
> yields directories nothing can traverse. The extractor assigns its own modes,
> and rejects symlinks, hardlinks, absolute paths and `..` escapes by realpath
> containment while it is there.

---

## How a character is assembled

Open Peeps bodies are **static poses, not cycles** — "Walking" is one drawing of
someone mid-stride. You cannot animate a walk with it, and stepping between
poses reads as a flipbook.

So the two halves are split by what each is good at:

- **The head comes from the artwork.** Hair, face, beard, accessory — all the
  identity and all the drawn character, composed through `layout.json`.
- **The body is rigged and solved.** Torso, arms and legs are drawn to match the
  ink weight and palette of the Peeps line, then driven by the physics in
  [`physics.md`](physics.md).

That seam is invisible because the rig is drawn in the same language: heavy
confident ink, flat fills, rounded joints. Thin strokes here read instantly as
a different illustrator.

```jsx
<Character
  m={track.at(frame)}                 // the ONLY source of facing and phase
  look={{palette, hair, face, beard, accessory, layout}}
  scale={0.42}
/>
```

Note that `Character` takes no `stride`. It owns its own, and callers ask
`strideUnits(scale, gait)` for the matching scene distance. Stride used to be a
prop, and every caller had to convert scene units to character units by
dividing by its own scale — precisely the bookkeeping that goes wrong the
moment two characters are drawn at different sizes.

---

## Colour tokens

Peeps artwork ships with parameterised fills. The extractor rewrites them to
tokens, which the pack resolves at render time:

| Token | Meaning |
|-------|---------|
| `@skin` | skin |
| `@ink` | outline |
| `@clothing` | garment |
| `@hair` | hair |

This is what makes a cast look like one cast. Every colour in a shot comes from
one pack in `lib/packs.js` — nothing is written at a call site — so two
characters cannot end up with subtly different blacks, which was one of the
things wrong with the `pursuit` film.

---

## Sets

Backgrounds are **authored in-style**, not imported, and that is a deliberate
choice rather than laziness.

What makes a background good is that it matches the characters standing in
front of it. Importing a pixel-art tileset or a different vector pack next to
Open Peeps figures would reintroduce exactly the inconsistency this rebuild
exists to remove — two illustrators in one frame, which the eye catches
immediately even when it cannot name what is wrong.

`Sets.jsx` builds streets from the pack's own palette and ink weight, seeded so
they are deterministic.

Two staging rules it enforces:

- **Street furniture stands upstage of the acting line** — slightly higher on
  the plate and slightly smaller — so the cast passes in front of it. Sharing
  one ground line with the characters is cheap to write and looks exactly like
  what it is: a bench growing out of somebody's hip.
- **Something must occlude the actors.** Depth in a flat drawing comes from
  overlap, and overlap only reads if something passes in front as well as
  behind. `StreetForeground` is a kerbside railing at shin height. It has to be
  a thing that would plausibly be there — the first attempt put a hedge in the
  middle of the carriageway, which occluded correctly and read as nonsense.

---

## Adding an asset

1. Add the source to `assets/manifest.json` with its licence and sha256.
2. If it is not CC0/MIT/Unlicense/PDDL/CC-BY, stop — `ALLOWED_LICENSES` will
   refuse it, and that refusal is correct.
3. Run `python3 scripts/fetch_assets.py --force`.
4. Commit the extracted assets **and** the manifest together.

Never add an asset the fetcher cannot re-derive. An asset that only exists
because somebody once dragged it into the folder is an asset nobody can verify
the provenance of later.
