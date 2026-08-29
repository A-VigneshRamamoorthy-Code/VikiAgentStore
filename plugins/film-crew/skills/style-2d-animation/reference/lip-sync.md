# Lip sync

A character who talks with a closed mouth is the single most obvious tell that
a film was assembled rather than animated, and it is also the defect most
likely to survive every check you have. This document is the post-mortem of a
three-minute film that shipped **4163 frames of mouthless faces** while its
render log printed `OK`, its loudness was on target, its a/v drift was
`0.000s`, and its frozen-run audit passed.

The lesson underneath all of it:

> **A missing mouth is not a crash. Every layer in the path was designed to
> carry on without one, so every layer did.**

---

## The mouth is not on the head

Start here, because it inverts the natural assumption. Commercial character
kits — the ones that advertise "all possible mouth movements" — draw the face
**without a mouth** and ship the mouths as separate parts. The neutral head is
a complete drawing of eyes, nose, brows and cheeks, and where the mouth goes
there is bare skin.

That is a sensible way to sell a kit and a trap for a rig, because a rig loads
`head.png`, gets a face, and has no way to notice that the face is incomplete.

```bash
# Look at the base part before you build anything on it.
python3 -c "from PIL import Image; Image.open('rigs/emma/head.png').show()"
```

Two consequences, and the second is the one that bites:

- The `rest` viseme is **not optional**. It is the closed mouth, and it has to
  be composited even when nobody is speaking. A rig with no viseme applied is
  not a quiet character, it is a character with no mouth.
- Therefore **never let a non-speaking frame fall through to the base head.**
  The default is `rest`, not "nothing". In the film this document is about, the
  narrator speaks over most shots, so the characters on screen were not
  speaking, so they fell through — and the bug was invisible in exactly the
  shots where a person would look hardest at the face.

---

## Four independent causes, each sufficient on its own

The mouth was dead for four separate reasons. Any one of them alone produces
the identical symptom, so fixing three of them changes nothing you can see —
which is precisely why this took four render cycles to clear. Diagnose all the
way down before you fix anything.

### 1. The viseme names did not match the consumer's vocabulary

The generator emitted `"oh"` and `"talk"`. The consumer matched against a set
containing `A E I O U MBP FV L rest`. Unknown names were **discarded rather
than rejected**, so the head selector received nothing and returned neutral.

Any place that maps a string to art is a place two vocabularies can silently
disagree. Make the mapping total and make the failure loud.

### 2. The target art did not exist

`head_grin.png`, `head_smile.png` and `head_joy.png` were `shutil.copy2` of
the neutral head — placeholders from an earlier stage that nobody had gone
back to. The rig reported eight expressions. It had one.

**Content hashing does not catch this.** A later preprocessing pass rewrote
every `head*.png` (it was splitting the character's back hair into its own
part), so the placeholder copies were no longer byte-identical to the neutral
head while remaining visually identical to it. A dedupe step ran, found
`skipped_duplicates: 0`, and reported success.

> Only a contact sheet tells the truth about whether two drawings differ.
> Render them side by side and look.

### 3. The timing data was never written

The voice directory held wavs and one `intelligibility.json`. The per-line
sidecars the lip sync reads had **never been generated at all**. The lookup
iterated a single track named `intelligibility`, matched nothing, and returned
`None` for every frame of the film.

Fixing causes 1 and 2 without this one still yields a closed mouth. That is
what makes this class of bug expensive: the fixes are not independently
verifiable.

### 4. The art was on disk, correct, and never loaded

This is the subtlest and the most general, and it is worth stating as a rule
rather than an anecdote.

The variant loader scanned the rig directory for `<part>_<label>.png` and
split each filename **on its last underscore**, because part names like
`hand_r` contain underscores. Given `head_vis_rest.png` it therefore derived
part `head_vis`, looked for `head_vis.png` to anchor it, found none, and
**skipped the file**. All 72 baked lip-sync heads were dropped on the floor at
load time.

