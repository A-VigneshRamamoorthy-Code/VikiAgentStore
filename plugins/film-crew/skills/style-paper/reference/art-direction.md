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

### A subject must contrast with what it stands on

Choosing colours per element is not enough, because the frame is a *stack*. A
figure is drawn on a hill, a bench on the same hill, a flame on a lantern. If
any of those pairs is assigned the same sheet, the shape vanishes into its own
backdrop and only its border survives.

The failure is easiest to introduce in translation. A board compiled for one
style and re-coloured for another has to map more inks than the target palette
has sheets — nine against five, measured — so *some* pair must share, and the
naive rotation (`papers[n % len(papers)]`) picks that pair by first-seen order,
which correlates with nothing. It put a bench and its hill on the same colour.

Reuse is fine; **accidental** reuse is not. Build the graph of which inks are
drawn over which — boxes overlapping, lifetimes overlapping — and colour it, so
sheets are shared only between things that never appear together. Judge the
resulting separation perceptually, not by RGB distance: a teal and a blue of
the same lightness are far apart in RGB and read as one shape on screen.

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

### A beat hands over with a cut, not a dissolve

Every hand-over on a board is built the same way: the newcomer's `in.t` is set
to exactly the outgoing drawing's `out.t`. That is a **cross-fade** — and for
the 0.3–0.5 s the fade lasts, both drawings are on screen, both solid enough to
read. If they occupy the same ground, that is two objects piled on top of each
other, which is precisely the "last scene overlaid onto the new scene" note
that kept coming back from review.

It survived every fix aimed at *placement*, because placement was never the
problem — the two are supposed to be in the same place, one replacing the
other. It also survived every fix aimed at the **checker**, for a subtler
reason: an element does not vanish at `out.t`. The renderer keeps drawing it
for the whole of `out.dur`. Measuring lifetimes as `in.t .. out.t` — which
both the compiler and the verification script did — makes the hand-over
literally invisible to the geometry: the two are believed never to coexist, so
nothing separates them and nothing reports them. Widening `_live_window` to
the *visible* window took the validation board from a reported **0 overlaps to
7**, all of them real, all of them fades.

The fix is temporal, not geometric: the outgoing fade is tightened to a brief
wipe (0.15 s) and the newcomer is delayed to start when it finishes. Only
pairs whose boxes actually collide are staggered — two drawings at opposite
ends of the frame may dissolve across each other freely, and that is what
keeps the film from feeling like a slideshow. On the two boards this cut 6 and
19 hand-overs.

Two things had to move with it:

- **"On screen" and "scheduled" are different questions.** Everything asking
  *is this drawing here at the same time as that one?* wants the visible
  window, fade included. The flicker check (rule 13) asks *does this have time
  to play its own transitions?* — and adding the fade to the life it measures
  against inflates every element by exactly the quantity in question, so it
  stopped firing. That is `_life_window` versus `_live_window`, and the
  distinction is worth keeping straight.
- **The ground a drawing stands on is the one it shares the most time with.**
  Both host lookups took whichever ground came first (and, being separate
  copies of the same loop, `_ground_span` took the *last* while
  `_seat_on_ground` took the *first* — they had silently disagreed all along).
  Once a fade counts as being on screen, the outgoing act's hill qualifies at
  every hand-over, and a lantern living 31.0–34.1 s was seated on a hill that
  left at 31.4 s, hanging 238 px over the hill it actually spent its life on.
  Both now call `_ground_under`.

Grounds were excluded from the stagger at first, on the theory that scenery
dissolving is atmosphere rather than clutter. That was wrong, and it is the
single most visible case: an act change dissolves a *whole setting* through
the next one, so the frame holds a hillside and the sea that replaces it at
once, with the new act's boats already sailing through the old act's hill.
Including grounds took the 12-beat board from 6 staggered hand-overs to 22.

Then one pair survived, and it was instructive: a figure fading out at 5.3 s
while a hill faded in *over* it — the hill on layer 29, the figure on 20. The
trigger only recognised a hand-over as *the newcomer arrives inside the old
one's fade*, and here the order was reversed: the ground had begun arriving
**before** the figure started to leave. It is the same defect seen from the
other side, and the remedy has to be the other way round too, because an
arrival already in progress cannot be delayed. So the departure is pulled
forward — the figure is gone before the ground reaches it. That shift is
capped at 0.7 s and refused if it would leave the drawing less than half a
second on screen, because a beat that never plays is worse than a momentary
overlap.

A drawing's **layer** is what turns a harmless dissolve into a defect. A new
act's ground is deliberately drawn *above* the act it replaces — it has to
cover it — so during a cross-fade it covers the previous act's actors too.
That is why the answer is timing rather than z-order: lowering the ground
would break the act change it exists to perform.

