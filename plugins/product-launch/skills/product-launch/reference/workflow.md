# Workflow

Follow this pipeline every time. The goal is a polished launch video:

> branded intro → tightened demo + synced feature captions → outro CTA → logo + name end-card.

---

## 0. ⛔ Intake gate

Before setup, probing, or config work:

1. **Recording required.** If no demo recording path/video was provided, ask for it with `ask_user` and stop until it exists.
2. **Ask for missing product details.** Product name, tagline, captions/features, colors, aspect, CTA, logo, music vibe.
3. **Never invent brand specifics.** Defaults are fine for style choices, but confirm names, claims, and links.

See `reference/intake-and-questions.md`.

---

## 1. Setup / verify dependencies

From the skill directory:

```bash
python3 --version
ffmpeg -version
ffprobe -version
python3 -c "import PIL, numpy"
```

Install Python deps if needed:

```bash
pip install -r scripts/requirements.txt
```

If `ffmpeg` is downloaded manually, pass it explicitly:

```bash
python3 scripts/launch_video.py --config config.json --ffmpeg /path/to/ffmpeg --dry-run
```

---

## 2. Probe + contact sheet

Create a starter `config.json` with at least:

```json
{
  "input": "demo.mov",
  "brand": { "name": "Product Name" }
}
```

Then run:

```bash
python3 scripts/launch_video.py --config config.json --contact-sheet
```

This probes the input and emits a labeled contact sheet. Use it to identify:
- where the product first looks impressive,
- where key features appear,
- dead air, loading, typing, repeated actions,
- accidental cursor movement or confusing pauses,
- natural cut points.

---

## 3. Map beats and choose `segments`

`segments` are **SOURCE seconds** from the original recording. Keep only strong moments.

Good segment choices:
- start just before a feature becomes clear,
- end after the result is visible,
- remove waiting, login/setup, long typing, duplicate clicks,
- preserve enough context so the viewer understands the action.

Example:

```json
"segments": [
  { "start": 1.2, "end": 8.0 },
  { "start": 12.5, "end": 21.0 },
  { "start": 27.0, "end": 34.2 }
]
```

Use `transitions` (`wipe`, `dissolve`, or `cut`) to hide joins.

---

## 4. Decide caption text + OUTPUT-time windows

Captions describe what the viewer is seeing. They are timed in **OUTPUT seconds after assembly**, not source seconds.

Rules:
- 3–6 captions total.
- One caption at a time.
- Lower third, away from important UI.
- Hold most captions for ~2s.
- Align the caption entrance with the on-screen moment, not with the source timestamp.

### Worked timing example

Input source keeps:

| Segment | Source range | Kept duration | Output demo time |
|---------|--------------|---------------|------------------|
| 1 | 10.0–16.0 | 6.0s | 0.0–6.0 |
| 2 | 30.0–38.0 | 8.0s | 6.0–14.0 |

If a feature appears at **source 33.0s**, it is 3.0s into segment 2.
Segment 2 starts at output demo time 6.0s, so the feature appears at **output demo time 9.0s**.

If the intro duration is 2.8s, the final video time is:

```text
2.8 intro + 9.0 output demo time = caption start around 11.8s
```

Config:

```json
{ "text": "Feature result appears instantly", "start": 11.8, "end": 14.0 }
```

---

## 5. Author `config.json`

Start from `templates/config.example.json`. Match field names exactly from `templates/config.schema.json`.

Key choices:
- `resolution`: `[1920,1080]` 16:9, `[1080,1080]` 1:1, `[1080,1920]` 9:16.
- `fit`: use `height` for screen recordings with important top UI; use `contain` to avoid cropping; use `cover` for full-bleed social.
- `personality`: one of `playful`, `premium`, `corporate`, `energetic`.
- `brand.logo`: path to PNG, or `null` for a generated mark.

Preview the plan:

```bash
python3 scripts/launch_video.py --config config.json --dry-run
```

---

## 6. Render

```bash
python3 scripts/launch_video.py --config config.json
```

Optional overrides:

```bash
python3 scripts/launch_video.py --config config.json --input demo-v2.mov --output launch-v2.mp4 --fps 30
```

---

## 7. Verify + iterate

Probe the final MP4:

```bash
ffprobe -hide_banner -i launch.mp4
```

Generate an output contact sheet:

```bash
python3 scripts/launch_video.py --config config.json --input launch.mp4 --contact-sheet
```

Review:
- captions appear at the right moment,
- joins are hidden by transitions,
- intro/outro duration feels right,
- audio ends cleanly and does not overpower the demo,
- logo/end-card are readable,
- no black bars or unwanted crop.

If anything is off, adjust `segments`, `captions`, `fit`, `resolution`, `music.gain`, or `outro.duration`, then render again.