The accessor then completed the disaster:

```python
def get(self, part, label, base_img=None):
    """Falls back to the base image if the variant does not exist."""
```

So `get("head", "vis_rest")` returned the mouthless base head, and the caller's
guard —

```python
got = art.get("head", name)
if got is not None:          # can never be false
    return got
```

— could not fire, because a forgiving accessor never returns `None`.

**Fix both halves.** Parse against the rig's declared part list rather than
against punctuation:

```python
rig_parts = sorted(json.load(open("rig.json"))["parts"], key=len, reverse=True)
part = next((p for p in rig_parts if stem.startswith(p + "_")), None)
label = stem[len(part) + 1:]
```

Longest declared part wins, so `hand_r_point` → `hand_r` + `point` while
`head_calm_vis_a` → `head` + `calm_vis_a`. Labels may then contain underscores,
which is what lets a variant name encode two axes at once.

And give callers a way to ask the other question:

| method | question | on a miss |
|---|---|---|
| `get(part, label)` | "give me something to draw" | returns the base art |
| `has(part, label)` | "is the art I asked for present" | returns `False` |

Use `get` for decoration. Use `has` anywhere a missing variant means the shot
is **wrong** rather than merely plain, and raise:

```python
if art.has("head", name):
    return art.get("head", name)
raise KeyError(f"rig is baked for lip sync but has no variant for {vis!r}")
```

---

## Building a viseme library from a kit

If the character kit ships a lip-sync sheet, use it: hand-drawn mouths carry
teeth, tongue and lip thickness that no procedural ellipse will give you.
Getting them out of the kit has three traps, and all three were hit in order.

**The mouths are drawn on a skin-coloured swatch, not on transparency.**
Rasterising the EPS with `gs -sDEVICE=pngalpha` returns a crop that is **fully
opaque** — alpha 255 everywhere, corners reading `(237, 205, 187)`. A flood
fill seeded with white keys nothing at all. Check the corner pixel before
assuming a background colour:

```bash
python3 -c "
from PIL import Image; import numpy as np
a = np.asarray(Image.open('/tmp/sheet.png').convert('RGBA'))
print('corner', a[0,0], 'alpha range', a[...,3].min(), a[...,3].max())"
```

**A border flood fill eats the open shapes.** Re-seeded from the four corners
on the real backdrop colour, the ink percentages look plausible — until you
grade them and find `I` at 27% and `O` at 17%. Those two mouths are open at
the corners, so the fill leaks *through* the shape and consumes the lips. The
numbers do not reveal this. A contact sheet on a contrasting ground does.

**The recipe that works** takes geometry from one source and coverage from the
other: high-resolution **RGB from the EPS**, **alpha from the kit's own PNG
cutout**, upscaled. The low-res mask is exactly the bounding-box crop of the
same artwork, so it registers without any offset hunting.

```bash
gs -dNOPAUSE -dBATCH -sDEVICE=pngalpha -r288 -sOutputFile=/tmp/kit.png kit.eps
```

At `-r288` a full kit sheet came out 13923×10757 in six seconds, so there is
no reason to work from the low-resolution preview.

### Scale every viseme by one factor

The artist drew `O` wider than `I` because `O` **is** wider. Normalising each
shape to a common width destroys exactly the information you extracted the
library for. Record one reference width for the set and scale them all by it.

```python
WIDTH_FRAC = {"rest": 0.24, "MBP": 0.26}   # narrower, so silence does not pop
DEFAULT     = 0.30                          # fraction of head width
```

`rest` and `MBP` are deliberately narrower than the rest: the cut from silence
into the first syllable is the most visible frame in any lip sync, and a `rest`
as wide as an `A` makes the mouth appear to *close* as speech begins.

### Name the variants in lower case

macOS is case-insensitive by default, so `head_A.png` and `head_a.png` are the
same file and the second bake silently overwrites the first. Use `vis_a`,
`vis_mbp`, `<expression>_vis_<viseme>`.

