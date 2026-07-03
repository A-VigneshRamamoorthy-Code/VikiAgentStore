# Generic walkthrough: Acme Notes launch video

This is an illustrative placeholder example. “Acme Notes,” file paths, colors, captions, links, and timings are fake values you would replace with real user-provided details.

## 1. User triggers the skill

User: “Create a polished launch video from my product demo.”

Agent: “Please share a screen recording / demo video of the product in action, plus the product name, tagline, 3–6 feature highlights, brand color, desired aspect ratio, motion personality, outro CTA, optional logo, and music vibe.”

## 2. User provides illustrative inputs

- Recording: `recordings/acme-notes-demo.mov`
- Product: `Acme Notes`
- Tagline: `Capture ideas before they disappear`
- Features: instant capture, smart folders, quick share
- Accent: `#6D5EF7`
- Aspect: 16:9
- Personality: playful
- CTA: `Try the beta` / `https://example.com/acme-notes`
- Logo: none; use generated mark
- Music: modern-playful

## 3. Install dependencies and create a first contact sheet

```bash
pip install -r scripts/requirements.txt
cp templates/config.example.json config.json
python3 scripts/launch_video.py --config config.json --input recordings/acme-notes-demo.mov --contact-sheet
```

The agent reviews the contact sheet to choose source ranges and decide caption timings. Caption `start`/`end` values below are **output seconds after assembly**, not source-video seconds.

## 4. Example `config.json`

All values are illustrative placeholders.

```json
{
  "input": "recordings/acme-notes-demo.mov",
  "output": "renders/acme-notes-launch.mp4",
  "fps": 30,
  "resolution": [1920, 1080],
  "fit": "height",
  "personality": "playful",
  "brand": {
    "name": "Acme Notes",
    "tagline": "Capture ideas before they disappear",
    "primary": "#6D5EF7",
    "bg_gradient": ["#111827", "#241B5A", "#0F172A"],
    "logo": null
  },
  "intro": {
    "enabled": true,
    "duration": 2.8,
    "title": "{brand.name}",
    "subtitle": "{brand.tagline}"
  },
  "segments": [
    { "start": 1.2, "end": 8.8 },
    { "start": 12.4, "end": 23.6 },
    { "start": 28.0, "end": 36.5 }
  ],
  "transitions": "wipe",
  "captions": [
    { "text": "Jot an idea in one keystroke", "start": 3.4, "end": 5.9 },
    { "text": "Smart folders organize the chaos", "start": 8.2, "end": 11.2 },
    { "text": "Share polished notes without leaving flow", "start": 14.8, "end": 18.0 },
    { "text": "A playful workspace for fast-moving teams", "start": 21.0, "end": 24.0 }
  ],
  "logo_bug": true,
  "outro": {
    "enabled": true,
    "headline": "Your ideas, ready when you are",
    "cta_text": "Try the beta",
    "link": "https://example.com/acme-notes",
    "footnote": "Illustrative placeholder URL",
    "duration": 5.5,
    "end_card": true
  },
  "music": { "enabled": true, "vibe": "modern-playful", "bpm": 124, "gain": 0.85 },
  "sfx": true,
  "font": "fonts/Inter-Regular.ttf",
  "font_bold": "fonts/Inter-Bold.ttf"
}
```

## 5. Render and verify

```bash
python3 scripts/launch_video.py --config config.json
python3 scripts/launch_video.py --config config.json --contact-sheet
```

The agent verifies that the final MP4 exists, probes cleanly with `ffprobe`, and reviews the output contact sheet for cut quality, caption timing, readable lower thirds, outro CTA, and end-card branding. If a caption lands early or a segment feels slow, adjust `segments` or output-second caption times and render again.
