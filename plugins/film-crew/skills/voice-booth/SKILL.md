---
name: voice-booth
description: >
  Generates narration with edge-tts: natural voices, pacing, pause markup and
  provider-specific timing caveats. Produces measured audio inputs for
  renderers and storyboard timing. Use when asked for voiceover, narration,
  TTS audio, pacing or pauses. Part of film-crew, normally dispatched by the
  director skill.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "1.0.0"
---

# Film Voice Booth

This skill uses `edge-tts` to generate realistic, natural-sounding voiceovers.
It is free and needs no API key.

For installation, the preferred voices (UK male, Irish female, Singaporean
female), and the exact technique for natural pauses and pacing, **read
[`details.md`](details.md)** in this directory.

## Install it before you run anything

`tts.py` looks for the **edge-tts CLI**, not the importable module, so a plain
`pip install` into whatever interpreter you happen to be using is not enough —
and macOS blocks that anyway under PEP 668. Put it where the resolver looks:

```bash
python3 -m venv ~/.cache/film-crew/tts_env
~/.cache/film-crew/tts_env/bin/pip install edge-tts
```

Then generate one clip per line, and check the provider it reports:

```bash
python3 ../screenwriter/scripts/scriptcheck.py script.md --lines > lines.json
python3 scripts/narrate.py lines.json -o vo/ --voice en-GB-RyanNeural --rate "-8%"
```

**Read the last line of that output.** If it says `provider: say` the film has
been narrated by the macOS robot and every clip must be regenerated — the
fallback is deliberate so a run never dies, but it is silent about the fact
that the result is unusable.

Two traps worth knowing before you start:

- **edge-tts ignores SSML and has no emphasis markup** — `*word*` is silently
  dropped.
- **It runs ~13 % slower than macOS `say`** at the same nominal rate, so any
  timing measured under another provider must be re-measured.