---

## Anything socketed near a feature will cover it

The wizard's mouth was correct, composited, and completely invisible. His
beard's socket was `[146.5, 278.2]`; his mouth centre was `[146.5, 279.03]` —
the same point to within a pixel — and the draw order was `[… head, beard, hat]`.

The beard was drawn over the mouth, every frame, exactly as instructed.

Measure the feature's real footprint before deciding where the neighbour goes.
Diff the baked variants against the base to get it exactly, rather than
estimating from the art:

```python
b = np.asarray(Image.open("rigs/wizard/head.png").convert("RGBA")).astype(int)
for v in VISEMES:
    g = np.asarray(Image.open(f"rigs/wizard/head_vis_{v}.png").convert("RGBA")).astype(int)
    ys, xs = np.nonzero(np.abs(g - b).sum(2) > 24)
    print(v, "rows", ys.min(), ys.max())
# widest shape reached row 301; the beard's ink top sat at 295 and clipped it
```

Then seat the neighbour clear of it, remembering that a part's ink and its
pivot are not the same point — this beard's ink began 13.16px **above** its
own pivot, so the socket had to be that much lower again.

> Whenever you animate a feature, list every part whose `zorder` puts it
> later and whose socket is within that feature's footprint.

---

## Deriving the timing

Two sources, and you want both:

- **Text → visemes** gives the correct *shapes* in the correct order.
- **The wav's RMS envelope** gives the correct *timing* and, critically, the
  silences.

Pair them: walk the viseme sequence against the measured envelope and gate on
amplitude, so the mouth closes when the actor stops rather than when the
sentence ends.

```python
SILENCE = 0.12          # of peak RMS; below this the mouth returns to rest
```

Sanity-check the result as a **distribution**, not as a boolean. A healthy
speaking shot has the mouth open on roughly half its frames:

```
mouth open on 54% of speaking frames (per-line range 27-74%)
```

100% means the gate is not working. 0% means nothing is wired up. Both look
identical in a log line that only says `OK`.

Match on `(line_id, speaker)`. Matching on "any track whose name starts with
the shot id" makes both characters in a two-hander lip-sync to whoever speaks
first.

---

## Blinking is easy to delete by accident

Many rigs implement a blink by swapping to a `calm` head, because `head_calm`
*is* the eyes-closed drawing. If the head selector you are replacing did that
implicitly, replacing it removes blinking from the film and nothing will
report it.

Route it through the bake instead, so both axes survive:

```python
base = "calm" if openness < 0.5 else expression
for name in (f"{base}_vis_{vis}", f"vis_{vis}"):
    ...
```

This is why the bake is a **product** of expressions and visemes rather than a
list of visemes: 8 expressions × 9 visemes = 72 heads per rig. Bake them all;
they are small and the alternative is discovering the gap mid-film.

---

## Verify

Automated audits cannot see this defect. Every one of them passed while the
film was broken. Use them to catch regressions in things they can measure, and
use your eyes for the mouth.

**1. Grade the bake on a contact sheet.** Before rendering a single frame.

```python
visemes.contact_sheet(rig, out="/tmp/bakes.png")
```

Every shape must read as a *different* mouth. If two are indistinguishable,
reassign them — after grading this library by eye, `O` and `U` were swapped to
different source parts.

**2. Confirm the variants actually loaded.** The bug in cause 4 is invisible in
every artefact; it is only visible here.

```python
base = art.get("head", None)
for name in ("vis_rest", "vis_a", "calm_vis_rest"):
    assert art.has("head", name), name
    assert not np.array_equal(art.get("head", name), base), f"{name} == base"
```

That second assertion is the one that matters. `has()` can pass while the
image is still the base if the loader registered it wrongly.

**3. Look at the mouth in the delivered file.** Not the frame buffer, not a
test render — the mp4 you are about to hand over.

