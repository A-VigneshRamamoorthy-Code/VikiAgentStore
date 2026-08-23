# Verification — how to know a voice is actually good

Synthetic speech fails in ways that are obvious in numbers and easy to miss by
ear, especially when you have listened to forty clips in a row. Measure first,
then listen.

```bash
.venv/bin/python scripts/analyze.py out/cast/*.mp3
.venv/bin/python scripts/analyze.py --compare source.m4a clone.mp3
```

---

## The five checks

| Check | Expected | A failure means |
| --- | --- | --- |
| **Duration** | proportional to text length | `duration_s` was set, or generation truncated |
| **Gaps > 0.5 s** | exactly **0** | fixed-canvas padding — the classic `duration_s` bug |
| **Noise floor** | < −45 dB | the reference wasn't denoised |
| **Median F0** | inside the gender range | wrong reference, or the clone failed |
| **F0 vs source** | within ~5 % | the clone didn't inherit the timbre |

Gender ranges: **male 85–180 Hz**, **female 165–265 Hz**. These catch gender
inversion, not stylistic drift — don't narrow them to enforce a house sound.

Same-gender siblings cloned from the **same** recording need **≥25 Hz**
separation or they blur together. Siblings from **different** recordings also
differ in accent and cadence, so a smaller gap is acceptable; `build_cast.py`
downgrades that case from an error to an advisory note.

---

## Why each one exists

**Identical durations across clips** is the signature of `duration_s` being set.
Eight clips all at exactly 13.000 s is not a coincidence; it is the model padding
to fill a canvas. The padding shows up as silent gaps.

**Noise floor above −45 dB** means hiss got cloned into the voice. Filtering the
output cannot fix it — the reference has to be denoised before cloning. See
`reference/omnivoice.md`.

**F0 outside the gender range** catches the failure where the reference didn't
load and the model fell back to its own default speaker. It also catches
`instruct`-style gender inversion.

**F0 drift from source** is the direct test of whether cloning worked at all. Under
5 % means the timbre transferred; 20 %+ means you got a different voice than you
asked for. Because generation is stochastic, judge drift over a *best-of-N* build
(`--tries 3`), not a single lucky or unlucky draw.

---

## Two checks the five don't cover

The five acceptance checks prove a clip is technically sound. They cannot tell you
whether it is **intelligible** or whether two voices are **actually distinct**.

### Pronunciation — `intelligibility.py` and `build_ab.py`

Synthesizes a line through each candidate, transcribes it back with Whisper and
scores the match against the input text.

```bash
.venv/bin/python scripts/intelligibility.py a.mp3 b.mp3 --text-file line.txt --lang ta --show
.venv/bin/python scripts/build_ab.py     # the full, multi-line reference ranking
```

It is a **proxy, not a verdict** — Whisper has its own error rate on colloquial
Tamil, and it cannot hear a botched ழ. Use it comparatively.

**Average over several lines.** A single line is not a measurement: one reference
scored 85.0 % on one Tamil line and 93.4 % on another, which reversed the entire
ranking. `build_ab.py` averages three lines in different registers and reports
the spread; treat any gap smaller than the spread as a tie.

Used properly it is still the only objective handle on pronunciation, and it has
overturned assumptions here more than once — including retiring a claim, made
from a single line, that trimming a reference improved its pronunciation.

### Reference fidelity — `check_refs.py`

Transcribes each character's reference and compares it to the stored `ref_text`.

```bash
.venv/bin/python scripts/check_refs.py --characters templates/characters.json
```

Anything flagged SUSPECT will clone badly. Note the two-way failure mode: a low
score can mean the transcript is wrong, *or* that the clip contains something that
doesn't belong (a second language, a second speaker). Read the diff it prints
before deciding which.

The thresholds are **language-aware**, because Whisper is markedly worse at
colloquial Tamil: a correctly aligned Tamil reference can score in the mid-70s
with every word right and only the spelling different. Always read the diff
before editing a `ref_text` — if the words match, the reference is fine.

