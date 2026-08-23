# Troubleshooting

---

## All clips have the same duration / audio is gappy and fragmented

`duration_s` was set to a number. It must be `None` — a fixed value forces a
canvas the model pads to fill.

Confirm with `scripts/analyze.py`: non-zero `gaps` is the signature.

---

## The voice sounds hissy / noisy

You denoised the output instead of the reference. OmniVoice bakes reference hiss
into the voice itself; the mastering compressor then amplifies it.

Fix: denoise before cloning. `prepare_ref(..., denoise=True)` is the default —
check you didn't pass `--no-denoise`.

Measured example: source −50.3 dB → clone −40.3 dB (worse than its source) →
−51.0 dB once the reference was denoised first.

---

## The clone sounds like a different person / garbled

Usually `ref_text` doesn't match the reference audio. The model aligns the two;
a wrong transcript degrades the result badly.

- Check every character at once:
  `scripts/check_refs.py --characters templates/characters.json`.
- Regenerate the transcript with `scripts/transcribe.py`.
- If you trimmed the audio, trim `ref_text` to match — **at a word boundary**.
  `scripts/transcribe.py --words` gives you word-level timings to cut on.

**A code-mixed reference is a common hidden cause.** An English brand name or
verb inside a Tamil clip drags the alignment off. Cut the reference to its clean
single-language span with `ref_trim` and shorten `ref_text` to match — a 4 s clean
clip beat the same speaker's 7.6 s code-mixed clip by 7.7 intelligibility points.

```json
{ "ref_trim": [0.0, 3.98], "ref_text": "…only what is inside that window…" }
```

Verify with `scripts/analyze.py --compare source.wav clone.mp3` — under 5 % F0
drift means the timbre transferred.

---

## The same build gives a different result each time

**Expected — OmniVoice generation is stochastic.** Two identical builds of the
same characters produced F0 drift of 0.9–3.8 % on one run and 6.5–15.2 % on the
next, from byte-identical inputs. A single generation is a lottery, so "the clone
stopped matching the source" is often just an unlucky draw, not a regression.

`build_cast.py` therefore generates several candidates per character and keeps the
best, scored on pitch drift plus timbre distance from the reference:

```bash
.venv/bin/python scripts/build_cast.py --characters templates/characters.json --tries 3
```

`--tries 1` restores the old single-shot behaviour. Each extra try costs a full
synthesis (~45–60 s per voice), so 3 is the default compromise. If one voice is
already good, don't rebuild it — `--only` takes a comma-separated list:

```bash
.venv/bin/python scripts/build_cast.py --characters … --only harper,zane --tries 3
```

Rebuilding with `--only` preserves every other character's existing entry in the
manifest.

---

## "Processor not found" from Whisper

`mlx_audio`'s bundled Whisper is broken — the mlx-community repo it points at is
missing `preprocessor_config.json`.

Use the standalone package (installed by `setup.sh`):

```bash
uv pip install mlx-whisper
```

---

## `load_model()` fails / tokenizer not found

Use mlx-audio's loader, not a hand-rolled one:

```python
from mlx_audio.tts.utils import load_model
model = load_model(model_path="mlx-community/OmniVoice-bfloat16")
```

The module README references a `{path}/tokenizer` subdirectory that **does not
exist** — the text tokenizer is at the repo root, the audio tokenizer under
`audio_tokenizer/`. `load_model`'s `post_load_hook` handles both.

---

## Install fails: no wheels, or numpy conflicts

You are on Python 3.13 or 3.14. Much of the TTS ecosystem has no cp313/cp314
wheels and pins `numpy<=1.26.4`.

Use **Python 3.12 exactly**. `setup.sh` enforces this.

Also: in a `uv` venv there is no `.venv/bin/pip`. Use `uv pip install`.

---

## Generation is extremely slow (20+ minutes instead of ~3)

Check the machine isn't loaded by something else:

```bash
uptime          # load average
top -l 1 -n 10 -o cpu
```

A shared machine under load average 100+ starves MLX. This is not a hang — it
finishes eventually. Expected performance is RTF ≈ 0.85, roughly real-time.

**Distinguish "slow" from "paging to death".** If the process is stuck in
uninterruptible I/O wait it accrues almost no CPU and will not finish in any
useful time:

```bash
ps -o state=,time= -p <PID>   # state U + CPU time barely moving = swapping
sysctl vm.swapusage           # free ≈ 0 confirms it
```

Observed on this machine: a `--tries 5` rebuild sharing the box with a video
render (load average 17-20, 18.2 GB of 19.4 GB swap used) sat in state `U` at
~3 % CPU — 1:30 of CPU in 30 minutes. At that rate nine syntheses would have
taken hours. Stop it, wait for the machine to free up, and rerun; the code is
not at fault. `--only` merges into the existing manifest, so nothing already
built is lost.

