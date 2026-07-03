# Config Reference

The schema is `templates/config.schema.json`. Match field names exactly.

---

## CLI contract

```bash
python3 scripts/launch_video.py --config config.json --contact-sheet
python3 scripts/launch_video.py --config config.json
```

Optional flags:

```bash
--input PATH        # override config.input
--output PATH       # override config.output
--ffmpeg /path      # use a specific ffmpeg binary
--fps N             # override config.fps
--dry-run           # print the ffmpeg/filter plan without rendering
```

---

## Field table

| Field | Type | Default | Meaning | Tips |
|-------|------|---------|---------|------|
| `input` | string | required | Path to the product demo recording. | Required. Can be overridden with `--input`. |
| `output` | string | `launch.mp4` | Final MP4 path. | Can be overridden with `--output`. |
| `fps` | integer | `30` | Output frames per second, 24–60. | Lower for faster renders; 30 is a good default. |
| `resolution` | `[w,h]` integers | `[1920,1080]` | Output size. | 16:9 `[1920,1080]`, 1:1 `[1080,1080]`, 9:16 `[1080,1920]`. |
| `fit` | enum | `height` | How the demo is scaled into the frame: `height`, `width`, `contain`, `cover`. | `height` preserves top-screen UI; `contain` avoids crop; `cover` fills frame. |
| `personality` | enum | `playful` | Motion style: `playful`, `premium`, `corporate`, `energetic`. | Pick one and use consistently. |
| `brand` | object | required | Brand settings. | Must include `brand.name`. |
| `brand.name` | string | required | Product name. | Used in intro/end-card. Never invent it. |
| `brand.tagline` | string | none | One-line pitch. | Can be referenced by `{brand.tagline}`. |
| `brand.primary` | string | none | Accent color. | Hex format like `#5B8DEF`. |
| `brand.bg_gradient` | string array | none | 2–3 hex colors for intro/outro gradient. | Put colors in visual order, dark-to-light or brand-to-depth. |
| `brand.logo` | string or null | none | Path to logo/app-icon PNG. | `null` generates a simple mark. |
| `intro` | object | defaults inside | Intro card settings. | Set `intro.enabled: false` to skip. |
| `intro.enabled` | boolean | `true` | Whether to render the intro. | Keep enabled for launch videos. |
| `intro.duration` | number | `2.8` | Intro length in seconds. | 2.5–3s is usually enough. |
| `intro.title` | string | none | Main intro title. | Supports `{brand.name}` and `{brand.tagline}` tokens. |
| `intro.subtitle` | string | none | Intro subtitle. | Often `{brand.tagline}`. |
| `segments` | array | empty | Source time ranges to keep. | **SOURCE seconds**. Empty array = whole input. |
| `segments[].start` | number | required per segment | Start time in original input. | Use contact sheet labels. |
| `segments[].end` | number | required per segment | End time in original input. | Must be after `start`. |
| `transitions` | enum | `wipe` | Join style: `wipe`, `dissolve`, `cut`. | `wipe` is the launch default; `dissolve` for calm/premium. |
| `captions` | array | empty | Synced feature callouts. | **OUTPUT seconds** after assembly. Use 3–6. |
| `captions[].text` | string | required per caption | Caption text. | Short, concrete, user-approved claims only. |
| `captions[].start` | number | required per caption | Caption start in final output timeline. | Include intro time if intro is enabled. |
| `captions[].end` | number | required per caption | Caption end in final output timeline. | Avoid overlaps; hold ~2s. |
| `logo_bug` | boolean | `true` | Small persistent brand mark during demo. | Disable if it covers important UI. |
| `outro` | object | defaults inside | Outro CTA and end-card settings. | Set `outro.enabled: false` to skip. |
| `outro.enabled` | boolean | `true` | Whether to render the outro. | Recommended for launch videos. |
| `outro.headline` | string | none | Closing message. | Ask user; do not invent claims. |
| `outro.cta_text` | string or null | `null` | Button label. | `null` means no button. |
| `outro.link` | string or null | `null` | URL chip. | `null` means none; never invent links. |
| `outro.footnote` | string or null | `null` | Small supporting note. | Optional. |
| `outro.duration` | number | `6.0` | Outro length in seconds. | Shorten for social; lengthen if CTA needs reading. |
| `outro.end_card` | boolean | `true` | Finish on logo + product name. | Good default for brand recall. |
| `music` | object | defaults inside | Synthesized music bed. | Set `music.enabled: false` for silent/no music. |
| `music.enabled` | boolean | `true` | Whether to add music. | Keep low under demo audio. |
| `music.vibe` | enum | `modern-playful` | `modern-playful`, `calm`, `energetic`, `corporate`. | Match `personality` when possible. |
| `music.bpm` | number | `120` | Music tempo. | Higher for energetic videos. |
| `music.gain` | number | `0.9` | Music volume multiplier, 0–1.5. | Lower if voice or product audio matters. |
| `sfx` | boolean | `true` | UI sound effects. | Disable for quiet/professional exports. |
| `font` | string or null | `null` | Regular font path. | `null` = bundled/system fallback. |
| `font_bold` | string or null | `null` | Bold font path. | Set for brand fonts or missing glyphs. |

---

## Timing notes

- `segments` are **SOURCE seconds** in the original input.
- `captions[].start` / `captions[].end` are **OUTPUT seconds** in the assembled final timeline.
- If intro is enabled, caption times include the intro duration.

---

## Minimal config

```json
{
  "input": "demo.mov",
  "brand": {
    "name": "Product Name"
  }
}
```

---

## Fuller config

```json
{
  "input": "demo.mov",
  "output": "launch.mp4",
  "fps": 30,
  "resolution": [1920, 1080],
  "fit": "height",
  "personality": "playful",
  "brand": {
    "name": "Product Name",
    "tagline": "A concise one-line product promise",
    "primary": "#5B8DEF",
    "bg_gradient": ["#14172B", "#1E2348", "#101326"],
    "logo": null
  },
  "intro": {
    "enabled": true,
    "duration": 2.8,
    "title": "{brand.name}",
    "subtitle": "{brand.tagline}"
  },
  "segments": [
    { "start": 1.2, "end": 8.0 },
    { "start": 12.5, "end": 21.0 }
  ],
  "transitions": "wipe",
  "captions": [
    { "text": "Show the first key feature", "start": 4.0, "end": 6.2 },
    { "text": "Highlight the visible result", "start": 9.0, "end": 11.3 },
    { "text": "End with the strongest payoff", "start": 14.0, "end": 16.4 }
  ],
  "logo_bug": true,
  "outro": {
    "enabled": true,
    "headline": "Your closing message",
    "cta_text": "Try it now",
    "link": "https://example.com",
    "footnote": null,
    "duration": 6.0,
    "end_card": true
  },
  "music": {
    "enabled": true,
    "vibe": "modern-playful",
    "bpm": 120,
    "gain": 0.9
  },
  "sfx": true,
  "font": null,
  "font_bold": null
}
```