**Attachments follow their host through all of this.** They are placed before
staggering runs, so a lantern whose fade is cut or whose exit is pulled
forward leaves its flame burning in mid-air over the scene that replaced it.
The re-anchor pass therefore copies the host's `out` every time, including
when the position is already correct — the second pass exists precisely
because the *schedule* changed, not the position.

**Measuring this needs its own probe.** "Do two boxes overlap while on screen"
is not the question; two drawings are allowed to share the frame. The question
is *are both mid-transition where they collide* — one fading out while the
other fades in. Sweeping the film at 0.1 s and reporting only those pairs took
the board from 32 → 2 → 0 across the fixes above, and never once disagreed
with what the frames showed. Note that the film's **opening** trips a naive
version of this check, because everything fades in at once there; it is an
establishing shot, not a hand-over, and the sweep starts after it.

**And a third case the probe cannot see**, because nothing is fading *out*: a
new act's ground arrives on a layer above drawings that are still mid-beat
beneath it. At 42 s on the validation board, `b11 hill` (layer 120) faded in
over a live sea (107) and two trawlers (87) — for half a second the hillside
was translucent and the previous act's boats sailed through it. There is no
hand-over partner to stagger against, so the fade *itself* is the defect and
is cut to a 0.15 s wipe.

Retiring the covered drawings as well was tried first and made things worse:
forcing them to fade out invented eight fresh cross-fades — exactly what the
two loops above exist to remove — and stranded a figure on open water. **A fix
that creates work for an earlier pass is not a fix**; the pass order is a
pipeline, and anything injected after a stage runs is never checked by it.
Cutting only the newcomer's own arrival touches nothing downstream.

**Boxes touching is the wrong test for the same drawing twice.** The stagger
deliberately leaves distant pairs alone — that is what stops the film becoming
a slideshow — and by that rule a lantern at the foot of the hill dissolving
into the same lantern on the summit was left to cross-fade, because x=403 and
x=864 do not collide. On screen it is unambiguous: for a third of a second
there are **two lanterns**, which is a different story from one lantern that
was carried up. So identity overrides geometry — two drawings of the same
illustration are always a hand-over, wherever they sit. Legitimate repeats
survive this, because they are not hand-overs: three hills making a range, or
two figures cast into one beat, are on screen together from the start rather
than one arriving as the other leaves.

### A drawing that travels arrives somewhere it could have stood

A **drift** is how a figure climbs the stairs rather than cutting from the
foot of them to the top — it is the whole answer to "show them walking from
one place to another", which is the note that put travel into these films in
the first place. It is expressed as a delta on top of `at`.

And that is the trap. Every geometry pass in `compile.py` reads `at`: seating,
separation, the frame check, the ground lookup. `at` is where the drawing
*starts*. **Nothing had ever looked at where it ends up.**

Measured, the result was not marginal — **1 of 2** travelling drawings on the
12-beat board and **10 of 10** on the 37-beat board arrived off the frame or
off the ground. The clearest case: a figure seated exactly on the hill, given
a `405 x -328` climb, finished with its centre **29 px above the top of the
board**. On screen it was a pair of legs sliding along the top edge for four
seconds. It passed every single check, because at `at` it was perfect.

The destination is now seated the way the start is — clamped into the frame,
held inside the host ground's span, and dropped onto the measured surface at
the x it actually reaches — and the delta rewritten to match. Vessels keep
their y, because a boat travels along its waterline and `_reseat_vessels`
owns that height. It runs **last**, after staggering and re-seating, because
every one of those passes can still move `at`, and a delta is only meaningful
relative to a settled origin.

The general lesson is worth more than the fix: **a value that is validated and
a value that is drawn must be the same value.** Three separate defects in this
file have now had that shape — a modelled dome instead of the measured one, a
slot the renderer did not fill, and now a start position standing in for an
end position. When a check and a frame disagree, suspect the quantity, not the
check.

### A flame belongs at the wick, not at the foot

`staging.ATTACH` already knows a flame is drawn small at an anchor on its
lantern, a halo above a head, smoke above a funnel. But that only applies when
`_extract_attachments` sees both in the **same cast**. A lantern lit *across a
beat boundary* — established in one sub-beat, lit in the next — arrives as two
independent elements, and the flame is then treated as scenery: seated on the
ground like anything else, at the same base as the lantern, so it spans the
lantern's bottom third and appears to leak out of its foot rather than burn
inside its glass. This is exactly the "this is how a lit lantern is shown"
frame that came back from review.

`_reanchor_attachments` runs last, after every pass that could have moved the
host, and pins each stray attachment back onto whichever host shares the screen
with it — preferring its own beat, then the largest candidate. On the
validation boards: the flame moved from y=508 to y=370, which is the wick
(`centre − 0.46 × height`), and was rescaled to 0.42 of the lantern.

Two consequences worth knowing:

