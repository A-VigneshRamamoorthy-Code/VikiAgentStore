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
| Humaaans heads | 18 | CC0-1.0 | Pablo Stanley |
| bodies | 10 | CC0-1.0 | ” |
| bottoms (standing / sitting) | 12 | CC0-1.0 | ” |
| seats + scene pieces | 7 | CC0-1.0 | ” |

Stored as flat JSON under `assets/packs/<pack>/<category>/<Name>.json`, plus,
per pack:

- `index.json` — what exists, by category
- `layout.json` — the composition offsets that put a face on a head correctly,
  including 44 per-hairstyle nudges lifted from the original artwork

### Animating the `bottom/` artwork

Whether a `bottom/` piece can be animated depends on how the artist drew it,
and it differs per asset:

| Asset | Structure | Animatable |
|---|---|---|
| `Sweatpants` | two separate `@clothing` legs + cuff + two shoes | **yes** |
| `Sprint` | two `@clothing` legs, one already `rotate(-55°)` | **yes** |
| `Skinny-Jeans`, most others | both legs fused into one path | no |
| every shoe, in every asset | own element, own `translate(...)` | **yes** |

Sprint is the tell: the artist rigs his own legs with a `rotate` about a hip
pivot, so transform-driven legs are the library's native idiom, not a hack.

But rotation alone is not enough. Hip→ankle distance over a real cycle runs
**194–240 for a walk and 149–251 for a run** — a rigid leg would have to shed a
third of its length at the top of a run, and a leg that cannot shorten drives
its swinging foot straight through the ground on every pass. What the drawing
lacks is not separability, it is a **knee**.

The first answer was to warp the artwork — two-bone skinning over the parsed
path — and it was the wrong one. A warp needs a hip, and the only landmark at
the top of a `bottom/` asset is the **waistband**, so cutting the trousers into
two independently-deformed ribbons discards the pelvis; the hard-edged
rectangle that used to sit at every hip was there to plug that hole. Nothing
needed plugging. The artist's own composition closes the hip for free, because
the torso is drawn *over* the trousers.

So `prepareBottom()` cuts instead of warping. It parses the asset, keeps each
leg as one whole drawn piece — never a ribbon — pairs it one-to-one with its
shoe by ankle proximity, and records the pivot and the geometry **it measures
from the drawing**:

```
far  leg  hip [143.4, 0] → ankle [ 84, 199]   drawn 207.7   splay −16.6°
near leg  hip [154.7, 0] → ankle [178, 199]   drawn 200.4   splay  +6.7°
                                              BONE  199.0 for both
```

Two lengths and one bone, and the difference between them is load-bearing. The
drawn length is the axis the artwork is *measured* along, so the bend stays the
identity at rest. The **bone** is the vertical drop, which is 199.0 for both
legs — because they are the same leg at two angles, not two different legs.
Taking the drawn length as the bone gives the figure a limp that no single
frame reveals: the hip rides wherever the leg currently in stance demands, so
it sits 7 units lower on every other step. Plot hip height over a whole cycle
and it is a sawtooth; look at any one frame and it is fine.

Note that the two drawn legs are different lengths and neither splay is zero —
the artist drew a standing pose with the feet splayed ~94 apart. Assume
symmetry and the figure walks permanently astride.

The knee once came from **foreshortening along the limb's own axis** —
`rotate(−θ) · scale(1, k) · rotate(rest)` about the hip, with `k ≥ 0.74` — on
the theory that shortening a leg without touching its width is what a bent leg
looks like in flat art. It is not. A squashed leg is still a *straight* leg, so
it telescopes rather than folds, and the frame `k` hits its floor is the frame
the drawn ankle stops agreeing with the solved one and the shoe separates. The
marching gait and the detached-shoe report were the same bug.

What replaced it is **two-bone IK plus a bone-weighted bend of the outline**
(`remotion/src/lib/legrig.js`). Every outline point is described in the rest
leg's own frame — `s` along the limb, `n` across it — then rebuilt on the posed
thigh and the posed shin and blended over a band of ±10% of leg length at the
knee. Two properties earn it its place:

- Straight and at the drawn angle, both mappings **collapse to the identity**,
  so a leg with nothing to do is the artist's drawing to the last decimal.
- The blend mixes the two bones' **spines**, then offsets by `n` along a
  blended normal *put back to unit length*. Averaging the offset points instead
  — plain linear blend skinning — shrinks the width to `cos(bend/2)`, costing
  13% at a walk's 60° and 33% at a run's 96°: the pinched knee. Re-normalising
  is one square root and holds the drawn width at every angle.

The shoe is exempt — feet do not bend — and stays a rigid child of the solved
ankle, so it cannot detach by construction.

Two details that cost real time:

- `rotate(θ − rest)` is a **reflection about the rest angle**, not a swing to
  it. It is correct at rest and wrong everywhere else, so the figure stands
  perfectly and comes apart the moment it steps. The swing is `rest − θ`.
- Shoes are placed with chains like `translate rotate translate translate`.
  Reading only the last `translate` puts the piece nowhere near the drawing;
  parse the whole transform list into a matrix.

`look.bottom = prepareBottom(asset)` is **required** — there is no procedural
fallback, because a silent fallback is how stick limbs kept reaching the
screen. `HumaaansBench` stands the rig at rest next to the artist's own stacked
composition; at rest the rig must not move a single pixel.

Two libraries, two rigs: `Character.jsx` drives Open Peeps and `Humaaans.jsx`
drives Humaaans, because their proportions differ too much to share geometry
(legs are 43% of standing height against 56%). They share `locomotion.js`,
which is the part that has to agree.

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

### Two gates, not one

This is the distinction that keeps coming up, usually phrased as *"but the free
licence says commercial use and modification are allowed"* — which is true, and
still does not settle it. **Obtaining and using are governed by different
documents:**

