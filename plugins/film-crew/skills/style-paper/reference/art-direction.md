# Art direction: staging, movement and colour

This is the layer that decides *what is on screen and where*, as opposed to
[`visual-style.md`](visual-style.md) (how a drawing looks) and
[`../../animation-director/`](../../animation-director/) (how much it moves).

It exists because a compiler that gets the timing perfect can still produce a
film nobody wants to watch. The failure mode is specific and it is worth naming,
because it is what this document is written against:

> Every beat drew one keyword-matched cutout, alone, in one of two positions,
> in one fixed palette. A story about a woman climbing a hill with a lantern
> became a picture of a woman, then a picture of a hill, then a picture of a
> lantern — three separate objects, none of them touching, none of them
> anywhere. Journeys never happened. Timelines had no dates on them. Twenty-five
> art elements resolved to fifteen drawings in two columns.

Every rule below is a repair to one part of that.

---

## 1. A shot is a scene, not an object

`pick_cast()` reads the whole line and casts up to four drawings by **role**,
then `staging.stage()` arranges them into one coherent picture:

| role | what it is | where it goes |
|---|---|---|
| `ground` | the place — hill, stairs, room, road, sea | sits on the ground line, widest element |
| `actor` | who or what moves — figure, boat, plane, car | stands *on* the ground line |
| `prop` | what is held or used — lantern, book, key | beside the actor, scaled to hand height |
| `atmos` | weather over everything — snow, smoke | full frame, high z |
| `sky` | what is behind — moon, star, halo | upper third, low z |

The ground line (`staging.GROUND_Y = 0.775`) is the whole trick. Once every
element is placed relative to one horizon, a figure and a hill and a lantern
stop being three stickers and become *a person standing on a hill holding a
lantern*. That is the same picture the sentence describes, which is the entire
job.

**Consequence for authors:** write beats as sentences, not nouns. `"she climbed
the hill with the lantern"` casts three elements into one scene. `hint: lantern`
casts one object floating in space.

## 2. The background belongs to the scene, and is held

A background is established **once per act** and held for the whole act: no
exit, no re-entrance, no idle float. Only the actors in front of it change.

This is the oldest trick in limited animation and it buys two different things
at once:

- **It is cheap.** The expensive layer is drawn once and reused for a dozen
  shots, which is the premise the entire `animation-director` budget rests on.
- **It is legible.** Once the ground stops changing, the eye reads whatever *is*
  changing as the subject. Motion means something only against stillness.

Re-picking a setting from every individual line produced the exact opposite. It
looked busy and measured as noise: every beat tore down and rebuilt its whole
world, so a quiet beat churned as hard as a loud one and the film had no motion
contrast left to spend. Acts are the scene boundaries the plan already declares,
so the compiler groups beats by act, casts the setting from **everything the act
says** rather than from one line of it, and emits it as `sc<act>_<n>` with a
long `out`.

Beats inside an act therefore cast *no* ground, atmos or sky of their own — the
scene already shows where this is, and a second hillside on top of the first one
is not a second location, it is a mistake.

> If a story genuinely changes location mid-act, that is a missing act boundary
> in the beat plan, not a compiler problem. Split the act.

## 3. A journey has to happen on screen

If a line describes travel, something must cross the frame. Not a cut to a
different picture of the same person — actual lateral movement.

`staging.motion_of()` detects the medium from the verb, and the **actor** (never
the ground) gets a `drift`:

| medium | verbs | typical mover |
|---|---|---|
| `foot` | walk, climb, run, wander, march, trudge | `figure` |
| `water` | sail, row, drift, cross, ferry | `boat` |
| `air` | fly, soar, glide, rise | `plane` |
| `road` | drive, ride, race | `car` |

Two rules make this fire as often as it should:

- **Match stems, not words.** `climb|climbs|climbed|climbing` is one verb. The
  first version matched exact words and caught 4 lines out of 24.
- **A journey needs a traveller.** Prose routinely describes travel without
  naming who is doing it — *"for whoever was still walking home"*, *"had carried
  it up for forty-one years"*. A literal reading casts nobody, so the one shot
  that most needs to move is the one that cannot. If a line travels and names no
  actor, cast one. This alone took drifts from 2 to 10 on the test film.

