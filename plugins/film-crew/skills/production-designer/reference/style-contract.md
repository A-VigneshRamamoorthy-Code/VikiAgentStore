# Adding a style

A style is a **skill**. Install it as `skills/style-<id>/`, and `registry.py`
finds it — nothing in this skill or in the director needs editing.

```
skills/style-<id>/
├── crew.json           # required — declares provides_style, which is what
│                       #   makes the registry treat this skill as a style
├── style.json          # required — the manifest
├── SKILL.md            # how to use it
├── scripts/
│   ├── compile.py      # beat plan  -> this style's storyboard
│   └── render.py       # storyboard -> video
├── reference/          # deep documentation for whoever edits a storyboard
└── examples/           # at least one storyboard that renders
```

The folder is `style-<id>` but the id users type is `<id>` — `--style paper`
lives in `skills/style-paper/`. `crew.json` must carry `"id": "style-paper"`
(the crew registry requires id == folder) while `style.json` carries
`"id": "paper"`.

`crew.json` for a style provides no pipeline stages:

```json
{
  "crew_api": 1,
  "id": "style-paper",
  "role": "Style",
  "about": "...",
  "provides": [],
  "provides_style": { "manifest": "style.json" }
}
```

Check your work at any point:

```bash
python3 scripts/registry.py doctor <id>
```

---

## `style.json`

```json
{
  "style_api": 1,
  "id": "paper",
  "name": "Paper collage",
  "version": "1.0.0",
  "aliases": ["paper-explainer", "collage", "documentary"],
  "tagline": "Archival paper board — torn cards, keyword chips, red annotation.",

  "strengths": ["history", "disaster", "investigation", "science", "business"],
  "avoid": ["software", "screencast", "live-action"],

  "entrypoints": {
    "compile": ["python3", "{style}/scripts/compile.py", "{beat_plan}", "-o", "{storyboard}"],
    "check":   ["python3", "{style}/scripts/compile.py", "{beat_plan}", "--check"],
    "render":  ["python3", "{style}/scripts/render.py", "{storyboard}"]
  },

  "requires": {
    "bin":    ["ffmpeg", "ffprobe"],
    "python": ["PIL", "numpy"]
  },

  "aspects": ["16:9", "9:16", "1:1"],
  "deliverables": ["episode", "short"]
}
```

| field | required | meaning |
|---|---|---|
| `style_api` | yes | `1`. The registry refuses a version it does not understand |
| `id` | yes | must equal the directory name; kebab-case |
| `name` | yes | shown in `registry.py list` |
| `version` | yes | part of the director's cache key — bump it and downstream work re-runs |
| `aliases` | yes | what a user might type instead. `--paper-explainer` resolves to `paper` |
| `tagline` | yes | one line, shown in listings |
| `strengths` | yes | topics this suits. **Closed vocabulary** — see below |
| `avoid` | yes | topics this is wrong for. Weighted more heavily than `strengths` |
| `entrypoints` | yes | must include `compile` and `render`; see the sandbox rules below |
| `requires` | no | `bin` (on `PATH`) and `python` (importable), checked by `doctor` before any expensive work starts |
| `aspects` | yes | which frame shapes it can produce |
| `deliverables` | yes | free-form list; recorded, not interpreted |

Every field in that table is required, and `registry.py doctor` will say so.
A list may be empty (`"avoid": []`) but it has to be present: an absent
`strengths` and an empty one mean different things to the ranker, and a style
with no `tagline` cannot be listed.

### Entrypoints are contained, not sandboxed

Be clear about what this buys: a style's own `compile.py` is ordinary Python and
can do anything Python can do. **Installing a style means trusting its author.**
What the registry guarantees is narrower — that the manifest cannot be used to
run something *other* than the style's own scripts, so a style cannot claim to
be a renderer while quietly launching a shell.

An entrypoint is an **argv array, never a shell string**, shaped
`[interpreter, script, ...arguments]`:

