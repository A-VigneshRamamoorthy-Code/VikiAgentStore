# The beat plan

`beat-plan.json` is what the storyboard artist hands to the production designer.
It says **what is on screen and when**, in language no single renderer owns.

Validate with `python3 scripts/beatplan.py beat-plan.json`.

---

## Why it is style-neutral

The temptation is to write the plan in the vocabulary of the renderer you happen
to have — torn cards, chips, elevation, pins. Do that and the "style registry"
is one style wearing a hat: a second style could never be added, because the
plan would already be a paper storyboard by another name.

So the rule is: **if a field only means something to one renderer, it does not
belong here.** A beat says *"reveal the factory, stress UNION CARBIDE, circle
it"*. How a circle is drawn is the style's business.

---

## Top level

```json
{
  "schema": 1,
  "title": "Bhopal, Part One",
  "seed": 19,
  "narration": [ … ],
  "acts":      [ … ],
  "beats":     [ … ],
  "hooks":     [ … ],
  "loops":     [ … ],
  "timing":    { "lead_in": 34.0, "tail": 6.0 }
}
```

| field | required | meaning |
|---|---|---|
| `schema` | yes | must be `1`. A validator that cannot read the plan refuses rather than guessing |
| `title` | yes | becomes the default output filename |
| `seed` | no | makes every style's randomisation reproducible |
| `narration` | yes | the spoken lines, in order — the plan's clock |
| `acts` | no | movements, for camera and pacing |
| `beats` | yes | what appears, and when |
| `hooks` | no | the moments worth cutting as Shorts |
| `loops` | no | promises opened and paid |
| `region` | no | where the story happens, for any map the style draws. Omitted means an **unlabelled** chart — see below |
| `timing` | no | `lead_in` — seconds of film before the first spoken word; `tail` — seconds after the last |

### `timing`, and why a documentary needs it

`lead_in` is the run-up to the first spoken word. Feed video cannot afford one
and defaults to under a second. Long-form is built on it: in the measured
reference the title card does not arrive until **~50 seconds** in, and the film
reads as authoritative *because* it does not hurry.

But **silence is not a cold open.** A held title over score, with nothing said,
is a viewer waiting for the file to start. What the reference actually does is
open *inside* the story at its most cinematic moment — already in the air,
already in trouble — runs about fifty seconds of it, drops to near silence for
the last few, and only then stamps the title.

To get that, write the teaser as the **opening narration lines** and mark it:

```json
"hooks": [{ "id": "h1", "kind": "cold-open", "from": "l1", "to": "l4" }]
```

A style that understands the tag plays those lines first and lands the title
when they end. Keep `lead_in` short (**2–5 s**) — enough for the score to
establish, not enough to feel broken.

Only if the film genuinely has no teaser should `lead_in` carry the opening
alone, and then hold **8–15 s**, not forty. `--check` says so when it sees a
long silent lead-in with no cold-open hook above it.

Give the ending the same courtesy; `tail` under two seconds clips the last
word's air and makes a considered ending sound like a mistake.

`music` and `mix` may be passed through if a style understands them.

### `region`, and why omitting it is safe

Any style that draws a map needs to know where the story happens. Name it once
here — `"region": "pacific-northwest"` — and the style stamps it onto every map
it draws.

Leave it out and you get an **unlabelled** chart: a coastline with no place
names, which reads as a map without claiming to be anywhere. That is the safe
default on purpose. The alternative is worse than no map at all — a film about
Washington State once shipped forty-two shots captioned `ARABIAN SEA` and
`COLABA`, because the geography was baked into the style instead of being asked
for. A viewer who knows the place reads that instantly as a lie.

Each style publishes the regions it can draw; `style-paper` ships `mumbai`,
`pacific-northwest` and `generic`. If your story happens somewhere else, add
the region to the style rather than accepting a wrong one.

---

## `narration`

The timeline. Every beat time is relative to a line here, so this list is the
one thing that must be right before anything else can be.

```json
{ "id": "l4", "text": "By dawn the hospital had run out of room.",
  "audio": "vo/l4.wav", "gap_after": 0.8 }
```

| field | meaning |
|---|---|
| `id` | the handle beats point at. `l1`, `l2`, … by convention |
| `text` | the spoken words. Used to check that keyword chips are actually said |
| `audio` | path to the clip, relative to the plan. Measured with `ffprobe` |
| `duration` | used **instead of** `audio` to reserve silent time before the voice exists |
| `gap_after` | silence after this line. **This is where pacing lives** — 0.4–0.9 s |

A line with neither `audio` nor `duration` occupies no time, and every beat after
it is a guess. The validator warns; take the warning seriously.

---

## `beats`

```json
{
  "id": "b4",
  "at": "l4+0.2",
  "intent": "portrait",
  "subject": "the casualty ward at dawn",
  "keywords": ["Hospital"],
  "emphasis": 0.9,
  "assets": [{ "kind": "illustration", "hint": "hospital" }],
  "annotate": { "mark": "circle" },
  "safe": "vertical"
}
```

