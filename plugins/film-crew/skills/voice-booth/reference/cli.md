# The `voice.py` CLI

The skill's front door. Everything else in `scripts/` exists to build, measure
or audition the voices this command speaks with.

```bash
.venv/bin/python scripts/voice.py --script <text|@file> --voice <name> [--language auto|ta|en] [--out FILE]
```

## Flags

| Flag | Default | Meaning |
| --- | --- | --- |
| `--script` | *required* | Text to speak, **or** `@path` to read it from a UTF-8 file. |
| `--voice` | *required* | Character key or display name, case-insensitive (`divya`, `Divya`). |
| `--language` | `auto` | `auto` \| `ta` \| `en`. Forces one language for the whole script. |
| `--out` | `narration.mp3` | Output path. Parent directories are created. |
| `--instruct` | `None` | Style direction, **clone voices only**. See the warning below. |
| `--list` | — | Print every available voice and exit. |
| `--raw` | off | Skip mastering (loudness, de-ess, trim). For debugging only. |
| `--ref` | — | Clone from your own recording instead of a cast voice. Requires `--ref-text`. |
| `--ref-text` | — | Exact transcript of `--ref`, word for word. |

## Examples

```bash
# List the cast
.venv/bin/python scripts/voice.py --list

# Tamil, from inline text
.venv/bin/python scripts/voice.py \
  --script "வணக்கம் நண்பர்களே! இன்று ஒரு புதிய தொழில்நுட்பம் பற்றி பார்ப்போம்." \
  --voice valluvar --out out/tamil.mp3

# English, from a file
.venv/bin/python scripts/voice.py --script @episode.txt --voice everett --out out/ep1.mp3

# Tanglish — no flag needed, it is detected
.venv/bin/python scripts/voice.py \
  --script "இந்த வாரம் ஒரு special-ஆன topic பார்க்கலாம்." \
  --voice karthik --out out/tanglish.mp3

# Force a language (romanised Tamil, which detection can only guess at)
.venv/bin/python scripts/voice.py \
  --script "vanakkam nanbargale" --voice meera --language ta --out out/roman.mp3
```

## Cloning without adding to the cast

To audition a voice before committing it, clone straight from a recording:

```bash
.venv/bin/python scripts/voice.py --script @script.txt \
  --ref me.m4a --ref-text "exactly what is said in that recording" \
  --out out/audition.mp3
```

`--ref` and `--voice` are mutually exclusive. `--ref-text` is mandatory because
OmniVoice aligns the reference against its transcript and a wrong one degrades
the clone badly. The reference is denoised before use.

**Only clone audio you have the right to clone** — see `reference/consent.md`.
Once a voice is worth keeping, promote it to `templates/characters.json` so it
gets measured and named: `reference/building-a-cast.md`.

## `--script` vs `--script @file`

Use the `@` form for anything longer than a sentence. A real script contains
quotes, apostrophes, newlines and punctuation that a shell will mangle, and
Tamil text is far easier to keep in a UTF-8 file than to paste into a terminal.

Files are read as UTF-8 explicitly. A file saved in another encoding fails loudly
rather than producing mojibake that the model would dutifully read aloud.

## Language handling

Language is decided **per sentence**, so a script that switches between Tamil,
Tanglish and English is voiced correctly without any flags. `--language` forces
one language for the entire script and is an escape hatch, not the normal path —
its main legitimate use is Tamil written in Latin letters, where detection can
only guess.

For `engine: edge` voices the language lives in the voice id itself
(`ta-IN-ValluvarNeural`), so detection is informational only. A Tamil Edge voice
reading English words reads them with a Tamil accent — which is usually exactly
what a Tanglish script wants.

Full rules and thresholds: `reference/language-detection.md`.

## Chunking

Text is split on sentence enders (including the Tamil danda `।`) and synthesized
a chunk at a time, then concatenated. Sentences over 180 characters are split
again at commas.

This exists because OmniVoice's duration estimator degrades on long inputs and
the delivery flattens. The chunk boundaries double as natural phrase breaks.
Verified not to introduce audible seams: a 3-chunk Tamil render measured a
longest internal pause of 0.33 s, well inside normal sentence spacing.

## `--instruct` — usually leave it alone

It looks like a style dial. On this checkpoint it is not instruction-tuned: it
degraded every measured variant and collapsed to 0.0 % intelligibility when used
without a reference. It is wired through for experimentation only, and is
ignored entirely by `engine: edge` voices.

## Exit behaviour

- Unknown voice → lists every available key and exits non-zero.
- Missing `@file` → names the path and exits non-zero.
- Empty script → exits non-zero.
- Unrecognised `[bracket]` tags → **warns on stderr and continues**, because the
  audio is still valid, just wrong. See the nonverbal tag list in
  `reference/tamil-naturalness.md`.

## `narrate.py` — the batch/pipeline entry point

`voice.py` makes one file from one script. `narrate.py` makes **one clip per
line** and is what the film pipeline (and `animation-director`) calls. Its
name and `lines.json → vo/` contract are external — do not rename it.

```bash
python3 scripts/narrate.py lines.json -o vo/ --voice karthik
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `lines` | *required* | JSON file: `[{"id": "l1", "text": "…"}, …]`. |
| `-o`, `--outdir` | `vo` | Directory for `<id>.wav` clips. |
| `--voice` | — | A cast name (`karthik`) **or** a raw provider id (`en-GB-RyanNeural`). |
| `--language` | `auto` | `auto` \| `ta` \| `en`, for cast voices. |
| `--rate`, `--pitch` | — | edge-only. Never pitch-shift to hit a target F0. |
| `--provider` | `auto` | Pin one of `cast\|edge\|gemini\|openai\|say`. |
| `--list-voices` | — | Print the cast names and exit. |

It runs under the pipeline's **system** `python3`, which has no MLX. The `cast`
provider therefore shells out to this skill's `.venv` rather than importing —
that subprocess boundary is deliberate, and keeps the 2.5 GB dependency out of
the pipeline interpreter.

Each run writes a `voice.json` sidecar next to the clips recording the provider,
voice, rate, pitch, language and duration per clip. It is **merged**, not
overwritten, so re-rendering two lines does not make the sidecar lie about the
rest of the film.
