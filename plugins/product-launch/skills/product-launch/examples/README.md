# Examples — end-to-end test

A self-contained, cross-platform smoke test for the skill (no macOS-specific tools).

Files:
- `make_sample_demo.py` — generates a synthetic **"Acme Notes" app demo recording**
  using Pillow + ffmpeg (works on macOS/Windows/Linux). Distinct feature beats:
  adding notes (~2–10s), checking one off (~11s), search + filter (~14–18s).
- `sample_demo.mp4` — a pre-generated copy of that demo (the test **input**), ~21s, 1920×1080.
- `sample_config.json` — a generic launch-video config whose `segments` and
  `captions` are timed to the demo's beats.
- `generic-walkthrough.md` — a narrated walkthrough of using the skill.

## Run the test

From this `examples/` directory:

```bash
# 0) deps (once): ffmpeg on PATH + python packages
pip install -r ../scripts/requirements.txt
# (no ffmpeg? see ../reference/cross-platform-setup.md, or pass --ffmpeg /path/to/ffmpeg)

# 1) (optional) regenerate the demo recording from scratch
python3 make_sample_demo.py --output sample_demo.mp4

# 2) review the footage to choose moments
python3 ../scripts/launch_video.py --config sample_config.json --contact-sheet

# 3) render the launch video
python3 ../scripts/launch_video.py --config sample_config.json
#    -> sample_launch.mp4   (intro → captions → outro CTA → logo + name end-card, with audio)
```

The produced `sample_launch.mp4` is ~24–25s, 1920×1080 H.264 + AAC. Open it (or run
`--contact-sheet` on the output) to verify intro, synced captions, transitions, the
logo bug, the outro CTA, and the logo + name end-card.

> Everything here is illustrative placeholder content ("Acme Notes"). Replace the
> recording and `sample_config.json` values with a real product to make a real video.
