# Clash detection

Finding the fights, acoustically, without watching eight hours.

## What a clash sounds like

A civil debate and a shouting match differ in ways that survive in the audio
even at low bitrate:

| | Orderly speech | Clash |
|---|---|---|
| Turn-taking | Regular pauses between speakers | Nobody yields; gaps disappear |
| Noise floor | Drops to room tone between phrases | Never falls — someone is always talking |
| Spectrum | Structured, harmonic | Flattens toward noise as voices overlap |
| Onsets | Paced | Dense and irregular |

`analyse.py` measures exactly these. Per second it computes `db`, `peak_db`,
`min_db`, spectral `flat`ness and spectral `flux`, then scores sliding windows
for **continuity** (does the floor ever drop?), **flatness** and **onset
density**.

## The calibration that made it work — worth reading before tuning anything

The first implementation measured continuity as "what fraction of this window
is quiet", using an **absolute** RMS threshold. Run against a real eight-hour
session it produced **40 candidates and 0 clashes**.

Dumping the distributions showed why: the median second of that webcast was
already 32% "quiet" by that threshold. Continuity could therefore never reach
the 0.90 gate, no matter what happened in the chamber. The threshold was
measuring the mix, not the argument.

Two changes fixed it:

1. **Use the per-second noise floor (`min_db`), normalised against the
   session's own distribution**, instead of an absolute quiet fraction. Turn-
   taking drops the floor into room tone; shouting over one another never lets
   it fall. This is a property of the conversation, not of the gain staging.

2. **Gate on outliers, not on fixed values.** The clash gate is
   `max(p93, median + 3·MAD)`, with continuity above p85 and flatness above
   p80. A fixed gate either fires on every session or on none, depending
   entirely on how hot the source was mixed.

Re-run on the same audio: **40 candidates, 1 clash, at `00:41:25`** — the
segment that had independently been hand-labelled *"சபையில் சூடான வாக்குவாதம்"*
(heated exchange) when the session was reviewed by hand.

The general lesson, which applies to every threshold in this skill: **judge a
moment against the session it came from, never against a constant.**

## Because it is outlier-based, a calm session yields nothing

That is correct behaviour, not a bug. If a sitting contained no clash, the
detector should flag none. Do not lower the gate to force a result — see
`editorial-ethics.md`.

## The confirmation rule

**A clash flag is a candidate, never a fact.**

These all look like a clash on a spectrogram:

- Sustained applause
- Laughter across the chamber
- Desk-thumping
- A crowded procedural interruption where everyone speaks at once
- An audio fault or feedback

Before any title, thumbnail or Short claims a confrontation, **confirm it** by
watching the segment or transcribing it. `analyse.py` emits `clash_pct` and
`clash_sigma` precisely so a human can see how unusual the moment was; a
4.45-sigma flag deserves a look, a 1.4-sigma one does not.

### Confirming it without a human in the loop

An unattended session cannot stop and ask, so the rule above has to be
mechanised. One signal is never enough. Measured on a single sitting:

| Window | `clash_pct` | What it actually was |
|---|---|---|
| sh06 | 98 | A real row — member pointing, the chair's palm up |
| sh09 | 97 | A real row — papers brandished, members on their feet |
| sh13 | 91 | **The chair alone, calmly reading a procedural note** |
| sh17 | 89 | **A speech about yoga** |

Loudness alone would have titled the bottom two as fights. Two further
signals separate them, and a confrontation is claimed only when they agree:

1. **The words members use when contesting the floor.** A row transcribes as
   short overlapping phrases about who may speak — *"I'm not speaking / you're
   not speaking"*, *"explain it!"*, *"one minute"*, *"sit down"* — repeated.
   Count those phrases, and count repetition itself: the same short phrase
   four or more times is something no prepared speech does.
2. **The camera.** During a row the gallery director cuts around the chamber —
   wide shots, members on their feet, reaction angles. During a speech the
   camera holds one face for a minute at a time. Measured: **8.8 cuts/min for
   a row against 0.9 for the chair reading**. `ffmpeg -vf select='gt(scene,
   0.25)'` counts them in a few seconds per clip.

