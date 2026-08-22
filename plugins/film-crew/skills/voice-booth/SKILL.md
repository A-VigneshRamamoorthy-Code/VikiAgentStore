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

Two traps worth knowing before you start:

- **edge-tts ignores SSML and has no emphasis markup** — `*word*` is silently
  dropped.
- **It runs ~13 % slower than macOS `say`** at the same nominal rate, so any
  timing measured under another provider must be re-measured.