| Gate | Document | Question it answers |
|---|---|---|
| Acquisition | site **Terms of Use** | may you *get* the file this way? |
| Use | **content licence** | may you *do this* with a file you lawfully have? |

A permissive content licence never authorises breaching the ToS on the way in.
So when a site answers scripted requests with **HTTP 403**, that is its
anti-robot clause being enforced, and **driving a headless browser specifically
to get past it is circumvention, not a workaround** — the technique is not the
issue, defeating the block is. Fetching the same file from a normal logged-in
session is the user's own call and no business of this skill.

Watch for a third catch even when both gates pass: free tiers commonly require
the asset be a *secondary element rather than the main focus*. In a film whose
characters and backgrounds **are** the product, that clause alone disqualifies
the source.

Headless browsing is not itself suspect — point it at sources that permit
automated access and it is simply a fetcher that runs JavaScript. Use it there.

---

## What imports, and what has to be built

Two independent harvests across five source sites, several hundred candidate
files, all correctly licensed — and the usable fraction was in the single
digits. The failures were not licensing failures. They were **fitness**
failures, and they fell into a stable pattern worth encoding as a rule:

> **Overlays, particles, textures and fonts import cleanly.
> Characters, sets and hero props do not. Build those.**

The reason is resolution and authorship. An imported rain tile or sparkle
sprite has no style of its own to clash with — it is alpha, and this skill
tints it (below). A character carries another illustrator's line weight, eye
shape and proportion into your frame, and the audience sees two hands at work
even when they cannot name the problem.

Run every candidate through this triage **before** downloading it:

1. **Scale it to the size you will actually use it at.** The single most
   reliable filter. Game-sprite characters are authored at 16–120 px; a hero
   figure on a 1080p plate is 400–900 px tall. Blowing one up produces exactly
   the "wrong asset" note that gets a film rejected. Compose the proof — put
   the candidate on a full-size frame beside a rig figure and look at it.
2. **Is it artwork, or a picture of artwork?** Public-domain scans are the
   classic trap: genuinely free, often enormous, and still unusable because
   they are *book pages* — inset illustration, borders, captions, foxing,
   engraving hatch. Reference value, not asset value.
3. **Is it a store listing?** Marketplace previews routinely have ad copy and
   watermarks burnt into the pixels.
4. **Does it have to match anything?** If yes, build it. If it is alpha that
   takes your colour, import it.

Budget accordingly: assume you will **author every character, set and hero
prop**, and treat anything importable as a bonus. That is not a counsel of
despair — authored sets are a few hundred lines and they match by construction.

### Tinting is what makes imported FX safe

Effect packs are greyscale alpha. Used as a **CSS mask over a flat colour**
rather than as an image, they take the shot's palette instead of bringing their
own:

```jsx
<div style={{
  WebkitMaskImage: `url(${staticFile(src)})`, maskImage: `url(${staticFile(src)})`,
  WebkitMaskSize: 'contain', maskSize: 'contain',
  WebkitMaskRepeat: 'no-repeat', maskRepeat: 'no-repeat',
  backgroundColor: color,          // a token from the shot's world
}} />
```

Every particle in a film then resolves to the same palette the sets and cast
resolve to, which is the whole reason an imported sprite can sit in an authored
frame without announcing itself. Verified under Remotion's Chrome; both the
`-webkit-` and unprefixed properties are needed.

**No FX pack is bundled, though, and `SampleFilm` draws its own** — a four-point
star as a single path, and a "glow" built from five concentric discs at rising
opacity rather than a radial gradient, since the style allows one gradient per
film and it is spent on the sky. Two reasons that turned out to be the right
default:

- A film's effects should not be the one thing a clean clone cannot render.
- Drawn sparkles came out **better** than the imported ones. At the sizes FX
  actually play at, a sprite is mostly antialiasing, and the pack's soft edges
  read as blur against this style's hard flat shapes.

So reach for the mask technique when a film genuinely needs something laborious
— rain sheets, smoke, dense embers — and draw anything you can describe in a
path. The bar is lower than it looks.

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
they are deterministic. `StorySets.jsx` does the same for interiors, landscape
and cave, and is the worked example to copy when a film needs a world the skill
has never drawn: a palette object plus a component that spends it.

### Saturation is budgeted by area, not by taste

The style's envelope wants `saturation_mean` in **0.05–0.15** with no more than
**4.5%** of the frame above 0.45. That is not a preference, it is the arithmetic
of the tagline — *soft desaturated air, one figure carrying all the colour*. A
figure cannot carry the colour if the wall behind it is already carrying some.

The failure is always the same and it is always in the scenery, because scenery
is the largest surface in the frame. A warm brown interior that looks perfectly
reasonable as a swatch measured **0.34 mean with 15% hot** — three times the
hot-area budget — and the fix was not to touch the characters at all:

| Surface class | Share of frame | Target saturation |
|---|---|---|
| Air, sky, walls, floor, light shafts | most of it | **0.10 – 0.14** |
| Mid-ground scenery, foliage, beams | next largest | 0.13 – 0.18 |
| Props, furniture, set dressing | small | 0.20 – 0.25 |
| Costume, hero props, FX accents | tiny | **unrestricted** |

Order the surfaces by area, descending, and desaturate from the top until the
metric passes. Keep the hue — the goal is *pale warm grey*, not grey; dropping
saturation to zero produces the washed-out film the crew complains about just as
loudly as the brown one. Check `value_mean` stays in 0.66–0.90 while you do it,
which is what keeps pale from becoming murky.

Naturally dark locations — caves, night — will not reach 0.66 alone and should
not be forced to. Light them to roughly 0.38 and let brighter scenes carry the
film's average.

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
