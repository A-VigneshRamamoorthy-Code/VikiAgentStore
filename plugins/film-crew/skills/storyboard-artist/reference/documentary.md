# Boarding a documentary

Everything here is measured from a 29-minute investigative documentary with 24
million views, not asserted from taste. It is the visual half of the register
described in
[`../../story-editor/reference/hooks.md`](../../story-editor/reference/hooks.md#the-documentary-cold-open).

## The one hard constraint: primary sources only

Every image in the reference is a **primary source** — an archival photograph, a
document, a newspaper page, a piece of evidence, or a map. There is no
reenactment footage, no stock B-roll, and no actor anywhere in the film.

This is not a stylistic preference. It is what makes the film *evidence* rather
than *illustration*, and it is the reason viewers argue about the suspects in
the comments instead of arguing about the film.

| allowed | banned |
|---|---|
| archival photographs | dramatised reenactment |
| documents, memos, transcripts | stock footage of "a man in a hat" |
| newspaper clippings and front pages | actors, hands, silhouettes standing in for people |
| evidence photography | AI-generated "photographs" of real events |
| maps, diagrams, flight paths | generic mood B-roll |
| composite sketches | anything implying a scene nobody photographed |

If a beat has no primary source, the beat is boarded as **text on the board** —
a quoted line, a date, a name — not as an invented picture. An absence of
imagery is honest. A fabricated image is not, and in a film whose subject is
*what nobody knows*, it is self-defeating.

## Objects are characters

The reference returns repeatedly to a small cast of physical objects, each with
its own photograph:

- the ransom money, and the rubber bands around it
- the airstair placard
- the recovered tie, and a single titanium particle from it
- the composite sketches
- the sandbar where the money surfaced

Give the three or four objects that carry the story their own recurring
treatment, and reuse the *same* image each time. A viewer who has seen the
rubber bands twice recognises them the third time, and that recognition is what
makes a long film feel tight rather than long.

Board them as named elements so the style renders them consistently.

## Geography is shown, not narrated

A place-based mystery gets an **animated map**, not a location name in the
narration. The reference animates the flight path, the drop zone estimate and
the recovery site. Three named places in a sentence with no map is three places
the viewer does not retain.

Board a map beat wherever the story moves, and mark what changes on it — a
path drawn, a radius shaded, a pin dropped.

## Chapters are visible

The reference is cut into five named chapters plus an intro and an outro:

```
0:00  Intro
0:50  Chapter 1: The Hijacking
5:07  Chapter 2: The Manhunt Begins
8:12  Chapter 3: Follow the Money
12:34 Chapter 4: A Leap of Faith
18:46 Chapter 5: The Suspects
28:05 Outro
```

Each gets a **held title card**. Three things this buys:

1. A structural promise — the viewer can see the film has a shape.
2. A rest between dense sections, which is what makes 29 minutes survivable.
3. YouTube chapter markers, which are a real ranking and navigation signal.

Chapter names are **noun phrases about the story**, never "Part 2". *Follow the
Money*. *A Leap of Faith*. They read as chapter titles in a book, and each one
is a small promise of its own.

Board a chapter card as its own beat, and give it real screen time — the
reference holds its opening title for around 27 seconds.

## Pacing on the board

| section | seconds per image |
|---|---|
| cold open | long holds, 4–8 s, almost no cuts |
| body | 3–5 s per image, with slow continuous motion on each |
| evidence close-ups | 2–3 s, and always after the claim they support |
| chapter cards | 3–5 s, longer for the opening title |

Motion is a **slow pan or push on a still**, never a fast move. The film is
made of photographs; the camera's job is to keep them alive, not to be noticed.

## What this looks like in a beat plan

```json
{ "id": "b7", "lines": ["l18", "l19"],
  "shot": "evidence",
  "subject": "the recovered tie, close",
  "source": "FBI evidence photograph, 1971",
  "motion": "slow push",
  "hold_s": 3.0 }
```

`source` is not decoration — it is what the
[`rights-manager`](../../rights-manager/) clears and what stops an invented
image reaching the screen.