It also honours `ref_trim`, checking the transcript against the **kept span**
rather than the whole source file. Without that, every trimmed reference reports
a false SUSPECT.

### Distinctness — `timbre.py`

F0 alone is a poor distinctness metric. Harper and Imogen sit 13.2 Hz apart and
are the *most* distinct pair in this cast (0.808, American vs British); Meera and
Divya sit 19.3 Hz apart — wider — and are the *least* (0.959). `timbre.py`
compares MFCC profiles, so accent and delivery count.

### Failures no measurement can see — `test_nonverbal.py`

Some defects produce clean audio. An unrecognised bracket tag is the clearest
case: the model performs `[sigh]`, but reads `[pause]` aloud as the word "pause",
and matching is case-sensitive so `[Sigh]` is read out too. Duration, F0, noise
floor and gaps are all perfectly normal — the take is simply wrong.

The only defence is to check the text *before* generating, which `voice.py` does.
The test pins `core.NONVERBAL_TAGS` to OmniVoice's own regex and cross-checks
every verdict against it, so a model upgrade that changes the tag list fails
loudly instead of degrading quietly:

```bash
.venv/bin/python scripts/test_nonverbal.py
```

The general lesson: when a failure mode leaves the audio valid, no acceptance
metric will find it — move the check upstream of synthesis.

---

## Raw ffmpeg recipes

Useful when debugging outside the scripts.

```bash
# duration
ffprobe -v error -show_entries format=duration -of csv=p=0 clip.mp3

# noise floor and peak/RMS
ffmpeg -i clip.mp3 -af astats=metadata=1:reset=0 -f null /dev/null 2>&1 \
  | grep -E "Noise floor|Peak level|RMS level"

# silent gaps (count silence_start lines)
ffmpeg -i clip.mp3 -af silencedetect=n=-45dB:d=0.5 -f null /dev/null 2>&1 \
  | grep -c silence_start

# overall loudness
ffmpeg -i clip.mp3 -af volumedetect -f null /dev/null 2>&1 | grep mean_volume
```

Median F0 uses autocorrelation over voiced frames only — see `median_f0()` in
`scripts/core.py`. Unvoiced frames and silence are excluded, otherwise the median
is meaningless.

---

## Browser decode: HTTP 200 is not proof

A truncated or malformed mp3 is still served with status 200, and then plays as
silence. To actually verify a gallery:

```bash
.venv/bin/python scripts/serve.py --verify
```

It decodes every clip through `AudioContext.decodeAudioData` in a real browser and
reports the duration each one yields. A clip that 200s but fails to decode shows
up as `FAIL`.

---

## What measurement cannot tell you

Three things need a human, and one needs a native Tamil ear:

1. **Does it sound like a person?** Naturalness of delivery has no metric here.
2. **Does the persona match the name?** Whether "Arun" sounds like a warm
   documentary narrator is a judgement call.
3. **Tamil phoneme accuracy.** ழ / ள / ண / ற / ன, and post-nasal voicing
   (சிங்கம் → "singam", not "sinkam"). No measurement in this skill detects these.
   A voice can pass every numeric check and still be unusable for Tamil.

Always audition before approving. The numbers only tell you it isn't *broken*.

---

## Mastering

Applied by `master()` in `core.py`:

```
highpass=f=80                                    remove rumble
equalizer=f=2800:t=q:w=1.5:g=2.0                 presence / intelligibility
acompressor=threshold=-20dB:ratio=3:...          even out level
silenceremove=...                                trim dead air
loudnorm=I=-16:TP=-1.5:LRA=11                    broadcast loudness
```

−16 LUFS is the podcast/streaming target. This is not cosmetic — raw model output
is quiet and uneven, and the loudness difference alone makes an unmastered clip
sound worse than a mastered one in an A/B comparison, independent of the voice.

Note the compressor **lifts residual hiss along with quiet speech**, which is why
reference denoising matters so much.
