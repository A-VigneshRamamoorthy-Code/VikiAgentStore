# Quality screening — `qa.py`

Catches the two defects a listener notices first and a spectrum plot does not:
**uneven pauses** and **a single letter yelping to the wrong pitch**.

```bash
.venv/bin/python scripts/qa.py --manifest out/cast/manifest.json   # whole cast
.venv/bin/python scripts/qa.py --detail out/cast/zane.mp3          # timestamps
.venv/bin/python scripts/qa.py --json out/cast/*.mp3               # machine-readable
```

Output is a table per clip: pause count, longest pause, spike count, verdict.
`--detail` prints the timestamp, size in semitones, absolute Hz and duration of
every spike so you can seek straight to it.

This is a **screen, not a verdict**. It tells you where to listen.

## Uneven pauses

A pause is flagged when it is either longer than `LONG_PAUSE_S` (1.0 s) or more
than `PAUSE_RATIO` (4×) the clip's own median pause. The ratio matters more than
the absolute: a measured, slow read has long pauses everywhere and none of them
are wrong, while one 0.9 s gap in a brisk 0.2 s-paced read is jarring.

Leading and trailing silence within `EDGE_MARGIN_S` (0.35 s) is ignored — that is
mastering headroom, not a pause.

The shipped cast has **zero** flagged pauses; every clip's longest internal gap
sits between 0.36 s and 0.41 s. Concatenated multi-chunk narration was checked
separately and stays in the same band (0.33 s across a 3-sentence render), so
chunk joins do not introduce seams.

## Pitch spikes

A spike is a short excursion of ≥ `SPIKE_ST` (6 semitones) above the local
baseline, lasting between `SPIKE_MIN_S` (0.06 s) and `SPIKE_MAX_S` (0.22 s).

The bounds define "a single letter". Shorter than 60 ms is a glottal blip nobody
hears; longer than 220 ms is intonation, which is supposed to move. The baseline
is a median-filtered F0 track, so a slow rise across a question does not fire —
only a jump *away* from where the voice already is.

### The octave-error trap

Naive autocorrelation F0 tracking reports **double** the true pitch on isolated
frames. The first version of this tool flagged all 9 voices — Zane's "spikes"
sat at 320–400 Hz against a 158 Hz median, exactly 2×, lasting a single 20 ms
frame. Those were measurement errors, not audio defects.

The fix is **octave folding**: any frame more than `_OCTAVE_FOLD_ST` (10 st) from
the clip's median is halved or doubled toward it before analysis. 10 st sits
above real artefacts (~9 st) and below a true octave error (12 st).

**Do not** "fix" this by preferring the longest strong autocorrelation lag. For a
periodic signal the ACF at twice the true period is also strong, so that rule
systematically reports *half* the pitch. It was tried: it made Meera report a
"+11.6 st spike" at 231.9 Hz — *below* her own 238.8 Hz median — because the
local baseline had collapsed to ~119 Hz. Both the trap and the fix are in
`f0_track()`'s docstring.

Accepted limitation: an artefact landing within 1–2 st of an exact octave is
folded away with the glitches. That is deliberate. A screen that flags 9 out of 9
clips gets ignored.

## The budget

`SPIKE_BUDGET = 3` — above this, a clip is flagged `CHECK`.

Calibrated against audio a listener had **already approved**, not against zero:
raw Edge Valluvar scored 0 spikes and raw Edge Pallavi 1 — the cleanest audio
measured — while clones the same listener rated "much better" than the rejected
versions carried 2–3. Three is therefore the top of the known-good range.

Calibrating against approved audio rather than an ideal is what turned this tool
from useless (9/9 flagged) into discriminating.

## Spikes in candidate selection

`build_cast.py` folds the spike count into `candidate_score()` at
`SPIKE_WEIGHT = 0.02` per spike, so best-of-N actively prefers clips that do not
squeak. One spike costs about as much as 2 % pitch drift — enough to break a tie,
not enough to override a genuinely wrong voice.

Measured effect: Karthik went from **5 spikes to 2** on a `--tries 4` rebuild.

## When a voice will not come clean

Compare the clone against its own reference:

```bash
.venv/bin/python scripts/qa.py --detail out/refs/<key>.wav
```

If the reference is clean and the clone is not, the spikes are a cloning
artefact and more `--tries` may find a better candidate. If the reference spikes
too, the delivery itself is doing it and no amount of re-rolling will help —
re-cut the reference or accept it.

An onset spike in the first ~0.1 s is almost always a first-phoneme artefact
rather than delivery, regardless of what the reference does.

## Guarding the detector

```bash
.venv/bin/python scripts/test_qa.py     # 11 synthetic cases, 22 assertions
```

Synthetic signals with known ground truth: a single injected spike, two spikes, a
female-register spike — and, more valuably, the negatives that must **not** fire
(a slow intonation rise, a 20 ms micro-blip, mild stress, edge silence). Run it
after touching any threshold.
