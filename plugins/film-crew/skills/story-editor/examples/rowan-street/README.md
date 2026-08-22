# Rowan Street — a worked example

262 words · **2:19** · 112.5 gross wpm · `en-GB-RyanNeural` at `--rate="-25%"
--pitch="-5Hz"`

A woman walking home from a night shift notices that a window lit for nine years
has gone dark, and knocks on the door.

| File | What it is |
|---|---|
| [`script.txt`](script.txt) | The narration exactly as fed to edge-tts. Punctuation is the only markup. |
| [`storyboard.md`](storyboard.md) | Beat-by-beat map: which technique each line implements, the loop ledger, the visual plan and the audio mix. |

Reproduce the audio:

```bash
edge-tts --voice en-GB-RyanNeural --rate="-25%" --pitch="-5Hz" \
  --file script.txt --write-media rowan-street.mp3 --write-subtitles rowan-street.srt
```

---

## Why this example is here

It shows what the rules cost. Four things in it are the direct result of a
constraint in the reference modules rather than a stylistic preference:

**1. The rate is `-25%`, not the `-15%` default.**
Measured, not assumed:

| Rate | Duration | Gross wpm | Band |
|---|---|---|---|
| `-15%` | 123.2s | 127.5 | Explainer — too brisk for this story |
| `-20%` | 130.9s | 120.1 | Still high |
| **`-25%`** | **139.7s** | **112.5** | **Intimate / documentary** |

Only safe because every sentence is 8–16 words. A slow rate over long sentences
reads as sedated.

**2. Nine years is written, never "9".**
No digits survive in the script — the engine would have to guess. Same reason
there are no parentheses anywhere, despite two places where an aside would have
been natural on the page.

**3. The payload word is always last.**
There is no `<emphasis>` in edge-tts, so end-focus is the only stress available.
"Nobody came." and "Always." are one- and two-word sentences precisely because
that is the only way to make the engine land on them.

**4. The ending refuses the easy win.**
"The house sold anyway." The loop still pays — the light continues — but the cost
stands. An ending where the house is saved would be a coincidence rescue, which
[`loops.md`](../../reference/loops.md#endings) lists as a cheap ending.

---

## The loop ledger

```text
A — why is the window lit?    OPEN 0:06  PROGRESS 1:11         CLOSE 2:02
B — will Maya get an answer?  OPEN 0:28  PROGRESS 0:43, 0:52   CLOSE 1:41
C — who was the lamp for?     OPEN 0:52                        CLOSE 1:16
D — the house sells at dawn   OPEN 0:58                        CLOSE 2:07
```

Never more than three live at once. Closed in reverse order of opening. Re-hooks
land at 25%, 54% and 72% of runtime.

The seam is a **reinterpretation**: the last line — *"It is only in a different
window now"* — makes the opening sentence describe a different window than the
viewer assumed, which is what makes the first ten seconds worth replaying.

---

## Lint

```bash
python3 ../../scripts/hookcheck.py script.txt
```

Passes with one warning: the opening sentence is thirteen words against a
twelve-word guideline. Kept deliberately — "At three in the morning, one window
on Rowan Street was still burning" needs the hour, the singularity and the street
in one breath, and splitting it weakened the image. The warning is the linter
doing its job; overriding it is a judgement the writer owns.