The mover also **enters from the direction it is travelling** (`anim: "slide"`,
`from_x` set against `facing`) rather than dropping in from above, which reads
as *arriving* rather than *appearing*.

For a route that is described rather than performed — a flight path, a supply
line, a chain of custody — use `thread` with real `points`. See §4.

### A climb is not a walk

`climb` and `descend` are their own media, not a flavour of `foot`. Left in the
ground group they inherited `rise: 0.0`, so a line about someone climbing three
hundred and twelve steps was drawn as a figure sliding sideways. Two details
make the distinction hold:

- **Test the vertical verbs first.** Every climb verb is also a walking verb —
  *"she climbed the stairs"* matches the ground pattern too — and the first
  match wins.
- **Measure the ascent against the thing being climbed, not the frame.** A
  fixed `-0.40 * H` rise put the figure in the sky above the staircase.

The thing being climbed is a **ramp** (`staging.RAMP`), and it is scenery rather
than a hand-prop or far distance. `stairs` and `hill` are both grounds, so a
beat naming both used to put the hill on the ground line and shunt the staircase
into the `ground_far` slot — smaller, higher, offset — producing a small ladder
floating in the sky beside a hill with the figure hovering next to neither. A
ramp is laid *onto* the slope, spanning its near flank from foot to apex, and
the figure's `travel` is measured along the ramp's own box.

Two consequences that are easy to get wrong:

- **The act's held background counts.** When the staircase is the scene, the
  climbing beat has no ground of its own, so the compiler passes the scene's
  staged ramp in as `ramp_box`. Without it the figure falls back to a
  frame-relative guess and stands beside the steps.
- **Ascent follows the drawing, not `facing`.** The staircase is drawn rising
  to the right, so a climb travels up-and-right and a descent down-and-left
  whichever way the rest of the beat faces. Reading the direction from `facing`
  sent the figure up the *back* of the steps, moving left while the treads rose
  right.

### Behind is not beside

`staging.depth_of()` returns `"pursuit"`, `"distance"` or `None` — and the two
positives are **not** the same thing.