- **Attachments are exempt from ground seating.** A flame stands on its
  lantern; if it were also seated on the hill the two rules would fight.
- **Attachments are exempt from the legibility floor.** They are *drawn small
  by design*. The floor never saw one before, because a composed attachment is
  drawn as part of its host and is not a separate element at all — so the
  first thing re-anchoring did was trip a check that had simply never been
  reached.

### Nothing is drawn on top of anything else

Everything above decides placement **one beat at a time**, and a beat cannot see
what an earlier beat left standing. So every rule can be individually correct
and the frame still wrong. On the validation board the "far out to sea" beat
placed a trawler at x 1036.8 — a defensible spot on the waterline — where a
figure staged two lines earlier was already standing at x 1036.8. Both
placements were right. The composite was a boat sailing through a person.

An earlier version of this check compared scene *k* with scene *k+1*, so it only
ever caught bleed **across** a cut. Every defect a viewer actually reported was
*inside* one act, where the check never looked. Collisions are therefore resolved
on the **finished board**, against real lifetimes, in this order:

1. **A second setting goes to distance.** A beat may legitimately name two
   places — standing on a hilltop, looking out to sea. Drawn at the same size
   they are two horizons, and that is what makes a staircase appear to be
   standing in open water. The newcomer is scaled to **46%**, lifted to the
   held ground's shoulder and pushed behind it in z, carrying its whole beat
   group. The held hill then occludes its middle, which is exactly what
   distance looks like. Act settings and fixtures are exempt — a fixture is
   something you climb, not a competing place — and so is any ground with a
   person standing on it.
2. **Colliding drawings are pushed apart** horizontally, sweeping until the
   board converges. A single pass measurably undoes its own work: a trawler
   moved clear of a figure is shoved back by the next comparison.
3. **Where there is no room, the newcomer is drawn smaller** — never lifted.
   Almost everything in this style is seated: figures on the ground line, hulls
   on the waterline. Lifting to resolve a collision parked a figure at y=68,
   hovering in the sky.
4. **Failing that, the older drawing leaves.** Two things that cannot share a
   frame should not both be in it.

Three things make this harder than it sounds:

- **Depth defeats 2D collision — but only against scenery.** A distant boat
  passing behind a foreground *hill* is composition, not overlap; without a
  parallax test the compiler retires the protagonist to make room for a trawler
  on the horizon. Between two **actors** the exemption is wrong, and it shipped
  a defect: a figure on the near plane spanning x=[936,1137] and a trawler on
  the far one spanning x=[863,1128] were excused as "different depths", and the
  film drew her head inside the hull. Two drawings of similar size read as one
  object no matter what their z says. The exemption now requires that at least
  one of the pair is not an actor.
- **A beat's own cast is composed on purpose — unless it is two subjects.** The
  exemption exists so a flame stays on its lantern and a chair stays beside its
  figure, and those are props. Two *actors* cast into one beat get independent
  stage marks and can collide like any other pair: one beat put a trawler at
  x=[863,1128] and a second boat at x=[1033,1187], and the film showed a blue
  prow growing out of an orange hull. Same-beat pairs are compared when both
  are actors.
- **Shrinking needs a floor, and it needs two.** A relative floor alone is not
  enough, because a receded element has already been scaled to 46% — another
  60% of that is 28% of the drawn size. An absolute minimum is the backstop.
- **A ground is exempt from this check, and that exemption is one word too
  broad.** Grounds are left out of the comparison on purpose: a hill is *meant*
  to have a figure standing on it, so comparing their boxes would flag every
  correctly composed frame. But it is only true of the drawings that belong to
  that ground. Measured at t=42 on the lab board, a new beat's hill spanning
  x=[250,1670] arrived at 41.85 straight over a trawler at x=[994,1570] that
  the previous beat had put on open water and that ran on until 45.78. Both
  fully opaque, nothing dissolving, every check clean — and a fishing boat sat
  parked on a hillside for four seconds. **7 such leftovers on the lab board
  and 3 on the regression board.** Cutting the cross-fade stops two pictures
  blending; it does nothing about the previous scene's cast being *left* on the
  new scene's ground.

  So an arriving ground hands over as well, and the timing is the whole trick:
  the leftover must be gone **by** the moment the ground lands, not fading out
  as it fades in. The first version retired it *on* the arrival and simply
  traded a leftover for six fresh cross-fades. Two guards keep it honest —
  only non-grounds are retired, because an earlier attempt that also retired
  the grounds a newcomer covered stranded a figure on open water, and held
  scene backdrops (`sc*`) are not arrivals at all, because things standing in
  front of a backdrop is the point of having one.
- **A ground is a dome, not a rectangle.** Clamping a prop to the ground's
  bounding box lets a chair sit at the box's right edge, past the hillside,
  apparently floating on the sea. The usable span narrows with height above
  the base.