```bash
# -ss BEFORE -i seeks to the nearest keyframe and will not give you frame n.
ffmpeg -y -i film.mp4 -vf "select='eq(n\,435)+eq(n\,440)+eq(n\,445)'" \
       -vsync 0 /tmp/f_%02d.png
```

Crop to the face and lay the frames out in a strip. Six consecutive samples
from one line of dialogue should show six mouth shapes. Do not measure "the
frames differ" — a moving camera and an ambient layer make every frame differ,
and that statistic will happily report a healthy film with a dead mouth.

Find the face by skin colour rather than guessing a crop box:

```python
r, g, b = a[...,0], a[...,1], a[...,2]
skin = (r - b > 25) & (r - g > 12) & (r > 120)
```

Beware that warm-toned sets — attic wood, sepia interiors — satisfy that test
too. If the reported bounding box is the full frame width, it caught the
background; tighten the threshold or restrict to the character mask.

**4. Gate it automatically — by differencing against a forced-rest render.**

Everything above still ends in "use your eyes", which does not scale and does
not survive a refactor. There *is* an automatable test, and it works because it
compares two renders instead of two frames.

Render each speaking shot twice: once normally, and once with `_viseme_at`
patched to return `rest` for everything. Both runs share the identical camera,
ambient layer, blink schedule, set and seeds, so **the difference between them
is exactly the lip sync and nothing else**. A mouth that never moves makes the
two renders byte-identical. The moving camera that defeats every frame-to-frame
metric is now common to both sides and cancels exactly.

This is only meaningful on a deterministic renderer — see
[`verification.md`](verification.md). On a non-deterministic one it reports
motion on a still face, which is the same failure it was written to prevent.

**Find the mouth by shape, not by size or magnitude.** The raw difference is
not only the mouth. An ink pass that normalises by the global frame maximum
responds to *any* change: opening a mouth introduces a strong new edge, lowers
every other normalised gradient slightly, and flips borderline pixels along the
character's **entire silhouette**. That artefact is full-height and full-
magnitude — it survives both a magnitude threshold and a 3×3 opening — so
bounding-box area and pixel count both report a "moving region" of 10% of the
frame on a film whose mouths are working perfectly.

The mouth is separable because it is *compact*: a dense blob about 50×22 px and
80–90% filled, while the artefact is a long thin curve enclosing an enormous
box. Take connected components, keep the largest that is at least 30% filled,
and ignore the rest. Measured across one film that component stayed within
11 px of one spot all shot and never exceeded 0.09% of frame area.

Three exemptions are legitimate, and each is a real property of the shot rather
than a way to quieten the report: a **narrator has no body**, a **prop has no
mouth art**, and a **held cel is one frozen drawing by design**. Anything else
must sync.

Report sparseness, don't fail it. Across one film's thirteen on-screen lines
the mouth sat at `rest` for a median 50% of frames and a maximum 73% — a
continuous spread with no natural break — so failing at the sparse end is a
false alarm. Fail only what is genuinely not syncing (the defect this exists to
catch scores exactly 0), and warn in the band above it, naming the line's rest
fraction so the note is actionable.

Finally, **prove the gate can fail**: run it with every mouth forced shut and
require it to reject the film.

---

## Checklist

- [ ] The base head has been **looked at**; if it has no mouth, `rest` is
      composited on every frame including silent ones
- [ ] Viseme vocabulary is identical at the producer and the consumer, and an
      unknown name raises
- [ ] Expression heads are visually distinct on a contact sheet, not merely
      distinct by hash
- [ ] Timing sidecars exist for every line, and mouth-open sits near 50%
- [ ] Every baked variant loads and differs from the base array
- [ ] No later-drawn part is socketed inside the mouth's measured footprint
- [ ] Blinking still happens after any change to head selection
- [ ] A frame strip cropped to the face, taken from the **delivered** file,
      shows the mouth changing shape