- **Pursuit** is a relation between two things (*"behind her"*, *"following
  him"*). A sentence naming only one of them still means both are there, so if
  the beat casts one actor, cast the companion.
- **Distance** is one thing placed far away (*"far out"*, *"on the horizon"*).
  Conflated with pursuit, *"far out, a fishing boat was making for the
  harbour"* cast a **second** boat to stand in front of the first, so the shot
  said two boats.

Depth needs three cues at once — **smaller, higher up the ground plane, and
overlapped**. The third is why `upstage` is exempt from collision separation:
left in the collision set, `_separate` shoved the upstage figure sideways until
the two stood shoulder to shoulder, which is the defect it exists to prevent.

**Which thing is the far one depends on what is already on screen.** A distance
line with nothing else staged puts its single subject upstage. But when an act's
setting is *held*, the setting is usually the distant thing and the actor is the
near one: *"out at sea, the boat turned four degrees"* is the view **from** the
boat toward the lit hill, not a view of a tiny boat. Staged upstage the boat
shrank and rose while the full-size hillside behind it did not, so the two read
as standing side by side — reported as *"the mountain and the flame isn't shown
at a distance"*. With a held scene the actor therefore stays downstage and is
drawn `NEAR_SCALE` **larger** than normal, because depth is relative and making
the foreground bigger is the only lever available when the background is scenery
and cannot shrink.

Related: shapes that stand on the ground line (`_GROUNDED`) may only be
separated **sideways**. Lifting an actor off the ground line to resolve an
overlap makes it float, which is a worse defect than the overlap.

## 4. A diagram must be *of* something

A chronology with no moments on it, a clock with no time on it and a route
joining nowhere are decorations that merely resemble information. They are worse
than nothing, because they invite the viewer to read data that is not there.

If a beat puts a diagram on screen, the compiler fills it from the plan:

| drawing | field | filled from |
|---|---|---|
| `timeline` | `ticks` as `(y, major)` **pairs** + `labels` + `progress` | the plan's own **acts** — a story's real moments |
| `clock` | `hours` | a time named in the line (`midnight`, `half past four`, `19:40`) |
| `thread` | `points` | a route generated for the line's medium |

`progress` is where the film currently sits in the story, so a timeline shown in
act three is filled to act three. That is the difference between a chart and a
squiggle.

> `route_thread(points)` takes fractions **of its own tile**. A map and its
> thread need an *identical* box or the route misses the pins.

## 5. Colour comes from the story

Every film used to be the same browns with a `#c8402a` accent, because those
were literals inside the compiler. `palette.py` picks one of eight from the
story's own subject and mood:

| palette | accent | reads as |
|---|---|---|
| `sepia` | `#c8402a` | archive, memory, the default |
| `ash` | `#5b7f9c` | cold, institutional, winter |
| `ember` | `#d2691e` | firelight, warmth against dark |
| `tide` | `#2e7d75` | sea, distance, voyage |
| `dust` | `#b5651d` | desert, drought, roads |
| `moss` | `#5a7d3a` | growth, countryside, the living |
| `bone` | `#7a8794` | clinical, forensic, absence |
| `noir` | `#a8231c` | crime, threat, blood |

A palette is a *film-wide* decision, like the mood. Changing it mid-film makes
one film look like two.

### The largest surface wins

Picking a colourful palette is not the same as making a colourful film. The eye
grades a frame by area, so a saturated accent on a beige ground reads as beige.
Two surfaces are bigger than anything the palette-picker touches, and both had
to be fixed separately after viewers still called the result "grey or brown":

- **The stock** (`paper_light` / `paper_deep`) is the biggest area in every
  frame. It measured S 0.05–0.53 at L 0.73–0.89 — beige and pale grey. It now
  sits at S 0.22–0.74. Note that **lightness mattered as much as saturation**:
  `ember` measured S 0.53 but L 0.78, which reads as beige regardless.
- **Scenery** is the next biggest. It used to return the film's single `ink` so
  that a place would not shout over the figure standing on it. The reasoning is
  right; the conclusion was too strong. Every landscape in every act was the
  same near-black rectangle, so a film that visited four places looked like one
  place. A setting is now cut from a real sheet and then *pushed back* toward
  the ink by `SCENERY_RECEDE` — coloured enough to tell one act from the next,
  muted enough to stay behind the actor.

Index scenery by **scene** as well as by position. Every scene's first element
is `si = 0`, so indexing on position alone gave all four acts the same ground.

**The defaults are a surface too, and they were the largest one of all.** Both
fixes above were correct and the finished films were *still* brown, because two
places bypassed the palette entirely:

- The full-bleed board card — the sheet everything is pinned to, and by area the
  largest object in every single frame — was created with a **hardcoded beige**
  rather than the chosen stock. The palette was being applied faithfully to the
  drawings and then buried under a beige sheet.
- Every `spec.get("color", …)` fallback in the renderer resolved to the module
  default palette, which is the same beige. Chip backgrounds, cards and tape all
  land on top of the artwork, so they read strongly.

Measured on a teal-palette film: finished frames averaged **19% saturation at
hue 53° (brown)** against a palette that was 46% saturated. After binding both
to the board's own stock, the same film measured **hue 160° (teal)**.

The lesson generalises past this style: *a palette is only as good as its least
disciplined default.* When a film comes out the wrong colour, do not re-tune the
palette — go and find what is painting over it.

### A fixture is not a place

Every act holds one setting. Choosing it on mentions alone puts a **staircase**
on the pinboard as the setting of an act about climbing 312 steps — and a
staircase is not somewhere you can be, it is something bolted to somewhere.
The hill it was cut into then gets demoted to a passing beat, leaves when that
beat ends, and the steps are left standing in open water long after the story
has put to sea. That is the "stairs shown in the water" defect exactly.

Two rules follow, and both are needed:

- A fixture is held back behind every real ground, and is the setting only if
  the act names nothing else at all (`staging.FIXTURE`).
- **A fixture implies its host.** An act whose only new ground is a staircase
  has not moved to a new place; it is on the last place the story *named*.
  Without this, the wanting-a-new-place rule skips past the fixture to the next
  candidate — which in a coastal story is the sea — and stages the climb out on
  the water. Note "named", not "staged": the hill may have been mentioned in an
  earlier act without ever being that act's setting.

### A vessel needs water under it

A boat placed on the ground line of an act that is held on land is drawn on the
hillside — a trawler parked on a mountain. Nothing in the collision code can
see this, because the placement is *correct*: the vessel is on the ground, and
the ground happens to be a hill. So the sea is brought in behind the land for
the vessel to sit on (`staging.WATERBORNE` / `staging.WATER`).

### Each act stands somewhere new

Colour is not the only thing that was collapsing to the middle. The reference
film spread its elements across x 75..1850 of a 1920-wide board — the whole
width. After the scene grammar arrived, a board measured **x 384..1536**: the
middle sixty per cent, with both edges permanently empty. The camera was not
being lazy; it had nothing at the edges to move toward.

`staging.stage_x_for()` gives each successive act its own stage centre, and the
compiler applies it as a **rigid translation of the things that act**. Scenery is
exempt — it is drawn wider than the frame on purpose and is the ground everything
stands on. A rigid translation is safe precisely because every measurement that
matters is relative: a climb's travel, a separation, an attachment's offset.

One exception, and it is the one that bites: a beat measured against a **held**
scene element must not be translated. A climb is measured against the act's held
staircase, which does not move with the cast, so translating the figure puts them
back beside the steps instead of on them.

Legibility survives all of this because every sticker already carries a white
torn border separating it from whatever is behind it — which is also why
cut-paper collage has always worked on coloured grounds (Matisse, Eric Carle)
rather than in spite of them.

### The palette and the score must agree

They are two independent readings of the same story, and they read different
things. The palette votes on the story's **imagery** — "snow", "furnace",
"sea" are the words that move it. The score reads the emotional register of
the **whole narration**.

They can therefore disagree, and when they do the film is scored one way and
coloured another. That is exactly what happened on the film this section was
written for: a ghost story that the score read as `dread` was printed on
`ember`, warm amber paper, because it was full of lanterns and matches. Each
half was defensible alone and nothing flagged the contradiction.

So the loop is closed in the compiler. The palette biases the score first
(the palette's own `score.mood` is passed as a hint); if the score overrules
that hint, and the palette's own vote was **not decisive**, the picture
follows the music via `palette.for_mood()`.

"Decisive" is a **ratio**, not a margin. Votes scale with the length of the
narration, so "beats the runner-up by 2" is a real bar for a 90-word short
and no bar at all for a 900-word episode — it once let 44-vs-31 through as a
clear answer, which is a 1.4x lead. The test is now `best >= 1.6 x
runner_up`.

An explicit `"palette"` in the beat plan disables all of this, as it should.

## 6. Variety is a real constraint

Repetition of the same drawing is fine as **continuity** (the same figure in
consecutive shots is the same person) and fatal as **filler** (the same figure
in twelve unrelated shots is a compiler that gave up).

The compiler reports both. Treat a high repeat count as a prompt to widen the
catalogue or rewrite the beat, not as a number to suppress.

---

## Verifying art direction

There is no single score for "is this a good picture", but these are measurable
and they caught every regression during development:

```bash
python3 - <<'PY'
import json, collections
sb = json.load(open("storyboard.json"))
art = [e for e in sb["elements"] if e.get("type") == "art"]
print("art elements   ", len(art))
print("distinct        ", len(set(e["name"] for e in art)))
print("x columns       ", len(set(e["at"][0] for e in art)))
print("drifts          ", sum(1 for e in art if "drift" in e))
print("held scene layers", sum(1 for e in art if e["id"].startswith("sc")))
PY
```

On the 24-line test film, before and after this document existed:

| measure | before | after |
|---|---|---|
| art elements | 25 | 43 |
| distinct drawings | 15 | 24 |
| distinct x positions | **2** | 9 |
| journeys shown | 0 | 10 |
| held scene layers | 0 | 5 |
| composed scenes (>1 element) | 0 | 10 |

Then **open the sheet and look at it.** The numbers above were all green on a
version whose timeline still had no dates on it.
