# OmniVoice via mlx-audio — what works and what doesn't

Model: `mlx-community/OmniVoice-bfloat16` (from `k2-fsa/OmniVoice`).
Apple Silicon only. ~2.5 GB download, ~2.3 GB peak RAM, RTF ≈ 0.85 (about
real-time). Fully offline after the first run.

---

## It has no built-in speakers

This is the fact everything else follows from. OmniVoice **cannot produce a voice
from nothing** — it copies the voice in a reference clip. So:

> A "voice character" = a reference clip + a name.

The pipeline in this skill is therefore a **two-stage hybrid**:

```
edge-tts  →  reference clip  (supplies the timbre — who it sounds like)
OmniVoice →  cloned output   (supplies the prosody — how human it sounds)
```

Edge alone is intelligible but flat. OmniVoice alone has no voice to speak in.
Together they produce a voice that has both identity and natural delivery.

---

## Loading

```python
from mlx_audio.tts.utils import load_model
model = load_model(model_path="mlx-community/OmniVoice-bfloat16")
```

Use **mlx-audio's own loader**. Its `post_load_hook` wires up both the text
tokenizer and the HiggsAudio codec tokenizer. Hand-rolling this fails: the module
README references a `{path}/tokenizer` subdirectory that does not exist — the text
tokenizer lives at the repo root and the audio tokenizer under `audio_tokenizer/`.

**Load once and loop.** The `mlx_audio.tts.generate` CLI reloads the model on every
invocation — about 15 s of pure overhead per clip. Twelve clips via the CLI wastes
three minutes doing nothing.

## Generating

```python
result = next(model.generate(
    text=text,
    language="ta",
    duration_s=None,            # see below — must stay None
    ref_audio=str(ref_wav),
    ref_text=reference_transcript,
    tokenizer=model.audio_tokenizer,
    text_tokenizer=model.text_tokenizer))
```

`generate()` is a **generator** — `next()` it. Both tokenizers must be passed
explicitly.

---

## `duration_s` must be `None`

Passing a number does not cap the length — it forces a **fixed canvas** the model
stretches or pads to fill.

Measured, same eight clips:

| `duration_s` | Result |
| --- | --- |
| `13.0` | all eight exactly **13.000 s**, fragmented, dead gaps throughout |
| `None` | 9.0–9.1 s, **zero** gaps |

The built-in `RuleDurationEstimator` derives length from the text correctly. This
is the most destructive single mistake available in this API, and it produces
files that look fine until you listen.

Detect it with `scripts/analyze.py` — non-zero `gaps` is the signature.

---

## Text-prompt voice design (`instruct`) does not work for Tamil

OmniVoice can take a natural-language voice description instead of a reference.
**Measured on four prompts, it failed on both axes:**

- Output truncated to 1.7–6.3 s instead of the expected ~9 s.
- Three of four prompts explicitly requesting a *male* voice returned ~355 Hz —
  female range. Gender was simply ignored.

Cloning is the only reliable path. Do not spend time on `instruct`.

Re-measured later with round-trip intelligibility, and the verdict got worse, not
better: adding an `instruct` string dropped every reference-based variant, and
with **no** reference it collapsed entirely — repeating `நான் நான் நான்…` at
400 Hz, 5.8 s for a 10.5 s script, **0.0 %** intelligibility. The parameter stays
plumbed through `core.synth()` and `voice.py --instruct` in case a future
checkpoint is instruction-tuned; it defaults to off and warns when used.

---

## Nonverbal tags (these *do* work)

Unlike `instruct`, bracketed vocalisations are a real feature of the checkpoint.
`_tokenize_with_nonverbal_tags` (`omnivoice.py:124`) splits them out and feeds
each as one atomic token, so the model performs them as sounds:

```
laughter  sigh  confirmation-en  dissatisfaction-hnn
question-en  question-ah  question-oh  question-ei  question-yi
surprise-ah  surprise-oh  surprise-wa  surprise-yo
```

**The trap:** the pattern at `omnivoice.py:14` has no `re.IGNORECASE` and
tolerates no whitespace, and unmatched bracket text falls straight through to
ordinary text tokenization. So `[pause]`, `[Sigh]` and `[ sigh ]` are all
*spoken as words*. Nothing errors and the audio measures perfectly — it just says
"pause" out loud.

`core.unknown_nonverbal()` mirrors the model's regex exactly and `voice.py` warns
before generating. `scripts/test_nonverbal.py` cross-checks both against the
installed package, so this stays true across upgrades.

