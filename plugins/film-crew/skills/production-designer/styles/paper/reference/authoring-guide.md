# Authoring guide

How to get from an idea to a board that actually reads.

---

## 1. Write the script to the clock

At ~105 wpm you get **3 words per second**. So:

| Target length | Word budget | Lines |
|---|---|---|
| 15 s | ~28 | 3–4 |
| 30 s | ~50 | 5–7 |
| 60 s | ~105 | 10–14 |

This is a brutally small budget and that is the point. Write the script, count
the words, and cut until it fits. Do not plan to "speed up the read" — the pace
*is* the style.

### Line shape

One idea per line. Lines are short — 6–12 words. Each line should contain
**exactly one word you would put on a chip**:

```
l1  It began on an ordinary Tuesday,                → ORDINARY TUESDAY
l2  in a town that kept very careful records.       → THE RECORDS
l3  Nobody had checked them in eleven years.        → 11 YEARS
l4  So one clerk carried the ledger up to the hall, → THE LEDGER
l5  and set it on the table.                        → THE TABLE
l6  What it showed changed the town.                → (resolution)
```

If a line has no chip-able word, it is probably connective tissue — fold it into
its neighbour.

### Punctuate for the voice

Set `gap_after` to 0.7–1.0 between lines — that silence is where the board gets
to be looked at. Pauses *inside* a line belong to the recording, so ask the
[`voice-booth`](../../../../voice-booth/) skill for them.

---

## 2. Plan beats before you place anything

List them as `(time-reference, what appears)` before opening the layout:

```
l1+0.05   chip ORDINARY TUESDAY
l1+0.45   red box around it
l2+0.15   town hall slides in
l2+0.55   chip THE RECORDS pinned
l2+1.15   ledger stamps down
l2+1.50   red circle around ledger
l3+1.00   chip 11 YEARS
l4-0.15   photo slides up
l4+0.35   red route draws
...
```

Check the spacing: **2–4 s apart**. A gap longer than ~4 s is dead air and needs
a beat; two beats inside 1 s will read as one.

---

## 3. Lay out for the whole timeline, not one frame

The board accumulates and things move. The three collisions that always bite:

1. **A drifting element crosses a parked chip.** Trace the drift path mentally,
   then verify on the contact sheet.
2. **A red annotation lands on artwork.** Red needs clear parchment around it.
3. **Type on a dark silhouette.** Warm ink on a black hill is invisible. Move
   the caption or move the terrain.

### Chips are far wider than you expect

Estimate a chip's width as roughly `size × characters × 0.55` **in design
space**, and it will still surprise you. A 16-character chip at `size: 78` is
about 700 px wide — more than a third of the frame. Three items authored at
`y ≈ 255` because each looked fine alone produced a pile-up of a date chip, a
name chip and a stamp all overlapping.

Put long chips on **different rows**, not merely different columns, and check
the row on the contact sheet before adding the next one.

### Reuse a slot instead of adding a column

A 30-second board cannot hold ten simultaneous elements without silting up. Give
a region of the board a *job* and let successive beats occupy it in turn: a
document panel can carry a clock and a duration chip for beat 3, take both `out`
together, then hold the figures that land in the same place for beat 5.

This reads as a board being worked on rather than a board being filled, and it
keeps each beat's subject near the centre of attention.

### The backing sheet must cover the whole camera travel

If a full-bleed `card` is smaller than the area the camera can reach, its edge
appears mid-shot as a hard vertical seam with a drop shadow. Size it against the
extremes of `camera.moves`, not against 1920×1080:

```
visible_left  = min(at.x − (1920 / zoom) / 2)
visible_right = max(at.x + (1920 / zoom) / 2)
```

and add margin. A backing sheet sized this way is never seen as a sheet, so set
`sides: [0,0,0,0]` and let a smaller *dossier* card supply the visible torn
edges.

### Composition checklist

- Subject on one side, annotation weight on the other.
- Chips in dead space, never over the thing they label.
- Leave the frame edges quiet — the camera pushes in, so edge content leaves.
- Ground your characters. An object that should be standing on terrain must
  actually touch it; compute the surface height rather than eyeballing it.
- Things being *held up* should float. Things standing should not.

### Use the contact sheet

```bash
python3 render.py sb.json --sheet
```

~8 seconds, 20 frames across the timeline. This catches essentially every
layout bug. **Run it after each change.** A full render to check a layout is a
waste of two minutes.

---

## 4. Shape the arc

Even a 25-second piece needs shape.

| Phase | Share | What happens |
|---|---|---|
| **Establish** | 0–20 % | Ground, date/place chip, the first red box. Sparse. |
| **Complicate** | 20–55 % | Subject arrives, the problem is named and circled. |
| **Move** | 55–85 % | Terrain, the red route, physical progress across the board. |
| **Resolve** | 85–100 % | One clear change of state, one `chime`, then the tail. |

The **tail matters**. `"tail": 2.8` leaves nearly three seconds on the resolved
image with only music. That is where the piece lands. Cutting on the last
syllable throws the ending away.

### The resolving beat

Change exactly one thing, and change it visibly: a dark window becomes lit, a
route completes, a redacted line clears. Support it with `halo` + `chime`, and
use the `chime` only there.

---

## 5. Iterate in the right order