| field | required | meaning |
|---|---|---|
| `id` | yes | unique; styles use it to target annotations |
| `at` | yes | **a line-relative time**. See below |
| `intent` | yes | why this beat exists. Closed vocabulary |
| `subject` | no | plain-English description of what is shown |
| `keywords` | no | words to put on screen. Each **must be spoken in that line** |
| `emphasis` | no | `0`–`1`. How much of the frame and attention this deserves |
| `assets` | no | `{kind, hint}` — what picture is wanted |
| `annotate` | no | `{mark: "circle" \| "box"}` — mark up what is already there |
| `safe` | no | `full` (default), `vertical`, `square` — which crops this survives |

### The picture is whatever *this line* puts on screen

The one rule that decides whether the film looks made or generated:

> **Read the line. Name the thing it just said. Draw that.**

If the narration hands over a note, the beat's subject is the note. If it puts
a man in the rear row, it is the rear row of seats. A beat is not "another
shot of the aeroplane because this is a film about an aeroplane" — the picture
has to move when the story does, or a viewer is watching a slideshow with a
voice over it.

Two failures follow from ignoring it, and `--check` blocks on both:

- **One picture carrying the film.** No subject may appear in more than ~12% of
  beats. Four subjects covering a 20-minute documentary is the single most
  common cause of "the visuals didn't match the story".
- **The same picture twice at once.** Two beats whose pictures are on the board
  together must not draw the same thing; a repeat inside that window literally
  duplicates the drawing on screen. Give the second one `"assets": []` instead
  (see below) — the first copy is still up there.

Write `subject` in plain English and let the style resolve it. Reach for
`assets[].hint` only to override that choice — a hint that is just the style's
catalogue name (`"map"`, `"figure"`) is the smell that a real subject was never
chosen. Where the catalogue cannot draw what the line needs, say so plainly in
the hint and let the style report the gap; that is how the vocabulary grows.

### A beat may show nothing

Set `"assets": []` — an explicitly empty list — and the beat draws no picture.
It is not a failure and the style will not report a missing illustration.

Use it when the picture the line calls for **is already on the board**. Several
beats are alive at once, so a line that returns to something shown four seconds
ago does not need a second copy of it; a second copy is the slideshow effect,
not emphasis. Leaving the beat empty holds what is on screen instead of
clearing it.

What you must *not* do is fill such a beat with something unrelated so the
numbers look varied. A moon over a line about a flight attendant scores
perfectly on every check above and is worse than the repetition it replaced,
because the viewer stops believing the picture means anything. The checker
enforces this: a subject with no word in common with its own narration line is
reported, and at scale it is an error.

### Time references

| form | means |
|---|---|
| `"l3"` | when line `l3` starts |
| `"l3+0.4"` | 0.4 s after `l3` starts |
| `"l3-0.15"` | 0.15 s before `l3` starts |
| `"l3.end"` | when `l3` finishes |
| `"l3.end+0.2"` | 0.2 s after `l3` finishes |
| `2.4` | absolute seconds — **avoid**; a rewrite desynchronises it |

### `intent`

Closed on purpose. A style must be able to render every intent, and an open
vocabulary means a plan that silently degrades on a style that has never heard
of it.

| intent | for |
|---|---|
| `establish` | introduce a place, object or person for the first time |
| `reveal` | show the thing the narration has been withholding |
| `evidence` | a document, quote or figure |
| `portrait` | a person, held long enough to matter |
| `locate` | where this is happening — map, route, position |
| `compare` | two things side by side |
| `list` | enumerate; items arrive one at a time |
| `annotate` | mark up something already on screen |
| `emphasise` | make one already-present thing dominant |
| `transition` | close one movement and open the next |

---

## `hooks`

Where a Short can be cut from. This decision is made here, once, with the whole
script in view — not later by an editor hunting for a loud moment.

```json
{ "id": "h1", "kind": "cold-open", "from": "l1", "to": "l4",
  "short_worthy": true, "why": "the cloud lands before any context" }
```

`python3 scripts/beatplan.py plan.json --shorts 3` turns these into concrete
windows with start and end seconds, sorted by how well each fits the target
length, and tells you plainly when there are not enough marked.

`kind` is free text — `cold-open`, `stat`, `contradiction`, `question`,
`reveal` are the useful ones.

---

## `loops`

An open loop is a promise. `opens` is the line that makes it, `pays` is the line
that keeps it.

```json
{ "id": "q1", "opens": "l2", "pays": "l31" }
```

The validator fails a loop that pays at or before it opens. An unpaid loop is
the cheapest way to lose an audience, and the easiest thing to miss when you are
inside the script.

---

## What the validator checks

**Errors** (it will not pass):

- schema version it cannot read
- duplicate or missing line ids; a beat pointing at a line that does not exist
- an `intent` or `safe` outside the vocabulary; `emphasis` outside `0..1`
- beats out of chronological order
- a missing audio file
- a loop that pays before it opens; a hook pointing at a missing line

**Warnings** (advice, and `--strict` makes them fail):

- beats closer than 1.5 s or further apart than 6 s
- an overall pace outside one beat every 2–4 s
- a keyword that is not spoken in its own line
- absolute times instead of line-relative ones
- a line with no measurable length
- no hook marked `short_worthy`
