# Matching a reference

How to make output measurably resemble a reference film instead of
approximately resembling it from memory.

This whole skill was built by measuring a reference rather than describing it,
and the `crime` music bed was fitted this way end to end. The method
generalises to any "make it sound/look like *that*" request.

---

## The principle

**Turn taste into a number, then minimise it.**

"It doesn't feel right" cannot be iterated on. A scalar distance between your
output and the reference can be — you can grid-search it, and you can tell
whether a change helped. Every hour spent building the metric pays for itself
the moment you have three candidate settings and no idea which is best.

---

## The procedure

### 1. Extract and find clean windows

You need windows of the reference containing **only** the thing you are
measuring. For music that means gaps between narration:

```bash
ffmpeg -i reference.mp4 -ac 1 -ar 48000 /tmp/ref_full.wav
```

Then locate quiet-in-the-voice-band spans, and **listen to each one before
trusting it**. In our reference, one apparently perfect "music-only" window at
0.70–1.35 s was actually a paper-whoosh sound effect. Its 6446 Hz centroid
would have dragged the entire fit towards a hiss.

Three verified windows were enough: `(5.45, 6.20)`, `(10.60, 11.15)`,
`(13.40, 14.50)`.

### 2. Choose a representation that survives comparison

Use an **averaged fixed-window power PSD** — 4096-point FFT, hop 2048 —
collapsed into a handful of bands:

```
<80 Hz | 80–250 | 250–1k | 1–4k | >4k        (normalised to sum 1)
```

Bands, not raw spectra: you want a handful of numbers you can read and reason
about, not 2049 you cannot.

### 3. Define the objective

L1 distance between the normalised band profiles. Simple, bounded,
interpretable — and each term tells you *which* part of the sound is wrong,
which a single scalar like centroid never does.

### 4. Measure the candidates, then search

Measure every option you already have before inventing new ones. For the music
that meant scoring all four existing moods against the reference:

| Mood | `<80` | `80–250` | `250–1k` | `1–4k` | `>4k` | L1 |
|---|---|---|---|---|---|---|
| *reference* | 0.428 | 0.355 | 0.170 | 0.013 | 0.034 | — |
| **`crime`** | 0.478 | 0.346 | 0.094 | 0.029 | 0.053 | **0.170** |
| `memorial` | 0.770 | 0.150 | 0.077 | 0.001 | 0.001 | 0.682 |
| `tension` | 0.783 | 0.088 | 0.116 | 0.010 | 0.002 | 0.709 |
| `music_box` | 0.161 | 0.043 | 0.748 | 0.046 | 0.002 | 1.221 |

The table immediately says *why* each is wrong: `music_box` is all midrange,
`tension` and `memorial` are all sub and hollow in the body. That diagnosis is
what tells you which knob to turn.

---

## Three traps that will waste your afternoon

### Comparing spectra across unequal lengths is invalid

A magnitude-sum band ratio from a 0.55 s reference clip against a 20 s bed
makes the wide high bands look enormous — they simply contain far more FFT bins
at finer resolution. This made one bed look **2.4× too bright** when
per-instrument measurement showed the opposite. The apparent problem was
entirely an artefact.

**Always compare equal-length windows with the same FFT size**, or use an
averaged PSD on both sides.

### Spectral centroid cannot hear

Across tick settings spanning band-pass 1650 → 1050 Hz and decay
0.0075 → 0.022 s — parameters that changed the sound *completely* — the
centroid moved 5796 → 5851 Hz. Under 1% for a total timbral rewrite.

Centroid is a single moment of a distribution. Use band ratios.

### Onset counts are threshold-sensitive

They shift with gain, so treat them as directional, not absolute. Useful for
"is there a pulse at all", useless for "is the pulse right".

---

## Deriving parameters, not just scoring them

The same measurements give you the settings directly:

| Property | Method | Result |
|---|---|---|
| Root note | Energy at candidate fundamentals | **D1, 36.71 Hz** — 4.7× the next candidate |
| Tempo | Sub-band autocorrelation of spectral flux | **92.75 bpm** |
| Beat vs eighths | Compare alternate onset strengths | 6.3 vs 8.0 → the beat is the *slower* value, 185.5 was eighths |

That last row is the kind of thing measurement catches and ears argue about.

---

## Design conclusions that fell out of the fit

Worth knowing because they are counter-intuitive:

1. **The pulse belongs in the body, not the sub.** `pulse_bass` is voiced at
   `root*4` so its fundamental lands in 80–250 Hz. An octave down it scooped
   the mids out and the bed stopped reading as music — 0.152 there against the
   reference's 0.355.
2. **Percussion belongs above 4 kHz.** A click at 2.4 kHz sits on top of the
   narration. Moving `tick` to 5.4 kHz cut voice-band energy more than
   threefold and let `mix.music` come **up** from 0.42 to 0.55 — the bed got
   *louder* and the voice got *clearer*.
3. **Anything bright competes with the voice.** `pluck` is low-passed with two
   poles at 1.6 kHz for the same reason.

The general lesson: **when a bed fights the narration, move it out of the way
in frequency before you turn it down.** Turning it down costs you the bed;
moving it costs you nothing.

---

## Know when to stop

Stop when the residual is smaller than the thing you are trying to hear. Our
remaining gap is almost all in 250 Hz–1 kHz (0.094 against 0.170) — the
reference has more midrange body than our pluck supplies. That is the honest
next improvement, recorded rather than papered over.

And check the fit end to end, not just the component: in the finished mix the
voice sits **+21.1 dB over the bed at 1–4 kHz** against the reference's
**+20.2**. Within a decibel in the band that governs intelligibility is the
result that actually matters — see [`verification.md`](verification.md).