- **…and the same curve decides height, not just width.** Constraining only
  *x* is half a fix. Separation moves a drawing **along** the slope, and if
  nothing then corrects *y* it keeps the height it had where it started: a
  lantern shunted from the summit out to x=310 hung 180 px above the hill in
  open sky. It passes every bounding-box seating test, because the box of a
  dome contains all the empty air beside it.
- **The drawn silhouette is not the bounding box, and every ground has its
  own.** The first version of both rules used one modelled curve,
  `1 - 0.85·up`. It is wrong for every ground in the set. Measuring the real
  artwork — topmost opaque pixel per column, five seeds, both halves — a
  hill's peak reaches only **0.80** of its box height, because the drawing
  carries 19% empty sky above it, so a lantern seated at "the top" hovered
  ~130 px in the air. And the shapes are not variations on a dome: a hill is
  a cosine, the sea and a café front are flat, a staircase is level then
  falls off a cliff, a terminus is a spike.

  ```
  hill     [.80 .79 .75 .70 .62 .52 .42 .30 .19 .08 .00]
  sea      [.90 .91 .91 .91 .91 .90 .91 .91 .91 .91 .90]
  stairs   [.77 .77 .77 .77 .77 .77 .70 .72 .45 .00 .00]
  terminus [1.0 .98 .61 .40 .40 .40 .40 .40 .56 .40 .00]
  ```

  `staging.SURFACE` holds all nine, sampled at eleven points from centre to
  edge; `surface_up()` reads a height off it and `surface_reach()` inverts it
  for the span clamp, so the two can never disagree. The table is baked
  rather than measured at runtime because the compiler is deliberately
  PIL-free — and it is safe to bake, because the normalised profile is
  **completely aspect-independent** (identical at 1200×420, 1200×600, 800×420
  and 1600×400) and near seed-independent (0.786–0.795).

  The lesson is bigger than the numbers: **a check that shares a model with
  the code it checks cannot find an error in that model.** The seating test
  had reported *0 floating* for weeks. Re-run against the measured surface,
  the same boards showed **6 and 22** floating drawings — including the
  lantern the reviewer had photographed.
- **…and the renderer has to draw it at the size the compiler placed.** Even
  with the surface measured and the seating correct *in stage space*, the
  lantern still hovered 60 px over the summit on screen. The compiler was
  right and the drawing was wrong: `fit` is a box, but a drawing scaled by
  `size` has only one number to scale, and the fit path treated it as square
  and took `min(fit_w, fit_h)`. A lantern given a 194×313 slot was drawn
  120×194 — **62% of its slot** — and since seating had used the box it asked
  for, it hung by the difference. Sixteen of the illustrations are scaled this
  way. `size` means *longest side*, so the answer is `max(fit)`; the compiler
  derives `fit` from `natural_box`, so the aspects already agree and the
  drawing fills the slot exactly.

  This is worth internalising: geometry that is provably correct on the
  storyboard still renders wrong if the renderer disagrees about how big
  anything is. The check is one line — draw every element and compare its
  image size to its `fit`:

  ```python
  img = make_base(spec, 1.0, accent, seed, ink, stock)
  assert abs(img.size[0] - spec["fit"][0]) <= 6 \
      or abs(img.size[1] - spec["fit"][1]) <= 6
  ```

  On the validation board this went from 16 mismatches to 0, and the residual
  gap under the lantern fell from 61 px to 11 px — the remaining margin being
  transparent padding inside the drawing itself, which is under a paper
  edge's own raggedness.

The passes also fight each other, and the order matters: separation lifts a
trawler off its sea, reseating pushes it back into a figure. Vessels are
**y-locked** so only horizontal separation applies, and reseating runs both
before the separation loop and again inside it.

### Height is distance, and it decides depth too

Seating a vessel on the right waterline is not sufficient. On the closing beat
of the validation film a boat sat correctly at y=687 while the hill in the same
shot had its base at y=905 — 218 px lower, and so unambiguously nearer — yet
the boat carried the higher `z` and was drawn straight across the hillside. Two
correct placements, one impossible frame.

In this projection *up* means *away*, so anything floating higher than a
ground's base line belongs behind that ground. Two things make the rule
narrower than it first looks:

- **Water is not land.** The first version treated the sea as a ground and
  filed the boat behind its own water, which hid it entirely.
- **Only the vessel moves.** Sending its whole beat group behind the hill took
  an unrelated chart down with it.

### Nothing appears for less time than it takes to appear

The last pass on the board, and the one that explains a report no amount of
palette work could fix.

Retiring the older of two colliding drawings sets its `out` to the moment the
newcomer lands. When the two are only a beat-substep apart that leaves almost
no lifetime at all: on the validation film a trawler was given **0.10 s**
against a **0.56 s** fly-in and a **0.40 s** fade-out.

