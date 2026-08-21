---
name: voiceover
description: >
  Generates natural-sounding voiceovers and narrations using edge-tts. Creates high-quality neural audio files from text, with pacing and pauses tailored for video production.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "1.0.0"
---

# Voiceover Generation

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
