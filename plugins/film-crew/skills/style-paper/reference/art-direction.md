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
