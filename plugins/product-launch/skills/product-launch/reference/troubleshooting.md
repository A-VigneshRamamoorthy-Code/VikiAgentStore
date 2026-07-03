# Troubleshooting

Use this as problem → cause → fix.

---

## `ffmpeg` or `ffprobe` not found

**Cause:** ffmpeg is not installed or not on `PATH`.

**Fix:** Install it for your platform, then verify:

```bash
ffmpeg -version
ffprobe -version
```

Or point at a downloaded binary:

```bash
python3 scripts/launch_video.py --config config.json --ffmpeg /path/to/ffmpeg
```

---

## Wrong ffmpeg version / unsupported encoder

**Cause:** Old distro package or minimal build.

**Fix:** Install a current full/static build (Gyan on Windows, johnvansickle on Linux, Homebrew/static on macOS). Re-run with `--dry-run` to inspect the plan.

---

## Output has black bars

**Cause:** `resolution` aspect does not match the input and `fit` preserves the whole frame.

**Fix:** Adjust `fit`:
- `cover` fills the frame but may crop,
- `height` or `width` anchors scaling,
- `contain` preserves all content with bars/padding.

For social formats, choose the right preset: `[1920,1080]`, `[1080,1080]`, or `[1080,1920]`.

---

## Output crops important UI

**Cause:** `fit: "cover"` or the chosen aspect cuts off action.

**Fix:** Try `fit: "height"` for screen recordings with top navigation, or `fit: "contain"` to preserve everything.

---

## Captions are out of sync

**Cause:** Caption times use source timestamps instead of final output timestamps.

**Fix:** Remember:
- `segments` = SOURCE seconds,
- `captions[].start/end` = OUTPUT seconds after assembly.

Re-run contact sheets, recalculate timing, and include intro duration when intro is enabled.

---

## Audio/video length mismatch or sync drift

**Cause:** Variable frame rate input, unusual audio streams, or mismatched trim/concat timing.

**Fix:** Render at a fixed `fps` (for example 30), avoid tiny segment gaps, and check the output with:

```bash
ffprobe -hide_banner -i launch.mp4
```

If needed, simplify segments and render again.

---

## Music is too loud or too quiet

**Cause:** `music.gain` does not match the demo audio.

**Fix:** Lower or raise gain:

```json
"music": { "enabled": true, "vibe": "calm", "bpm": 110, "gain": 0.55 }
```

Disable music for voice-heavy demos:

```json
"music": { "enabled": false }
```

---

## Fonts look wrong or glyphs are missing

**Cause:** Fallback font lacks the needed glyphs or does not match the brand.

**Fix:** Set explicit font paths:

```json
{
  "font": "fonts/Brand-Regular.ttf",
  "font_bold": "fonts/Brand-Bold.ttf"
}
```

Install the font or use a bundled font with the needed language support.

---

## Emoji do not render

**Cause:** The selected font does not include emoji glyphs or color emoji support differs by platform.

**Fix:** Use a font with emoji support, or avoid emoji in `captions`, `intro`, and `outro` text for consistent cross-platform output.

---

## Colors look wrong

**Cause:** Invalid hex values, missing `#`, or unexpected gradient order.

**Fix:** Use hex colors like:

```json
"primary": "#5B8DEF",
"bg_gradient": ["#14172B", "#1E2348", "#101326"]
```

Put gradient colors in the intended visual order.

---

## Video feels too long or slow

**Cause:** Too much raw footage, long pauses, or captions held too long.

**Fix:** Tighten `segments`, target ~20–35s, keep 3–6 captions, and remove setup/loading/duplicate actions.

---

## Render is large or slow

**Cause:** High resolution, high fps, long source, or many segments.

**Fix:** Lower `fps` or `resolution`:

```json
"fps": 30,
"resolution": [1280, 720]
```

Use shorter `segments` and generate a contact sheet before full renders.

---

## `pip install` fails

**Cause:** System Python restrictions, old pip, or missing build tools.

**Fix:** Use a virtual environment:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install --upgrade pip
pip install -r scripts/requirements.txt
```

On Windows:

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r scripts/requirements.txt
```