The renderer does not clamp this. It evaluates the entrance at whatever
fraction of it elapsed, so the drawing is frozen part-way through — still
translucent, still offset from its mark, its paper cut-out border not yet
opaque. Composited over a dark field, a half-faded violet hull is a
desaturated blue-grey smear.

That shipped as *"the ship is grey"*, and it cost three wrong diagnoses before
the cause turned up, because every colour in the chain was correct: the
element's ink was `#B04AC7`, the palette was the colourful one, the conflict
graph had done its job, and the renderer was passing the ink through properly.
**The colour defect had no colour in its cause.** It is worth remembering that
a washed-out drawing may be a *timing* bug wearing a colour bug's clothes —
check the lifetime against `in.dur + out.dur` before touching a palette.

Transitions are compressed to fit first, since a brief glimpse is sometimes
the intent. Below what a glimpse can even be — twice the 0.12 s floor — the
drawing is dropped outright; it was already competing for a frame it lost.
Across the two validation boards this dropped three drawings.

### A drawing made of words has a minimum size

Sizes are handed out by *role*: a diagram standing beside an actor is a prop,
and a prop's allowance is small. That is right for a lantern and wrong for a
chart — shrinking a lantern loses nothing, shrinking a chart loses the only
thing it was for. A `timeline` designed at 520x860 was drawn at 173x286 and its
four date labels were unreadable smudges, which is the "no clear timeline"
complaint in its most literal form.

Lettered drawings therefore have a floor, and enforcing it needs two more
things that are not obvious:

- **Grow from the foot, but respect the ceiling.** The base is where the
  drawing was placed against a ground line and is still correct, so the new
  height all goes upward — which pushed the first attempt 65 px off the top of
  the frame, where the off-frame clamp shrank it back to *below* where it
  started. Headroom is the real limit.
- **Never shrink one to resolve a collision.** A chart introduced on the last
  line is the newest thing on the board and so is always the element asked to
  yield, which took the freshly-enlarged timeline straight back down to 60%.
  Move it, or retire what it hit — but do not shrink it.

### A person needs land

The mirror of the vessel rule, and it was missed for the same reason. An act
that puts to sea brings in water for the boats — and the narrator, who is
standing on shore watching them, is placed on the same ground line. The result
is a woman standing in open water. A water act injects the last-named land back
into its cast for people to stand on.

This needs a narrower category than the one the vessel rule uses: `staging.ACTOR`
includes boats, so `staging.PERSON` exists specifically so "a person needs land"
does not fire for a trawler.

**Order matters more than the rule does.** The check first ran immediately after
the vessel rule and so sat *above* the two rules that put people into beats that
never named any — "a journey needs a traveller" and the pursuit companion. The
opening shot of the validation film, cast from the single word `sea` for the
line *"Meera walked the shore road out of the town"*, therefore looked like a
beat with nobody in it, passed the check, and then had a figure appended to it
one rule later. She walked on the water for the whole first act. The land check
is now the last casting rule to run, after every rule that can add a person.

**Casting is only half of it.** A ground that is cast correctly but *retired*
while someone is still standing on it draws the identical frame. On the same
board the Kalvari hillside left at `l3+0.3` and the figure on it stayed until
`l4-0.3`, so for a third of a line she stood on open sea — with a cast list
that satisfied every rule above. `_hold_ground_under_actors` extends each
ground's life to cover the last actor standing on it.

Matching the actor to *her own* ground is the subtle part. A first attempt
filtered to grounds that leave early and then picked the nearest one, which
matched her to a hillside two acts back and dragged it forward across three
scenes. Select the closest ground underfoot **first**, then ask whether it
leaves early — otherwise the filter chooses the answer before the geometry does.

### A caption is never occluded

A keyword chip is deliberately held past its own beat so there is time to read
it, which means later beats routinely lay artwork straight over it. This was
never checked, and it had been happening from the start: **eight** buried
captions on the 12-beat validation board and **twenty-nine** on the 37-beat
regression board. Every chip is now lifted into a reserved z band above the
topmost drawing.

The first attempt at the distance rule made this worse rather than better,
because the routine that gathers a beat's group matched chips as well as
artwork and filed the caption away behind the hill along with everything else.
Group transforms apply to artwork only.

Occlusion was only half of it. A caption can be perfectly unburied and still
unreadable, because being on the board is not the same as being in the frame.
Chips are positioned in stage space; the camera decides what is actually
photographed, and until now the two were never compared. Motion-plan moves are
clamped by the framing pass. **Act-change swings are not** — they lean a flat
`0.18 × W` (345 px on a 1920 board) purely to signal a change of act, and that
lean was applied without asking what it was pushing off the edge. Measured, **3
of the lab board's moves and 35 of the regression board's** pointed away from a
caption that was on screen at that instant. On screen it read as a typo:
"THE ROCKS" arrived as "ROCKS".

