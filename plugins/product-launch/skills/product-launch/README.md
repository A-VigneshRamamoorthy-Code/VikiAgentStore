# Product Launch Skill

`product-launch` turns a product demo recording into a polished, generic launch video: branded intro, tightened demo moments, synced captions, outro CTA, end-card, music, and SFX. It is self-contained and cross-platform, using `ffmpeg` plus Python (`pillow`, `numpy`) so it works on macOS, Windows, and Linux.

## Requirements

- `ffmpeg` and `ffprobe`
- Python 3.8+
- Python packages: `pillow`, `numpy`

See `reference/cross-platform-setup.md` for per-OS installation. On macOS, an optional Swift/AVFoundation fast path is documented in `reference/macos-fastpath.md`.

## Quick start

```bash
pip install -r scripts/requirements.txt
cp templates/config.example.json config.json
# Fill in config.json, or ask the agent to gather the missing details.
python3 scripts/launch_video.py --config config.json --contact-sheet
python3 scripts/launch_video.py --config config.json
```

Use the contact sheet to pick strong source segments and output-time caption moments before rendering the final MP4.

## Agent intake rule

When used through the agent, the skill asks for the demo recording first. It will also ask for any missing product details instead of inventing product names, links, claims, colors, or CTAs.

## Folder map

- `SKILL.md` — skill entry point, intake gate, and workflow rules.
- `README.md` — this quick start.
- `reference/` — setup, workflow, config, motion, narrative, and troubleshooting docs.
- `scripts/` — cross-platform render engine and requirements.
- `templates/` — example config and JSON schema.
- `fonts/` — bundled open-license font assets.
- `examples/` — generic worked walkthroughs.

## How to share

This is a single self-contained folder. Copy or zip `~/.copilot/skills/product-launch/` and share it; the recipient drops it into their own `~/.copilot/skills/` folder.