1. `--sheet` — layout, collisions, pacing. Cheap, run constantly.
2. `--frame T` — texture and detail at full resolution.
3. `--clip A B` — **the only way to judge motion.** Renders seconds `A`–`B`
   silently at full resolution and prints the largest single-frame change in
   the range. A contact sheet cannot tell a pan from a cut, and a full render
   is far too slow a loop for camera work.
4. `--motion N` — estimates the mean-frame-difference check from `N` sampled
   frame pairs in about a minute, instead of ~40 minutes. It reads roughly
   0.15 high, so aim for ~1.65 to land a true 1.5.
5. `--preview` — motion and timing feel, half res. Writes to
   `<output>_preview.mp4`, so it never clobbers a finished render.
6. Full render — only when the others are right.

### Reading `--clip`'s single-frame number

The printed figure is mean luma difference between adjacent frames. A large
value on its own means nothing: **the shape matters.**

- A **cut** is one isolated spike with near-zero either side.
- A **pan** is a smooth hump that ramps up and back down over ~20 frames.

The board is high-frequency paper grain, so even a slow, entirely comfortable
pan shifts every pixel and scores 15–20. Judge the profile, never the peak.

### Running the full render

A feature-length board takes ~50 minutes, so run it detached and watch the log
rather than holding a shell open:

```bash
nohup python3 render.py sb.json -o film.mp4 --force > /tmp/render.log 2>&1 &
tail -c 300 /tmp/render.log | tr '\r' '\n' | tail -1
```

Two things that waste a whole render if you get them wrong:

- **`render.py` auto-versions its output.** Without `--force` a second run
  writes `film-002.mp4` and leaves the file you were about to inspect
  untouched — you end up verifying the *old* cut and concluding the fix did
  nothing.
- **Killing the wrapper does not kill the render.** `nohup … &` gives you the
  shell's pid, not Python's; the render carries on writing frames. Find the
  real child and kill that:

  ```bash
  ps -eo pid,ppid,command | grep '[r]ender.py'
  ```

If you spot a defect mid-render, stop it. Twenty-three per cent of a doomed
render is cheaper than a full one you will throw away.

Then verify:

```bash
ffprobe -v error -show_entries format=duration,bit_rate \
  -show_entries stream=width,height,r_frame_rate,pix_fmt \
  -of default=noprint_wrappers=1 out.mp4
ffmpeg -nostdin -i out.mp4 -af ebur128=peak=true -f null - 2>&1 | tail -12
```

Duration < target · 1920×1080 @ 30 · I ≈ −14.0 LUFS · true peak ≤ −1 dBTP.

---

## 6. Building the depth, not just the layout

A storyboard that places elements correctly can still render flat. Three passes
turn a layout into a physical board.

**Stack it.** Decide what is lying on what, then assign `elevation` so the pile
is unambiguous — backing sheet lowest, subject highest. If two touching layers
share an elevation, the depth cue cancels.

**Attach it.** Real boards have furniture: masking tape at the corners of a
sheet, a push pin through a card, rotated marginalia along the edges, a coffee
ring in dead space. These cost one line each and do more for believability than
any amount of tuning on the main artwork.

**Move it.** Every element gets a `float`; every beat gets a `camera` move; the
subjects arrive with `"anim": "fly"` rather than fading in. Then measure — the
mean-frame-difference check in
[troubleshooting.md](troubleshooting.md#it-reads-as-a-slideshow) is the fastest
way to know whether the piece is actually alive or merely looks busy in stills.

**Two traps worth knowing.** Seeds must be unique — they identify elements for
randomisation, and duplicates make edits land in two places at once. And a large
`card` used as a backing sheet becomes the palette for most of the frame, so it
has to be warmer than feels right in isolation and should bleed off an edge
rather than framing the video.

---

## 7. Adapting the style to other subjects

The look is not tied to any one genre. It carries any subject that benefits
from *evidence*: history, geopolitics, science explainers, post-mortems,
case studies.

What changes:

| Subject | `music.mood` | Artwork | Chips |
|---|---|---|---|
| Children's story | `music_box`, major | characters, terrain | plain nouns |
| Investigation | `tension`, minor | maps, documents, redactions | dates, place names, numbers |
| Science | `warm`, dorian | diagrams, apparatus | terms, quantities |

What never changes: no cuts, one red, chips on the word, ~105 wpm, −14 LUFS,
and paper that has thickness.

To add artwork, write a function in `illustrations.py` that returns an RGBA
`Image` and add a branch to `render.make_art`. Build it from the same
primitives — flat warm-ink silhouettes, cream highlights, a `_spline` for
anything organic — and it will match automatically once `sticker()` wraps it.

### When the subject is real violence

The evidence-board look is persuasive, which is exactly why it has to be
handled carefully when the events are real. The rules:

- **Report, do not dramatise.** No weapons, no injuries, no perpetrator names or
  affiliations, no re-enactment of the act itself.
- **Anchor on the place and the people, not the act.** Make the setting the
  subject and find the human beat inside it.
- **Let the figures stand alone.** Set casualty numbers as bare chips with a
  small caption, hold real silence around them, and do not stack them with a
  musical sting.
- **Close on what followed**, not on the worst moment.
- **Check every number**, and prefer a phrasing you can source. "Within a month"
  survives scrutiny where an exact interval invites an argument.

Expect the read to be slower in this register, and let it be: widen `gap_after`
rather than adding words. Pair it with the `crime` bed — see
[audio-style.md](audio-style.md).
