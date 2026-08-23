# Building a cast

A voice character is **a reference recording plus a name** — or, for `edge`
voices, a Microsoft voice id plus a name. This is the pipeline that turns
`templates/characters.json` into a measured, shippable cast.

```bash
.venv/bin/python scripts/build_cast.py --characters templates/characters.json
```

References → denoise → clone (or speak) → master → measure → `out/cast/manifest.json`.

## 1. Define the characters

### An `edge` character

No reference audio, no transcript, ~1 s to build.

```json
{
  "key": "valluvar",
  "name": "Valluvar",
  "lang": "ta",
  "gender": "male",
  "engine": "edge",
  "source_voice": "ta-IN-ValluvarNeural",
  "persona": "native Tamil narrator — steady, measured, documentary authority"
}
```

List available voices with `scripts/list_voices.py`. **Do not add a `pitch`
offset** — see the 80 Hz measurement in `reference/voices.md`.

### A `clone` character

```json
{
  "key": "harper",
  "name": "Harper",
  "lang": "en",
  "gender": "female",
  "engine": "clone",
  "ref_audio": "/abs/path/to/female-american.wav",
  "ref_text": "Exactly what is said in that clip, word for word.",
  "persona": "polished American product narrator — clear, confident"
}
```

`ref_text` **must match the audio exactly** — the clone inherits any mismatch.
Get it with `scripts/transcribe.py`, then read it back against the clip; do not
trust the transcript unverified.

`lang` is the character's *native accent*. It picks the audition line and groups
the voice in the gallery. It does not limit what the voice can say.

`build_cast.py --validate` checks the structure before you spend ten minutes on a
build. It rejects `engine: "edge"` combined with `ref_audio`, duplicate keys,
missing fields and unknown engines.

## 2. Trim the reference

If the recording contains something you don't want cloned — a code-mixed English
brand name in a Tamil clip, a cough, a second speaker — cut it with `ref_trim`
(`[start, end]` in seconds) and shorten `ref_text` to match:

```json
{ "ref_trim": [0.0, 3.98], "ref_text": "…only what is inside that window…" }
```

**A short clean reference beats a long dirty one.** Trimming took `ref_text`
match from ~65 % to 100 %, F0 drift from 15.2 % to 0.9 %, and one noise floor from
−72.3 dB to −99.0 dB.

It does *not* measurably improve pronunciation. Trim to make the reference
honest, not to make it clearer.

Keep references **under 10 s**. That is OmniVoice's own cap and it truncates
**silently**, so a longer clip leaves the tail of `ref_text` describing audio the
model never heard. Verify the whole set at once with `scripts/check_refs.py`.

## 3. Build

Generation is stochastic: identical inputs produced 0.9–3.8 % F0 drift on one run
and 6.5–15.2 % on the next. `--tries N` generates N candidates and keeps the best
by pitch drift, timbre distance **and** pitch-spike count.

```bash
# whole cast
.venv/bin/python scripts/build_cast.py --characters templates/characters.json

# one or two, without disturbing the rest
.venv/bin/python scripts/build_cast.py --characters templates/characters.json \
    --only karthik,meera --tries 5
```

`--tries 5` reliably brought stubborn voices under the 5 % acceptance threshold,
at ~45–60 s per extra candidate. An all-`edge` build never loads the model and
finishes in about two seconds regardless.

If a voice "stopped matching the source", **rebuild before investigating**.

## 4. Verify

Three tools, all of which must pass before shipping:

```bash
.venv/bin/python scripts/analyze.py out/cast/*.mp3            # pitch, noise, gaps
.venv/bin/python scripts/qa.py --manifest out/cast/manifest.json  # pauses, spikes
.venv/bin/python scripts/timbre.py --manifest out/cast/manifest.json  # distinctness
```

See `reference/verification.md` and `reference/quality.md`.

## 5. Review by ear

```bash
.venv/bin/python scripts/serve.py --port 8901
```

A gallery with every character, its measured pitch, and an audition line.
Measurements narrow the field; they do not replace listening.

Optionally render the language-detection samples first so the gallery shows them:

```bash
.venv/bin/python scripts/build_samples.py --samples templates/samples.json
```

## Keeping voices distinct

Gender F0 ranges catch **inversion** (a male reference producing a female voice),
not house style: male 85–180 Hz, female 165–265 Hz.

Same-gender separation is **source-aware**. Two characters cloned from the *same*
recording must be ≥ 25 Hz apart, because pitch is the only thing distinguishing
them. Characters from **different** recordings differ in accent, cadence and
timbre, so a small F0 gap is fine — `build_cast.py` errors on the first case and
prints an advisory note on the second.

Genuinely different source recordings beat pitch-shifting. Always confirm with
`timbre.py`, never with F0 alone.