The camera gives way, not the writing. Each move now takes the box covering
every caption live at that moment, eases its zoom out first — cheaper than
moving, and often enough on its own — and then walks its aim back until the
words fit. Both boards go to zero.

The word *live* is doing work there, and it is the same trap as the fade
window, in a third place. A caption does not blink out at `out.t`; it fades.
Counting it as present to the last frame of that fade drags the camera around
to protect a word at a tenth opacity, which nobody can read and which costs
real motion. Counting it as gone at `out.t` cropped one at **70 %** opacity,
which is plainly legible. Aiming therefore treats a caption as present for the
legible share of its fade — about two thirds — while zoom headroom, which is
expensive, still stops at `out.t`. Of eight cases the first version left
behind, seven were at 0.10 opacity and one at 0.70: the seven were the probe
being wrong, the one was the code being wrong.

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

Overlap and seating are checked by the compiler itself and reported as blocking
notes, so a board that compiles clean has already passed them. To confirm
directly, sweep every pair of drawings that are **live at the same time**:

```bash
python3 - <<'PY'
import itertools, json, os, re, sys, wave
sys.path.insert(0, "scripts")           # or the style's scripts/ directory
import staging

SLACK, MIN_AREA = 0.25, 110.0 * 72.0
W, H = 1920, 1080

board = "storyboard.json"
sb    = json.load(open(board))
base  = os.path.dirname(board) or "."
art   = [e for e in sb["elements"] if e.get("type") == "art" and e.get("fit")]

# Real line times, not an assumed average: a line runs as long as its own
# voice-over, and the gaps between them differ too.
start, t = {}, float(sb.get("lead_in", 0) or 0)
for c in sb["narration"]:
    with wave.open(os.path.join(base, c["audio"])) as w:
        d = w.getnframes() / w.getframerate()
    start[c["id"]] = t
    t += d + c.get("gap_after", 0)

def when(tok, default):                 # "l6+0.2" -> seconds
    if not isinstance(tok, str):
        return default
    m = re.match(r"([A-Za-z0-9]+)([+-][\d.]+)?$", tok)
    if not m or m.group(1) not in start:
        return default
    return start[m.group(1)] + float(m.group(2) or 0)

def live(e):
    # A drawing does not vanish at `out.t` -- the renderer keeps drawing it
    # for the whole of `out.dur`. Measuring only in..out hides every
    # cross-fade from this script; it reported 0 overlaps on a board that
    # had 7, all of them hand-overs dissolving through each other.
    a = when((e.get("in") or {}).get("t"), 0.0)
    out = e.get("out") or {}
    b = when(out.get("t"), 1e9)
    return a, (b + float(out.get("dur", 0) or 0) if b < 1e8 else b)

def scheduled(e):
    # ...but rule 13 asks whether a drawing has time to play its own
    # transitions, and must *not* count the fade as part of the life it is
    # measuring against, or nothing ever looks too short.
    return (when((e.get("in")  or {}).get("t"), 0.0),
            when((e.get("out") or {}).get("t"), 1e9))

def box(e):
    (x, y), (w, h) = e["at"][:2], e["fit"][:2]
    return x - w / 2, y - h / 2, x + w / 2, y + h / 2

beat  = lambda e: str(e.get("id", "")).split("_")[0]
actor = lambda e: staging.role_of(e.get("name")) == "actor"
overlaps_in_time = lambda a, b: a[0] < b[1] - SLACK and b[0] < a[1] - SLACK

hits = 0
for a, b in itertools.combinations(art, 2):
    both = actor(a) and actor(b)        # two subjects, not an attachment
    if not both and beat(a) == beat(b):
        continue                                     # a beat composes its props on purpose
    if a["name"] in staging.GROUND or b["name"] in staging.GROUND:
        continue                                     # a ground is meant to be stood on
    if not both and abs(a.get("parallax", .5) - b.get("parallax", .5)) >= 0.2:
        continue                                     # scenery behind a subject reads fine
    la, lb = live(a), live(b)
    if not (la[0] < lb[1] - SLACK and lb[0] < la[1] - SLACK):
        continue                                     # never really on screen together
    ax0, ay0, ax1, ay1 = box(a); bx0, by0, bx1, by1 = box(b)
    if ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1:
        hits += 1
        print("overlap", a["id"], a["name"], "x", b["id"], b["name"])

floaters = []
for e in art:                           # rule 8/12: a person needs land, all the way through
    if e["name"] not in staging.PERSON:
        continue
    eb, el, ok = box(e), live(e), False
    for g in art:
        if g["name"] not in staging.GROUND or g["name"] in staging.WATER:
            continue
        gl, gb = live(g), box(g)
        if gl[0] <= el[0] + 0.05 and gl[1] >= el[1] - 0.05 \
                and gb[0] <= e["at"][0] <= gb[2] and gb[3] >= eb[3] - 8:
            ok = True
            break
    if not ok:
        floaters.append(e["id"])

ghosts = []                             # rule 13: retired before it finished arriving
for e in art:
    out = e.get("out") or {}
    if not e.get("in") or not out.get("t"):
        continue
    a, b = scheduled(e)
    if b < 1e8 and b - a < float(e["in"].get("dur", 0)) + float(out.get("dur", 0)):
        ghosts.append(e["id"])

hover, loose = [], []                   # rule 8: seated on the drawn surface
for e in art:
    n, el = e["name"], live(e)
    if n in staging.ATTACH:             # a flame stands on its lantern
        hosts = [h for h in art if h["name"] in staging.ATTACH[n]
                 and overlaps_in_time(live(h), el)]
        if not hosts:
            continue
        h = min(hosts, key=lambda h: abs(h["at"][0] - e["at"][0]))
        dx, dy, _ = staging.ATTACH_ANCHOR.get(n, (0.0, -0.46, 0.42))
        wx, wy = h["at"][0] + dx * h["fit"][0], h["at"][1] + dy * h["fit"][1]
        if abs(wx - e["at"][0]) > 6 or abs(wy - e["at"][1]) > 6:
            loose.append(e["id"])
        continue
    if n in staging.GROUND or n in staging.WATERBORNE \
            or staging.role_of(n) not in ("actor", "prop"):
        continue
    beat_id, own, host, best = e["id"].split("_")[0], None, None, 0.0
    for g in art:      # the ground it shares the most *time* with, not the first
        if g["name"] not in staging.GROUND or g["name"] in staging.WATER:
            continue
        gl = live(g)
        if not overlaps_in_time(gl, el):
            continue
        if g["id"].split("_")[0] == beat_id:
            own = g
        elif g["id"].startswith("sc"):
            shared = min(gl[1], el[1]) - max(gl[0], el[0])
            if shared > best:
                host, best = g, shared
    host = own or host
    if host is None:
        continue
    gx0, _, gx1, gy1 = box(host)
    f = min(1.0, abs(e["at"][0] - (gx0 + gx1) / 2) / max(1.0, (gx1 - gx0) / 2))
    surface = gy1 - staging.surface_up(host["name"], f) * host["fit"][1]
    if surface - (e["at"][1] + e["fit"][1] / 2) > 25:
        hover.append(e["id"])

piles, span = {}, max([live(e)[1] for e in art if live(e)[1] < 1e8] or [0])
for i in range(25, int(span * 10)):   # rule 15 — starts at 2.5 s, past the opening,
    T = i * 0.1                       # where everything fades in at once by design
    on = [e for e in art if live(e)[0] <= T <= live(e)[1]]
    for a, b in itertools.combinations(on, 2):
        fa, fb = T > scheduled(a)[1], T > scheduled(b)[1]        # leaving
        ia = T < live(a)[0] + float((a.get("in") or {}).get("dur", 0))
        ib = T < live(b)[0] + float((b.get("in") or {}).get("dur", 0))
        if not ((fa and ib) or (fb and ia)):
            continue                  # both merely present: co-existing, not handing over
        ax0, ay0, ax1, ay1 = box(a); bx0, by0, bx1, by1 = box(b)
        if ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1:
            piles[(a["id"], a["name"], b["id"], b["name"])] = round(T, 1)
for k, t in piles.items():
    print("dissolving through", k, "at t=%.1f" % t)

drifted = []                            # rule 16: a travelling drawing has to land
for e in art:
    d = e.get("drift")
    if not d:
        continue
    w, h = e["fit"]
    ex, ey = e["at"][0] + d.get("x", 0), e["at"][1] + d.get("y", 0)
    if ex - w / 2 < -40 or ex + w / 2 > W + 40 \
            or ey - h / 2 < -20 or ey + h / 2 > H + 40:
        drifted.append(e["id"])         # ends outside the board entirely
        continue
    host = None                         # ...or in mid-air over the ground it left
    if e["name"] not in staging.GROUND and e["name"] not in staging.WATERBORNE \
            and staging.role_of(e["name"]) in ("actor", "prop"):
        # Same rule as the seating block above — its own beat's ground first,
        # then the one it shares the most time with. Taking whichever ground
        # came first instead reported a figure standing 109 px off a hill it
        # was never on, while it sat exactly on its own beat's stairs.
        el, bid, own, best = live(e), e["id"].split("_")[0], None, 0.0
        for g in art:
            if g["name"] not in staging.GROUND or g["name"] in staging.WATER:
                continue
            gl = live(g)
            if not overlaps_in_time(gl, el):
                continue
            if g["id"].split("_")[0] == bid:
                own = g
            else:
                shared = min(gl[1], el[1]) - max(gl[0], el[0])
                if shared > best:
                    host, best = g, shared
        host = own or host
    if host is None:
        continue
    gx0, gy0, gx1, gy1 = box(host)
    f = min(1.0, abs(ex - (gx0 + gx1) / 2) / max(1.0, (gx1 - gx0) / 2))
    if abs((gy1 - staging.surface_up(host["name"], f) * host["fit"][1])
           - (ey + h / 2)) > 25:
        drifted.append(e["id"])

cropped = []                            # rule 17: a caption on screen is in frame
chips = [e for e in sb["elements"] if e.get("type") == "chip"]
for mv in sb["camera"]["moves"]:
    mt = when(mv.get("t"), 0.0)
    cx, cy = mv["at"][:2]
    z = float(mv.get("zoom", 1.0) or 1.0)
    hw, hh = W / 2 / z, H / 2 / z
    for c in chips:
        a, b = live(c)
        if not a <= mt <= b:
            continue
        ot = when((c.get("out") or {}).get("t"), 1e9)
        od = float((c.get("out") or {}).get("dur", 0.0) or 0.0)
        if mt > ot and 1 - (mt - ot) / max(0.01, od) < 0.35:
            continue                    # too faint to read; not worth a pan
        s = float(c.get("size", 60))
        w = len(str(c.get("text", ""))) * s * 0.60 + 60
        x, y = c["at"][:2]
        if (x - w / 2 < cx - hw - 2 or x + w / 2 > cx + hw + 2
                or y - s / 2 < cy - hh - 2 or y + s / 2 > cy + hh + 2):
            cropped.append((mv.get("t"), c.get("text")))

stranded = []                           # rule 18: a ground carries only its own
for g in [e for e in art if e["name"] in staging.GROUND
          and not str(e.get("id") or "").startswith("sc")]:
    ga, _ = live(g)
    gx0, gy0, gx1, gy1 = box(g)
    gbeat = str(g.get("id") or "").split("_")[0]
    for e in art:
        if e["name"] in staging.GROUND or e["name"] in staging.ATTACH:
            continue
        if str(e.get("id") or "").split("_")[0] == gbeat:
            continue                    # this ground's own cast
        ea, eb = live(e)
        if ea >= ga - 0.01 or eb <= ga + 0.01:
            continue                    # arrived later, or already gone
        ex0, ey0, ex1, ey1 = box(e)
        if ex1 <= gx0 or ex0 >= gx1 or ey1 <= gy0 or ey0 >= gy1:
            continue
        stranded.append((g["id"], e["id"], e["name"]))

print("overlaps        ", hits)
print("crushed         ",                # attachments are drawn small by design
      [e["id"] for e in art
       if e["fit"][0] * e["fit"][1] < MIN_AREA and e["name"] not in staging.ATTACH])
print("standing on water", floaters)
print("half-faded      ", ghosts)
print("floating        ", hover)
print("loose attachment", loose)
print("dissolving through", len(piles))
print("landed badly  ", drifted)
print("caption cropped ", cropped)
print("left on new ground", stranded)
PY
```

