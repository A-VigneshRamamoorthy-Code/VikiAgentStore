---
name: product-launch
description: >
  Turns a product demo recording into a polished, motion-designed product launch
  video. Probes and reviews the footage, tightens dead air, assembles the best
  moments, then adds a branded intro, synced feature captions, transitions, a logo
  bug, an outro CTA, and a final logo + name end-card, plus an original synthesized
  music bed and UI sound effects. Cross-platform engine (ffmpeg + Python: Pillow +
  numpy) that runs on macOS, Windows, and Linux, with an optional macOS-native
  Swift/AVFoundation fast path. Use when someone asks to create a launch / promo /
  teaser / "show-off" / Product Hunt / social video from a screen recording or
  product demo. ALWAYS ask the user for a demo recording (and any missing product
  details) the moment this skill is triggered if they were not already provided.
license: MIT
metadata:
  author: product-launch skill
  version: "1.0.0"
---

# Product Launch Video Skill

Turn a raw product **demo recording** into a polished **launch video**:

> branded intro → tightened demo with synced feature captions → outro CTA →
> logo + name end-card, over an original music + SFX track.

It is **generic and config-driven** — every product specific (name, tagline,
captions, colors, links) comes from the user or a `config.json`. Nothing is
hard-coded to any product.

---

## ⛔ INTAKE GATE — do this FIRST, every time (mandatory)

The moment this skill is triggered, **before any other work**:

### 1. Demo recording (mandatory)
If the user has **not** already provided a demo recording (a video/screen
recording of the product in action), you **MUST** ask for it using the `ask_user`
tool. Do **not** proceed, do not fabricate footage, do not start building.

Ask for it with clear guidance, e.g.:
> "Please share a screen recording / demo video of the product in action
> (≈15–60s, showing the key features). What's the file path?"

If the user cannot provide one, stop and explain that a recording is required.

### 2. Product details (ask for anything missing)
Collect the details needed to build the video. For **any required field the user
hasn't given**, ask via `ask_user` (batch related questions into one form). Offer
sensible defaults, but **ask** rather than invent brand specifics.

Required / important:
- **Product name** and a **one-line tagline / positioning**
- **3–6 key features** to call out (these become the synced captions)
- **Brand accent color** (and optional 2–3 background gradient colors)
- **Motion personality**: playful · premium · corporate · energetic
- **Output aspect**: 16:9 (1920×1080) · 1:1 (1080×1080) · 9:16 (1080×1920)
- **Outro / CTA**: closing headline, and optionally a button label + link
- **Logo / app-icon** image (optional but recommended for the outro & end-card)
- **Music vibe** (modern-playful / calm / energetic / corporate) or silent

> Never put a real link, brand name, or claim in the video that the user did not
> provide. When unsure, ask.

See `reference/intake-and-questions.md` for the full checklist and an `ask_user`
form template.

---

## When to apply

Use this skill when the user wants to create a:
- product **launch / promo / teaser / announcement / demo** video,
- "show this off" / Product Hunt / Twitter-X / social / website hero video,
- from a **screen recording or product demo** they have (or will provide).

If they have no recording, the intake gate above still applies — ask for one.

---

## Workflow (overview)

1. **Intake gate** (above) — recording + details. *(mandatory)*
2. **Setup** — ensure `ffmpeg`/`ffprobe` + Python `pillow`,`numpy` are available
   (`reference/cross-platform-setup.md`).
3. **Probe** the recording (duration, resolution, fps, audio) —
   `python3 scripts/launch_video.py --config config.json --contact-sheet`.
4. **Review** the contact sheet to understand the footage, pick the strongest
   segments, and decide caption timings.
5. **Author `config.json`** from the user's answers + your review (start from
   `templates/config.example.json`; see `reference/config-reference.md`).
6. **Render** — `python3 scripts/launch_video.py --config config.json`.
7. **Verify** — probe the output + extract an output contact sheet; review caption
   timing, cut quality, and audio; iterate on the config.

Full detail: `reference/workflow.md`.

---

## The launch-video structure

| Phase | Contents |
|-------|----------|
| **Intro** (~2.5–3s) | Brand gradient + product name (springy entrance) + tagline |
| **Demo** (tightened) | Best moments, dead air trimmed; **synced feature captions**; transitions hide cuts |
| **Outro** (~3–6s) | Headline (e.g. "Free & open-source") + optional CTA button + link + footnote |
| **End-card** | Finish on the **logo + product name** |

Captions ride in the lower third (out of the way of the action); only one is
active at a time. See `reference/narrative-structure.md`.

---

## Motion design (built on the `motion-design` skill)

Pick **one personality** and apply it consistently:

| Personality | Easing | Durations | Overshoot |
|-------------|--------|-----------|-----------|
| Playful | ease-out-back | 150–300ms | 8–20% |
| Premium | cubic(0.4,0,0.2,1) | 350–600ms | 0% |
| Corporate | cubic(0.2,0,0,1) | 200–400ms | 0–3% |
| Energetic | ease-out-expo | 100–250ms | 15–30% |

Captions pop in (enter) and accelerate out (exit, ~40% shorter). Entrances are
30–50% longer than exits. Transitions mask hard cuts. Three motion layers
(primary caption + secondary accents + ambient). Details:
`reference/motion-design.md`.

---

## Engine

**Primary (cross-platform):** `ffmpeg` + Python (`pillow`, `numpy`).
- ffmpeg: probe, contact sheet, trim/concat, scale/pad, overlay, mux, encode.
- Pillow: renders all overlay graphics frame-by-frame (intro, captions, wipes,
  logo bug, outro, end-card) with motion-design easing; piped as RGBA into ffmpeg.
- numpy: synthesizes the original music bed + SFX → WAV.

**Optional (macOS only):** a native Swift/AVFoundation builder —
`reference/macos-fastpath.md` + `scripts/swift_fastpath/`.

Run it:
```bash
pip install -r scripts/requirements.txt          # pillow, numpy
python3 scripts/launch_video.py --config config.json --contact-sheet   # step 1: review
python3 scripts/launch_video.py --config config.json                   # step 2: render
```

---

## Files

- `SKILL.md` — this file (entry + intake gate).
- `README.md` — quick start, dependencies, sharing.
- `reference/` — workflow, intake questions, narrative structure, motion design,
  cross-platform setup, config reference, troubleshooting, macOS fast path.
- `scripts/` — `launch_video.py` (orchestrator), `motion.py`, `assets.py`,
  `audio.py`, `probe.py`, `ffmpeg_utils.py`, `swift_fastpath/`, `requirements.txt`.
- `templates/` — `config.example.json`, `config.schema.json`.
- `fonts/` — a bundled open-license font (config can override).
- `examples/` — a generic worked walkthrough (placeholder product).

---

## Golden rules

1. **Ask for the recording** if it wasn't provided — always, first.
2. **Ask for missing details** — never invent brand names, links, or claims.
3. **Stay generic** — all specifics come from the user / config.
4. **Tighten** — cut dead air; keep it punchy.
5. **Sync captions** to what's on screen; one at a time; lower third.
6. **One personality**, applied consistently.
7. **Verify** with an output contact sheet before declaring done.
