# Template board

A neutral 22.9 s storyboard that exercises **every element type and motion
device** in the spec. It is not a film — it is a reference fixture. Copy the
folder and replace the copy.

```
template/
├── storyboard.json     the board
├── vo/l1.wav … l5.wav  narration clips (supplied, not generated here)
└── template_sheet.jpg  contact sheet of the result
```

## Render it

```bash
cd ../../scripts
python3 render.py ../examples/template/storyboard.json --sheet   # ≈17 s
python3 render.py ../examples/template/storyboard.json           # 5–8 min
```

## The two-skill workflow

This skill renders the video. It does **not** synthesise speech.

1. **Write the lines**, one idea each, and save them for the voice-booth skill:

   ```json
   [ { "id": "l1", "text": "It began on an ordinary Tuesday," },
     { "id": "l2", "text": "in a town that kept very careful records." } ]
   ```

2. **Record them** with the [`voice-booth`](../../../../../voice-booth/) skill — one clip
   per line, into `vo/`:

   ```bash
   python3 ../../../../../voice-booth/scripts/narrate.py lines.json -o vo/ \
           --voice en-IE-EmilyNeural --rate=-13% --pitch=-8Hz
   ```

3. **Point the storyboard at the clips.** Paths resolve relative to
   `storyboard.json`:

   ```jsonc
   "narration": [
     { "id": "l1", "audio": "vo/l1.wav", "gap_after": 0.75 },
     { "id": "l2", "audio": "vo/l2.wav", "gap_after": 0.85 }
   ]
   ```

   Before the narration exists, use `"duration": 3.2` instead of `audio` to
   reserve the time. The renderer warns, and the audio is silent.

4. **Render `--sheet`, then the video.**

Every beat is timed against the *measured* clips, so re-recording a line moves
everything that follows it. Always re-run `--sheet` after a narration change —
the total runtime shifts and a chip can drift out of the camera move that was
framing it.

## What it demonstrates

16 elements across 5 lines:

| | |
|---|---|
| Elements | `card`, `chip`, `typed`, `stamp`, `tape`, `pin`, `ring`, `art` (`clock`, `star`), `marker_rect`, `marker_ellipse`, `marker_path` |
| Entrances | `fly` (with travelling shadow), `pin`, `fade`, and drawn-on marker strokes |
| Depth | `depth`, `elevation`, `float`, `parallax`, `shadow`, `torn`, `fold` / `fold_strength`, `wobble` |
| Camera | 7 moves — an opening push, one per line, and a settle on the tail |
| Audio | `tension` bed at 60 bpm, paper SFX per entrance, a whoosh and a closing chime, ducking `-10 dB` under speech, −14 LUFS master |

See [`../../reference/storyboard-reference.md`](../../reference/storyboard-reference.md)
for the full schema.
