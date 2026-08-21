# Video Craft

Narrated explainer and story videos in the **archival paper-collage documentary
style** — the aged-evidence-board look used by Vox, Johnny Harris and similar
channels.

Everything is generated: paper texture, torn edges, illustrations, music, sound
design. No stock footage, no image-generation API, no external assets. Given the
same storyboard and seed, the render is byte-for-byte reproducible.

## Install

```bash
copilot plugin install video-craft@VikiAgentStore
```

## Skills

| Skill | What it does |
|---|---|
| [`content-research`](skills/content-research/) | Researches any topic against reliable sources, builds a fact ledger where every claim carries two independent citations, and writes a narration script that fits a target runtime — with a linter that fails the script if a spoken fact is unsourced, a contested figure is unhedged, or the word count misses the duration. |
| [`hook-engineering`](skills/hook-engineering/) | Engineers the script so people keep watching — the opening three seconds, the open loops that hold the middle, and an ending that earns a rewatch. Hook taxonomy, re-hook vocabulary, cut-rhythm and caption specs, plus the rules for writing narration a neural TTS engine can actually perform, enforced by a linter. |
| [`paper-explainer`](skills/paper-explainer/) | Renders a narrated documentary-style video from a JSON storyboard — parchment ground, torn-paper collage, condensed keyword chips, hand-drawn red annotation, synthesized score and a broadcast-standard mix. |
| [`voiceover`](skills/voiceover/) | Generates natural-sounding narration audio with `edge-tts`, with pacing and pauses tuned for video. |

The four compose in that order: `content-research` decides what is true and what
gets said, `hook-engineering` decides how it is told so the viewer stays,
`paper-explainer` decides what it looks like, and `voiceover` speaks it. Each is
usable on its own.

## Requirements

- `ffmpeg` (no `drawtext` needed — all text is rendered with Pillow)
- Python 3.9+ with `pillow` and `numpy`
- A neural TTS provider for natural narration. `edge-tts` is the default and
  needs no key or account:
  `python3 -m venv ~/.cache/video-craft/tts_env && ~/.cache/video-craft/tts_env/bin/pip install edge-tts`.
  `GEMINI_API_KEY` (free from [AI Studio](https://aistudio.google.com/apikey))
  or `OPENAI_API_KEY` also work. With none of them the render falls back to
  macOS `say` and says so.

```bash
python3 -m pip install -r skills/paper-explainer/scripts/requirements.txt
```

## Try it

```bash
cd skills/paper-explainer/scripts
python3 render.py ../examples/template/storyboard.json --sheet   # fast contact sheet
python3 render.py ../examples/template/storyboard.json           # full render
```

`examples/template/` is a neutral 22.9 s board that exercises every element type
and motion device in the spec, at 1920×1080/30, mastered to −14 LUFS. Copy it
and replace the copy.

Narration is **supplied**, not synthesised: the storyboard points each line at a
clip in `examples/template/vo/`. Produce your own with the `voiceover` skill:

```bash
python3 skills/voiceover/scripts/narrate.py lines.json -o vo/ \
        --voice en-IE-EmilyNeural --rate=-13% --pitch=-8Hz
```

Renders are never overwritten: if the output file already exists the renderer
writes `name-002.mp4`, `name-003.mp4`, … and prints which one it chose. Pass
`--force` to opt out.

## License

MIT
