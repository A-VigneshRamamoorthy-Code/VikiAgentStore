# Comedic timing

A gag is a four-part structure with frame counts. Get the counts wrong and a
funny idea lands flat; get them right and a thin one still works.

```
SETUP  ──────────► ANTICIPATION ──► SNAP ──► HOLD
(as long as        (3–12 frames,    (1–4    (20–36 frames.
 it needs)          held at peak     frames)  This is the laugh.)
                    for 2–4)
```

---

## The four parts

### Setup

Establish what is normal. It can take as long as it needs, and it is the only
part with no frame count, because the audience must accept the ordinary version
before the departure from it means anything.

The commonest failure is not a slow setup — it is a setup that is *already
funny*. Play it completely straight.

### Anticipation

The wind-up, against the direction of the coming move. The counts are
`poses.ANTICIPATION_FRAMES`, at 30 fps:

| action | wind-up | held at peak |
|---|---|---|
| head turn | 3 | 2 |
| run start | 5 | 2 |
| jump | 7 | 3 |
| big reaction | 12 | 4 |

That tiny freeze before the release is what makes the snap read as a snap, and
it is why `anim.ease("anticipate")` has a flat section in the middle of it
rather than a smooth valley.

### Snap

One to four frames, with a smear in the middle if the move is fast. This is the
part the audience does not consciously see, and it is the part that must not be
eased smoothly — fast departure, overshoot 8–15%, settle. The shipped
`overshoot` curve sits mid-band at 12%.

### Hold

**The joke.**

| | frames | seconds |
|---|---|---|
| standard gag | 20–36 | 0.7–1.2 |
| the film's central joke | 48–72 | 1.6–2.4 |

`shots.MIN_HOLD_FRAMES` is 20, and `pacing_report` says so when a `hold`-tier
shot comes in under it. It only *says* so — nothing in the pipeline clips a
hold, because a hold that runs long on purpose is the entire technique.

Cutting away on the punchline is the most common error in comedy animation. The
audience needs room to register the gag; a cut steals it. If a film feels
unfunny despite good jokes, this is almost always why.

A hold is **not** a freeze frame: breathing continues and the character blinks
every 72–96 frames — which, since `poses.stand` blinks once per three-second
cycle, means driving the actor at `rate: 0.33` rather than the default `1.0`.

---

## What the pacing report will tell you

`shots.pacing_report` measures the cut list against the style's bands. All of
it is advisory; none of it raises:

| measure | band |
|---|---|
| mean shot length | 3.0 – 4.0 s |
| cuts per minute | ~15.5 – 23.3 |
| a reaction shot | 1.0 – 1.5 s |
| a setup shot | 6 – 10 s |
| a `hold`-tier shot | ≥ 20 frames |

The cut rate is derived rather than chosen: 30–45 cuts across *Summit*'s
verified 116 seconds. A comedy that cuts slower than 15 a minute is a drama; one
that cuts faster than 23 has no room left for a hold, and the holds are the
jokes.

The reaction and setup rows only fire on a shot that says what it is —
`pacing_report` matches the shot's `beat`, or failing that its `kind`, against
`reaction`/`react`/`cut-in`/`cutin` and `setup`/`establish`/`establishing`/
`reveal`. A board compiled from a beat plan carries the beat's *id* in `beat`,
so those two checks stay silent unless you add `"kind": "reaction"` yourself.
Worth doing on the handful of shots where the timing is the joke.

The worked example scores: 25 shots, mean ≈ 3.1 s, median ≈ 3.3, range
0.35–6.76, 19.3 cuts a minute, 11 holds, 2 impacts — comfortably inside every
band, with one note about a 0.60 s hold that should have been 20 frames.
(The mean and median shift by a few hundredths as the example is retuned; the
bands are the stable thing, and it sits mid-band on all of them.)

---

## Rules that make it funnier

**Nobody in the film knows it is funny.** The moment a character acknowledges
the joke — a look to camera, a smirk — the premise collapses. Everyone plays
their situation completely straight. The one deliberate exception is a *final*
button, after the story is over.

**Let the frame be still.** Comedy lives in stillness far more than in motion.
A held wide shot of something absurd is funnier than the same thing with a
camera move over it, because the move tells the audience where to look and the
stillness makes them find it.

**Escalate on a schedule, and never resolve early.** Each beat should raise the
stakes of the misunderstanding without anyone noticing. The audience is ahead of
the characters; that gap is the comedy, and closing it ends the film.

**The straight man does the reacting.** Put the audience's reaction on screen,
in one character, and let the absurd one stay oblivious. The oblivious character
is never the funny one — the reaction is.

**Undercut immediately after a big claim.** The gap between an assertion and the
picture that follows it is the cheapest reliable laugh available, and it is what
the `pursuit` example is built entirely from: a reporter says *"speeds
approaching twenty-two miles per hour"* and a cyclist overtakes.

**Repeat, then break.** Three is the number. Establish a pattern twice, break it
the third time. The break is funnier for costing nothing to set up.

---

## Timing a gag against narration

When a narrator is involved, the gag's structure lives in the **gaps**, not in
the lines.

| line type | `gap_after` |
|---|---|
| setup | 0.4–0.6 s |
| punchline | 1.0–1.5 s |

That is the whole technique. A script whose gaps are all 0.6 s has no comedy in
it regardless of what the words say, because every joke is trodden on by the
next line. Look at
[`../examples/pursuit/script.md`](../examples/pursuit/script.md): its setup
lines run 0.35–0.7 s and its punchlines run 1.0–1.6 s, and the difference
between those two numbers is the entire difference between the film working and
not. The default, when a line says nothing, is `timing.gap` — `0.55 s`, which is
setup pacing, so **a punchline must always say so explicitly**.

**The picture should land the joke slightly before the narrator does, or well
after — never simultaneously.** Simultaneous is the one option with no comedy in
it. Landing early lets the audience get there first, which is the best feeling
a comedy can give them; landing late is a second, separate laugh.

---

## What this means for the motion budget

Comedy is unusually cheap to animate, and this is a genuine gift.

The animation director's distribution law wants ≥35% of beats `hold` and ≥62%
`hold` or `limited`. A comedy satisfies that **for story reasons**: its held
shots are held because stillness is funny, not because the budget ran out. The
expensive cut then goes to a climax that turns out to be a traffic light.

That alignment is worth noticing. In a documentary the distribution law is a
constraint you work within. Here it is simply a description of good comic
timing.