All six lists must be empty. A non-empty `crushed` means the shrink fallback ran
out of room, which is a casting problem upstream rather than something geometry
can fix.

Six details in that script are the whole reason these defects survived so long,
and getting any of them wrong reports a clean board as broken (or the reverse):

- **Measure the surface, don't model it.** `surface_up` reads the same measured
  `staging.SURFACE` table the compiler uses. The earlier version of this script
  re-derived the height from the old `(1 - f) / 0.85` formula — the same wrong
  model the compiler had — and so reported *0 floating* on boards that had 6 and
  22. A check that shares a model with the code under test only ever confirms
  the model.

- **Compare lifetimes, not just positions.** Two drawings at the same spot in
  different acts are fine. Elements carry symbolic times (`l6+0.2`), so they
  have to be resolved against the narration before they can be compared — and
  resolved against the **voice-over durations**, not an assumed seconds-per-line.
  A flat average puts every element in the wrong act; checked that way, a board
  reports the closing beat as live 25 seconds before it appears.
- **Allow slack at a handover.** A departing element and its replacement
  deliberately share a fraction of a second so the cut does not flash. Without
  a slack term every single handover in the film is reported as a collision.
- **Exempt grounds always, and depth only against scenery.** A hill *is* the
  thing everyone stands on. But "different depths read fine" is only true when
  one of the pair is scenery; between two actors it excuses a figure's head
  drawn inside a trawler's hull.
- **Exempt a beat's own cast only when it is not two subjects.** The exemption
  is there for attachments — a flame on its lantern, a chair beside a figure,
  all of which are props. Two actors in one beat can collide like any other
  pair, and did: a boat drawn inside a trawler.
- **Judge size by area, not by width and height.** A flame is legitimately
  82 px wide; a per-dimension floor calls it crushed. The compiler's floor is
  a guard on *shrinking further*, not a minimum imposed on small drawings.
