# Patching a look onto a shared engine

This style has no renderer. It borrows `style-paper`'s and replaces the four
functions that decide how a drawing looks, leaving the ~46 illustrations, the
staging grammar, the motion tiers, the scoring and the mix exactly as they
are.

That is a deliberate trade:

- **What it buys.** Every illustration renders flat for free, and a new
  illustration added for one style arrives in both. A fix to staging or
  scoring is a fix for both films. And because the two styles compile
  identically, the same storyboard renders in either — which is what makes an
  A/B honest, since the edit, the timings and the staging are literally the
  same file.
- **What it costs.** Flat vector gets no per-shape control of its own: no
  gradients inside a shape, no outline weights, no bespoke geometry. Here that
  costs almost nothing, because the style's own rule is that shapes are
  untextured, unoutlined and unshaded — but a style that *did* want its own
  geometry would need its own renderer rather than this.

## The four substitutions

| paper | flat | effect |
|---|---|---|
| `paper.parchment` | `look.colour_field` | mottled aged stock → one two-stop gradient |
| `collage.sticker` | `look.flat_sticker` | white cut-out border + contact shadow → nothing |
| `paper.add_grain` | `look.no_grain` | fibre noise → nothing |
| `collage.label_chip` | wrapped | inherited ink → a forced high-contrast pair |

Plus two table rewrites: `PALETTE` (mutated in place) and every module-level
function's captured colour defaults.

---

## Four traps, each of which this file fell into first

Everything below was a real bug, found by rendering a frame and looking at
it. They are recorded because each one is **silent** — the film renders
successfully and simply comes out wrong, so nothing fails and no test goes
red.

### 1. `import render` inside a file named `render.py` imports itself

Python prepends a script's own directory to `sys.path`, so from
`style-flat/scripts/render.py` the name `render` resolves to *itself*, not to
the engine.

The symptom is maddening: the film renders, and the patches appear to do
nothing. What is actually happening is that the patches are applied to one
set of module objects while a **second copy** of the engine draws the frames.

```python
spec = importlib.util.spec_from_file_location("paper_render", path)
```

Load the engine by **path**, never by name. Same for `compile.py`.

### 2. `from paper import PALETTE` binds the dict object

`illustrations.py` does exactly that at import time, so it holds a reference
to the dict. It must be **mutated**:

```python
paper.PALETTE.update(flat)        # correct
paper.PALETTE = flat              # wrong — illustrations keeps the old table
```

`illustrations.INK` is a separate module-level name and has to be set
independently.

### 3. Default arguments capture colour at import time

```python
def marker_rect(size, box, ..., color=PALETTE["accent"]):
```

A default is evaluated **once**, when the module is imported. Updating
`PALETTE` afterwards does nothing for it. This is why the first flat render
came back with a cream note card sitting on a near-black field: the field had
been repainted and the card had not.

`_retint_defaults()` handles it generically — build a map of *old palette
value → new palette value*, then walk every module-level function and rewrite
`__defaults__` and `__kwdefaults__`. It cannot help with colours written as
literals inside a function body (the hill's snow cap, for one); those either
have to be left alone or the function replaced.

### 4. `parchment` has two kinds of caller

The frame-sized **field**, whose colour this style owns, and small
**surfaces** — caption chips, note cards, labels — which pass a stock colour
because they mean it.

Ignoring the caller's colour for both made every caption card the same
near-black as the field behind it. Honouring it for both put paper stock back
as the film's background. Size is what separates them: nothing but the board
is frame-sized.

---

## Verifying a look change

Render a **contact sheet** before rendering a film. It is a few seconds
against a few minutes, and every defect this style can have is a defect you
can see in one still:

```bash
python3 scripts/render.py sb.json --sheet -o sheet.jpg
```

What to look for, in order:

1. **Figure/ground.** Can you find the subject in every tile? This is the
   style's weak point, because paper's white border was doing separation work
   for free.
2. **Caption legibility.** Dark text on a dark chip is the failure mode.
3. **Colour.** If the sheet reads as one colour, the palette is not reaching
   the elements — check `restyle()` before blaming the palette.
4. **Empty tiles.** A near-empty frame is a *board* problem, not a look
   problem; fix it in the beat plan, where it will fix both styles at once.

Do not verify a look by counting what was emitted into the storyboard. A
count of specs is not evidence of a visible change — this project has twice
shipped a "fix" that was present in the JSON and invisible on screen.

---

## Motion measures lower in this style, and the motion is still there

`motionprofile.py` scores a flat film roughly **0.6×** what it scores the
paper film *of the same storyboard*. Measured on one board: mean 1.46 for
paper, 0.92 for flat, with identical timings, identical staging and an
identical motion plan.

That is a property of the measurement, not of the film. The metric is a mean
absolute pixel difference between consecutive frames, and:

- **A camera move across a smooth field barely changes any pixels.** Paper's
  ground is mottled stock with grain, so panning it lights up every pixel in
  the frame. Flat's ground is a two-stop gradient, so panning it changes
  almost nothing. Since the field is by far the largest area on screen, it
  dominates the mean.
- Flat actually has *more* spatial detail than paper (5.02 vs 4.73 on the
  same board) because its edges are hard. But edges are a small fraction of
  the area, so they cannot make up the difference.

`style.json` therefore carries its own thresholds — `motion_mean_min` 0.85
against paper's 1.5 — rather than borrowing paper's. Compare a flat film to
other flat films, or better, use `--compare` against the same board rendered
in paper and check the *shape* of the distribution rather than its
magnitude.

