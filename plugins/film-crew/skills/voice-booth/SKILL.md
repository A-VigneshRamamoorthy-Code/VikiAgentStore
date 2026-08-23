---
name: voice-booth
description: >
  Turns a script into narration audio in a named voice. Ships a measured cast of
  nine characters (English, Tamil and Tanglish), detects the language per
  sentence, and falls back to edge-tts/gemini/openai when the cast can't serve.
  Use when asked for voiceover, narration, TTS audio, a specific character
  voice, Tamil or Tanglish speech, pacing or pauses. Part of film-crew, normally
  dispatched by the director skill.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "2.0.0"
---

# Film Voice Booth

Give it a script and a voice name, get a `.wav`.

```bash
.venv/bin/python scripts/voice.py --script "Hello there." --voice imogen --out vo.wav
```

The voice supplies the *timbre*; the script supplies the *language*. Every
character can speak English, Tamil or a mix of both — pick a voice for how it
should **sound**, not for what language it needs to read.

## Non-negotiables

- **Never pitch-shift an edge voice to hit a target pitch.** `-40Hz` moved a
  measured median 80 Hz and wrecked the timbre. Re-cast instead.
- **Measure before you claim.** Every voice in the table below has a measured
  median F0 and a passing QA run. If you add one, `scripts/qa.py` gates it.
- **Clone only voices you have the right to clone.** See
  `reference/consent.md` — this is a hard gate, not paperwork.
- **The first render downloads ~2.5 GB** of model weights, then it's cached.

## The cast

| Voice | Sex | Engine | F0 | Character |
| --- | --- | --- | --- | --- |
| `imogen` | f | clone | 173.9 | British broadcast journalist — measured, documentary calm |
| `harper` | f | clone | 187.1 | American product narrator — clear, confident explainer |
| `everett` | m | clone | 108.1 | American storyteller — warm, deep, unhurried |
| `zane` | m | clone | 158.4 | high-energy promo — bright, punchy, trailer drive |
| `meera` | f | clone | 238.8 | warm Tamil storyteller — gentle, expressive |
| `pallavi` | f | edge | 246.2 | native Tamil news presenter — bright, crisp |
| `divya` | f | clone | 258.1 | bright Tamil service voice — professional, helpful |
| `karthik` | m | clone | 138.5 | everyday Chennai Tanglish — conversational, wry |
| `valluvar` | m | edge | 145.5 | native Tamil narrator — steady, documentary authority |

`scripts/voice.py --list` prints this live from the manifest.

## Quick start

```bash
bash scripts/setup.sh                        # once — builds .venv

# a single clip
.venv/bin/python scripts/voice.py \
    --script "வணக்கம், இது ஒரு சோதனை." --voice valluvar --out out.wav

# a long script from a file, language forced
.venv/bin/python scripts/voice.py \
    --script @script.txt --voice meera --language ta --out out.wav

# a whole film, one clip per line (the pipeline stage)
python3 scripts/narrate.py lines.json -o vo/ --voice karthik
```

`--script` takes literal text or `@path`. `--language auto` (the default)
detects Tamil, Tanglish and English **per sentence**, so a mixed script needs no
flags — see `reference/language-detection.md`.

## Primary and backup

`scripts/narrate.py` asks `tts.py` for a voice, and `tts.py` tries providers in
order, taking the first that succeeds:

| Order | Provider | When it serves |
| --- | --- | --- |
| 1 | `cast` | **primary** — `--voice` is one of the nine names above |
| 2 | `edge` | `--voice` is a raw edge id, or the cast is unavailable |
| 3 | `gemini` | `GEMINI_API_KEY` is set |
| 4 | `openai` | `OPENAI_API_KEY` is set |
| 5 | `say` | last resort; robotic, and it says so |

The cast provider returns *false* rather than raising — an unknown voice, a
missing `.venv` or a failed render all fall through to the backup chain instead
of failing the film. `python3 -c "import tts; print(tts.available())"` shows
what's live. Backup details: `reference/fallback-providers.md`.

## Listening to the result

```bash
.venv/bin/python scripts/serve.py --port 8901     # gallery in a browser
.venv/bin/python scripts/serve.py --verify        # check every clip decodes
```

## Reference

Load only what the task needs.

| File | Read it when |
| --- | --- |
| `reference/cli.md` | full flag list for every script |
| `reference/scripts.md` | which script does what; folder layout |
| `reference/voices.md` | choosing a voice; the full roster with measurements |
| `reference/language-detection.md` | mixed Tamil/English scripts, Tanglish |
| `reference/quality.md` | QA thresholds, pitch spikes, what "green" means |
| `reference/tamil-naturalness.md` | Tamil sounds robotic or mispronounced |
| `reference/building-a-cast.md` | adding or replacing a character voice |
| `reference/omnivoice.md` | the clone engine, chunking, model behaviour |
| `reference/verification.md` | proving a change didn't regress the cast |
| `reference/consent.md` | **before** cloning any new voice |
| `reference/pending.md` | open questions that still need a human ear |
| `reference/troubleshooting.md` | it broke |
| `reference/fallback-providers.md` | the edge/gemini/openai backup chain |

## Requirements

- Apple Silicon + Python 3.12 for the cast (MLX). The backup chain runs
  anywhere.
- `bash scripts/setup.sh` builds `.venv`; weights cache in `~/.cache/huggingface`.
- The backup chain alone needs only `edge-tts`.