### Wiring that check to a plan item

Two details make the difference between a working test and dead code, and
both failed silently in a live sitting:

- **Plan items do not carry the clash fields.** A `plan.json` entry has
  `theme`, `start`, `end`, `tc`, `label`, `gloss`, `parent` and `vip` — and
  nothing else. `clash` and `clash_pct` live only in `meta/candidates.json`,
  so a check written as `item.get("clash_pct")` reads `None` on every item
  and quietly answers "not a confrontation" every time. Match the plan item
  back to its candidate **by window overlap** and read the score from there.
- **`clash_pct` is a percentile on 0–100, not a fraction on 0–1.** A
  threshold written as `>= 0.90` is wrong by a factor of a hundred and passes
  everything; written as `>= 90` on a 0–1 field it passes nothing.

With both fixed, the working thresholds are **`clash_pct >= 97` and
`>= 5 cuts/min`**, and they hold up against the same sitting's own numbers:

| Window | `clash_pct` | σ | cuts/min | Verdict |
|---|---|---|---|---|
| 01:23:30 | 99.7 | 4.72 | 7.2 | confirmed row — alliance argument and a walkout |
| 01:42:30 | 98.8 | 3.68 | 9.5 | confirmed row — *"பேரவைத் தலைவரே!"* ten times |
| 01:15:05 | 99.0 | — | 4 | correctly rejected — loud, but the camera holds |
| 00:08:40 | 93.1 | — | 2 | correctly rejected — a speech, and it has a subject |

Note the third row: the single most turbulent-sounding window of that sitting
was **not** a row. Percentile alone would have titled it as one.

### The inverse error, which is more expensive

A row destroys the transcript that would be used to name it. Members shouting
over each other produce almost no intelligible speech, so a keyword-based
titler finds no subject and the moment is discarded as "a loud minute with
nothing in it".

That reasoning is backwards, and it is costly: one session held back **five of
its most turbulent windows — including a 98th-percentile one — while
publishing 44th- and 50th-percentile stretches of routine business.** The
collapse *is* the evidence. A prepared speech at the 97th clash percentile
still transcribes; loud *and* wordless does not happen by accident.

So when a high-clash window yields no subject, test it as a row before
dropping it: **loud, wordless, and the camera cutting** is a confrontation,
and it is publishable. Name it for what is verifiable — that the House was in
uproar, that an explanation was demanded, that a member was shouted down —
never for who won or for words the transcript cannot actually support.

A later sitting shipped this escape hatch and still lost the same material,
because the check was written against fields the plan item does not carry (see
above) and so never once returned true. Dead code and a missing rule fail
identically from the outside — the log simply says *"not a confirmed
confrontation"* either way. Once repaired, that sitting's two genuine rows
published, and the confirmed-clash path also produced their titles: with no
usable transcript the label is the verifiable one, `சட்டப்பேரவையில் அமளி`
("uproar in the Assembly"), which is cleaner than the garbled quote the ASR
offered for the calmer clips around them.


## Reading the output

`meta/candidates.json` rows:

| Field | Meaning |
|---|---|
| `start`, `end`, `tc` | Window on the source timeline |
| `highlight` | Combined interest score, 0–1 |
| `clash` | Clash-specific score, 0–1 |
| `continuity` | How rarely the noise floor dropped |
| `flatness` | Spectral flatness — overlapping voices raise it |
| `onset` | Onset density |
| `clash_pct` | Percentile of this window's clash score in this session |
| `clash_sigma` | Robust standard deviations above the session median |
| `kind` | `clash` or `speech` |

## Tuning

Prefer changing `longform.keep_fraction` (how much of the session is
publishable) over the clash gate. If you must adjust the gate, move the
percentile, not to an absolute score — the whole point is that absolute scores
do not transfer between sessions.