- `argv[0]` must be `python3` (optionally `python3.12`), `python`, `node` or
  `ffmpeg`, written plainly — not `/usr/bin/python3`, not `env`.
- **`ffmpeg` takes no script**; its arguments are checked directly. For the
  other three, `argv[1]` must be a script under `{style}/` with the extension
  that interpreter runs. Anything starting with `-` there is refused, which is
  what stops `-c`, `-m` and `--eval=…` from running code that is not in the
  folder — except a short allow-list of options that provably cannot introduce
  code (`-u`, `-E`, `-I`, `-s`, `-S`, `-B`; `--max-old-space-size=`).
- The script is resolved with `realpath`, so a symlink pointing out of the style
  folder is rejected too.
- After the script, arguments are the style's own business — a script may take
  its own `-c` — except that any path must stay under `{style}/`. That is
  enforced against `..`, a leading `/` or `~`, a scheme like `file:` or
  `concat:` (which is just a path that does not start with a slash), and
  against the value half of `--flag=value`.

A manifest that breaks any of these is reported as invalid and the style will
not resolve. `registry.py doctor` additionally checks that every `{style}` file
named by *any* entrypoint exists.

Anything else in the file is ignored, so a style may carry its own settings
without the registry having to know about them.

### Entrypoints are argv arrays, and stay inside the style

```json
"render": ["python3", "{style}/scripts/render.py"]   ✅
"render": "python3 {style}/scripts/render.py"        ❌ a shell string
"render": ["python3", "scripts/render.py"]           ❌ not under {style}
"render": ["python3", "/usr/local/bin/r.py"]         ❌ absolute
"render": ["python3", "{style}/../../r.py"]          ❌ escapes with ..
```

A style folder is user content, so a `.py` argument must begin with `{style}/`
and may not climb out of it. `{style}` expands to the style's absolute
directory; the director supplies `{beat_plan}`, `{storyboard}` and `{out}`. A
placeholder left unfilled is an error rather than a literal brace reaching the
process.

A command string is one quoting bug away from arbitrary execution, so the
registry refuses one outright.

`compile` turns a beat plan into the style's own storyboard and must support
`--check` (validate, write nothing). `render` turns that storyboard into video.
Declare the arguments in the manifest using the placeholders above; the
director fills them in.

### The ranking vocabulary

`strengths` and `avoid` are matched against the topic using a fixed list of
terms. `python3 scripts/registry.py list` prints it.

A term outside the vocabulary is **inert, not an error** — the style still
works, it just will not be ranked on that term. This is deliberate: a typo
should cost you a ranking signal, not break the registry.

---

## What `compile.py` owes you

It turns a style-neutral beat plan into this style's own storyboard. Two
obligations:

1. **Produce a draft that actually renders.** Get the mechanical things right —
   timing, layout, no collisions, a camera that keeps the composition in frame.
   Leave taste to the human. It is a storyboard artist's rough, not a finished
   board.

2. **Never invent a picture.** When a beat asks for something the style cannot
   draw, emit a **labelled placeholder** and report it, then exit non-zero. Do
   not substitute the nearest available thing.

   The paper style parses its illustration catalogue directly out of `render.py`
   rather than keeping a second copy, so the compiler can never offer a picture
   that does not exist, and adding an illustration needs only one edit.

The second rule is the important one. A documentary that shows the wrong
building is making a false claim in pictures, and it will do it silently.

---

## Testing a new style

```bash
python3 scripts/registry.py doctor <id>            # dependencies present
python3 scripts/registry.py rank "<a topic>"       # does it rank sensibly
python3 <style>/scripts/compile.py plan.json --check
python3 <style>/scripts/render.py storyboard.json --sheet
```

**Always look at the contact sheet.** A single frame hides the two failures that
matter most: elements piling up because nothing is ever retired, and neighbours
overlapping. Both are obvious across sixteen frames and invisible in one.

Then render for real and check it moves:

```bash
python3 <style>/scripts/render.py storyboard.json --motion 24
```

A mean frame difference below `verify.min_motion` means you have made a
slideshow.