**If you kill a build mid-run, the manifest and the audio disagree.** The
manifest is written only at the end, so a character regenerated just before the
kill is on disk with stale numbers recorded. Delete any `_<key>_<n>.mp3`
candidate leftovers, then either rebuild that character or recompute its entry
with `core.measure()` — never leave the manifest describing a file that no
longer exists.

To stop a specific offending process use `kill <PID>`. Never `pkill` / `killall`
on a shared machine.

---

## Clips 404 in the gallery, or play as silence

- 404 → `build_cast.py` hasn't run, or `--only` built just one character.
- Plays silently but returns 200 → the file is malformed. **HTTP 200 is not proof
  of a valid mp3.** Run `scripts/serve.py --verify` to decode each clip in a real
  browser.

---

## Port 8899 is in use

```bash
.venv/bin/python scripts/serve.py --port 8900
```

---

## Two voices sound the same

They are too close in pitch. `build_cast.py` warns below **25 Hz** separation for
same-language, same-gender characters.

First confirm it is real: **F0 is a poor distinctness metric on its own.** In
this cast Harper and Imogen are 13.2 Hz apart and the *most* distinct pair of all
(cosine 0.808, American vs British), while Meera and Divya are 19.3 Hz apart —
a wider gap — and the *least* distinct (0.959). The pitch gap predicted the
opposite of the truth in both cases. `scripts/timbre.py` compares MFCC profiles, so
accent and delivery count:

```bash
.venv/bin/python scripts/timbre.py --manifest out/cast/manifest.json
```

Anything above **0.97** cosine really is the same person and must be fixed.

Fix by choosing a genuinely different regional source voice — `ta-LK` vs `ta-IN`,
`en-GB` vs `en-AU` — rather than shifting one further. Shifting past ~±25 Hz
starts to sound pitch-shifted rather than like a different person, though a
moderate `pitch` offset is the right tool when two **Edge-sourced** characters
land on the same F0. Adding `ta-IN-ValluvarNeural` put Valluvar at 145.5 Hz,
0.976 against Karthik at 141.6 Hz — the same man. `"pitch": "+28Hz"` moved him to
172.0 Hz and 0.918, comfortably distinct.

Remember that a rebuild alone can move F0 several percent: re-measure with
`--tries 3` or more before concluding a pair has collided.

---

## Tamil pronunciation is wrong (ழ, ள, ண, ற, ன)

No parameter fixes this — it comes from the model, not the reference. Options:

1. Use a **Tamil** source voice rather than a cross-lingual clone.
2. Try a different Tamil Edge voice as the reference (there are 8 across 4
   locales).
3. Rewrite the word — a synonym without the problem phoneme.

See `reference/tamil-naturalness.md`.

---

## It sounds correct but robotic

Almost always the *text*, not the voice. For Tamil, check the register: literary
Tamil sounds like a textbook read aloud regardless of acoustic quality. Convert to
colloquial before synthesis.

See `reference/tamil-naturalness.md` §1.

**Do not reach for `instruct` to fix this.** It reads like a style dial but this
checkpoint is not instruction-tuned — it degraded every measured variant, and with
no reference it collapsed to a repeated syllable at 0.0 % intelligibility.

Before rewriting prosody, measure it: `core.pitch_range_st()` reports the p10–p90
F0 spread in semitones. Roughly 5–8 st is lively, below ~2.5 st is truly monotone.
Clones here already matched their sources (10.85 st vs 10.37 st), which ruled
prosody out as a cause early.

---

## `serve.py --verify` says every clip is undecodable

Suspect the **port**, not the audio. If the clips pass `analyze.py` and
`ffprobe` shows a valid mp3, the browser is almost certainly fetching someone
else's 404 page.

`SO_REUSEADDR` lets a new server bind `0.0.0.0:8899` while another process
already holds `127.0.0.1:8899`. Both binds succeed, but the **more specific**
bind wins every `localhost` request. The gallery loads from the other server,
each `fetch('cast/x.mp3')` returns its 404 HTML, and `decodeAudioData` reports
*"Unable to decode audio data"* for all of them at once.

**Every clip failing at once is the tell.** Genuine encoding faults hit one or
two clips, not the whole set.

```bash
lsof -nP -iTCP:8899 -sTCP:LISTEN     # find the squatter
kill <PID>                            # never pkill/killall
```

`serve.py` now pre-flights the port and refuses to start when something already
answers, so this should announce itself rather than look like corrupt audio.

---

## A voice sounds like one you already have

Median F0 will not tell you — two voices 1 Hz apart can be obviously different
people if the recordings differ in accent. Measure the timbre:

```bash
.venv/bin/python scripts/timbre.py --manifest out/cast/manifest.json
```

At **≥ 0.97** cosine they are effectively the same speaker; re-cast one from a
different reference recording. Pitch-shifting the same reference will not fix
it, because the formants stay put.