---

## Reference clip requirements

| Property | Value |
| --- | --- |
| Format | mono WAV, 24 kHz |
| Length | 4–10 s of continuous speech (hard cap `REF_MAX_S = 10.0`) |
| Content | dry speech only — no music, no second speaker, no heavy reverb |
| `ref_text` | the **exact** transcript of *exactly* what is kept |

Everything in the reference is cloned, including the room. Background music,
overlapping speakers and reverb all transfer.

**`REF_MAX_S` must not exceed 10.0.** OmniVoice's own `ref_audio_max_duration_s`
defaults to **10.0 s** (`omnivoice.py:303`), and it truncates silently. This skill
originally allowed 14 s, which meant a 12 s reference passed every check while the
model read only its first 10 s — so the last sixth of `ref_text` described audio
the model never heard. That is the same misalignment that makes a clone rush and
slur, but with no warning anywhere. Two English references (10.7 s and 10.2 s)
were quietly affected until this was found.

**`ref_text` accuracy matters.** The model aligns the reference against its
transcript; an approximate one measurably degrades the clone. Get it with
`scripts/transcribe.py` and audit the whole cast with `scripts/check_refs.py`.

**Never blindly truncate.** If you cut the audio you must cut `ref_text` to match,
at a word boundary. A hard cut mid-word corrupts the clone silently — in one real
case a 9 s cut sliced through the middle of "realistic". `prepare_ref()` trims to
`REF_MAX_S`, removes trailing silence, and warns you; the `ref_trim` field in
`characters.json` is the explicit, reproducible way to do it.

**Prefer a short clean reference to a long dirty one.** Cutting a Tamil reference
to its 4.0 s single-language span took F0 drift from a 15.2 % worst draw to
0.9 %, and trimming two English references to 4.95 s took their `ref_text` match
from ~65 % to 100 % and one noise floor from -72.3 dB to -99.0 dB. It did *not*
measurably improve pronunciation — that claim came from a single-line test and
did not survive averaging. `prepare_ref()` only warns below 3 s, because 4-5 s
clean clips clone very well.

---

## Denoise the reference, never the output

OmniVoice **bakes reference hiss into the voice itself**. Once cloned, it is part
of the timbre and no output filter removes it.

Worse, the mastering compressor *amplifies* it. Measured on one real clip:

| Stage | Noise floor |
| --- | --- |
| user's source recording | −50.3 dB |
| clone of it (no reference denoise) | **−40.3 dB** ← noisier than its own source |
| clone with the reference denoised first | **−51.0 dB** |

Setting used: `afftdn=nr=20:nf=-45:tn=1`, chosen by measurement across five
candidates. Speech bands were untouched (300–3000 Hz: 34.80 → 34.82 dB and
24.21 → 24.29 dB); only 6–12 kHz was attenuated. `nr=30` bought 1.6 dB more but
cost 9.6 dB at 6–12 kHz, audibly dulling sibilants.

Edge-generated references are already clean — denoising them only risks dulling
them, so `build_cast.py` skips it for those.

---

## Cross-lingual cloning works

An English reference produced Tamil speech at 195.1 Hz median F0 against the
source's 192.8 Hz — **1.2 % drift**. The timbre transfers cleanly across
languages.

Caveat: **pronunciation comes from the model, not the speaker.** A cross-lingual
Tamil voice still needs the ழ/ள/ண/ற/ன check by ear.

---

## Widening a cast beyond your source voices

Pitch- and rate-shifting the reference *before* cloning yields a new but
internally consistent character:

- **±14–18 Hz** and **±7–10 % rate** works reliably.
- Beyond about **±20 Hz** it starts sounding pitch-shifted rather than like a
  different person.

Use genuinely different regional Edge speakers first; shift only when you have run
out. A previous 12-voice gallery built this way had only **8 distinct source
speakers** — three "different" female voices were all ta-IN-Pallavi at different
settings, and it showed.

---

## CLI flag corrections

Documentation and third-party write-ups get these wrong:

| Wrong | Correct |
| --- | --- |
| `--language` | `--lang_code` |
| `--num_steps` | `--steps` / `--ddpm_steps` |

Moot if you use the Python API, which this skill does.

---

## `mlx_audio`'s bundled Whisper is broken

`mlx_audio`'s STT path raises **"Processor not found"** — the mlx-community repo it
points at is missing `preprocessor_config.json`. Install the standalone
`mlx-whisper` package instead (`setup.sh` already does).
