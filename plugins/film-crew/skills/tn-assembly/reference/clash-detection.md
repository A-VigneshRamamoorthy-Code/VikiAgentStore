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
