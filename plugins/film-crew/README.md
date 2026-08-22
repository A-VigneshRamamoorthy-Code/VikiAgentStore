# Film Crew

A film crew, as a plugin. Give the **director** a topic and a style; a crew of
specialists does the rest.

```bash
copilot plugin install film-crew@VikiAgentStore
```

> **Renamed.** This was `video-craft` up to v1.3.0. The skills were renamed too —
> `content-research` → `screenwriter`, `hook-engineering` →
> `story-editor`, `voiceover` → `voice-booth`, `youtube-publish` →
> `head-of-marketing`, and `paper-explainer` became a *style* rather than a
> skill. If you had `video-craft` installed, install `film-crew` instead.

---

## One command

Ask Copilot for it in words, or type the flag form — either wakes the director:

```
/director --paper --topic "the 1984 Bhopal gas disaster" --parts 2 --shorts 3
```

Two paper-style episodes of one narrative, plus three vertical Shorts cut from
the hookiest moments. Add `--publish my-handle` to package and upload.

`/director` is not a registered CLI command; it is a phrasing the
`director` skill recognises and hands straight to its own parser, so the
flags below are real and the same line works in a shell:

```bash
python3 skills/director/scripts/director.py \
  --paper --topic "the 1984 Bhopal gas disaster" --parts 2 --shorts 3
```

```bash
python3 skills/director/scripts/director.py --help
```

is the authoritative reference for every flag.

---

## The crew

| skill | role |
|---|---|
| [`director`](skills/director/) | Runs the production. Parses the brief, ranks or resolves the style, fans the work into episodes and Shorts, drives the crew stage by stage, and holds the gates — nothing is done without an artifact, nothing is published without approval bound to the exact bytes. |
| [`researcher`](skills/researcher/) | Establishes what is true before anyone writes a sentence. Two independent sources per claim, verbatim quotes stored, contradictions recorded rather than resolved. Produces `ledger.json`, which is the whole permitted vocabulary of fact. |
| [`screenwriter`](skills/screenwriter/) | Turns the ledger into narration. Every line is bound to a claim; the linter fails a script with an unsourced spoken fact, an unhedged contested figure, or a word count that misses the runtime. |
| [`story-editor`](skills/story-editor/) | Makes people keep watching: the opening three seconds, the open loops that hold the middle, the re-hooks, and an ending that earns a rewatch. Also chooses each Short's window. |
| [`storyboard-artist`](skills/storyboard-artist/) | Plans what is on screen and when, as a **style-neutral** beat plan pinned to spoken lines. Marks which hooks are worth cutting as Shorts. |
| [`production-designer`](skills/production-designer/) | Owns the look. Holds the style registry, compiles a beat plan into a style's storyboard, renders it. |
| [`voice-booth`](skills/voice-booth/) | Narrates, with `edge-tts`, and measures every clip so the board can be timed against it. |
| [`sound-designer`](skills/sound-designer/) | Everything audible that is not the voice: mood, music bed, ducking keyed to the narration envelope, and one final mix whose loudness is **measured** and reported rather than assumed. |
| [`subtitler`](skills/subtitler/) | The caption file the platform actually indexes — timed from the rendered storyboard, broken at clauses for reading speed, spelling proper nouns the way the ledger spells them instead of the way a recogniser guesses them. |
| [`head-of-marketing`](skills/head-of-marketing/) | Title, description, chapters, tags, thumbnail, outro — linted against the platform caps *and* against the fact ledger. Writes the package; never uploads it. |
| [`rights-manager`](skills/rights-manager/) | The last gate before an act that cannot be undone. Every asset's licence and attribution on record, every figure and superlative in the title checked back against the ledger. Refuses by default; exceptions must be reasoned and recorded. |
| [`publisher`](skills/publisher/) | The only skill that can reach YouTube. Every upload, edit, thumbnail and privacy change is gated on an approval bound to the sha256 of the exact bytes a human saw. |
| [`tn-assembly`](skills/tn-assembly/) | A different job: turns one long assembly or parliament webcast into publishable episodes and Shorts, cutting on natural speech boundaries. |

| [`style-paper`](skills/style-paper/) · [`style-news`](skills/style-news/) | The looks. Each style is a skill of its own, loaded only if the director picks it. |

The director loads a crew skill only when the pipeline reaches its stage, so a
whole crew's worth of instructions never sits in the context window at once.

---

## Styles

A **style** is how the film looks — and it is a **skill of its own**, named
`skills/style-<id>/`, that declares `provides_style` in its `crew.json`.
Installing one adds a look and changes no code.

```bash
R=skills/production-designer/scripts/registry.py
python3 $R list                # what is installed
python3 $R rank "<topic>"      # which style suits this subject
python3 $R doctor              # are its dependencies installed
```

| style | good for | wrong for |
|---|---|---|
| **`paper`** — parchment ground, torn-paper collage, keyword chips, hand-drawn red annotation, synthesised score | history, disaster, investigation, science, business | software demos, screen recordings, live action |
| **`news`** — full-bleed picture under a kicker/headline stack, channel bug, location chip, name straps, astonishers | journalism, investigation, business, disaster | comedy, gaming, screen recordings, product demos |

With no `--style`, the director ranks them against the topic — and **asks rather
than guessing** when it is a close call.

The contract for writing a new one:
[`style-contract.md`](skills/production-designer/reference/style-contract.md).

---

## How a production runs

```
research ─┬─ script ─ punchup ─ lint ─ voice ─ board ─┬─ compile ─ render ─┬─ package ─ publish
          │            (per episode)                  │                    │
          └─────────────────────────────────────────  │                    │
                                            cut ─ shoot ──────────────────┘
                                              (per Short)
```

State lives in `production.json`, which means:

- **It resumes.** Context compaction, a crash, or coming back a day later —
  `director.py report` and carry on.
- **It notices.** Every stage records the sha256 of what it consumed. Edit a
  script and everything downstream goes stale rather than silently shipping.
  Content-addressed, so reverting an edit un-stales it.
- **It fans out.** Two episodes where one rendered and one failed is a state the
  file can actually express.

Three rules are not negotiable, and they live in the director's always-loaded
body rather than in a reference file:

1. Skipping research marks the production `unverified`, and nothing may then
   describe it as sourced.
2. Publishing requires approval bound to the exact bytes. Re-render and the
   approval lapses.
3. A plan is not a film. Nothing is done until there is a rendered file.

---

## Requirements

```bash
python3 -m pip install -r skills/style-paper/scripts/requirements.txt
brew install ffmpeg              # ffmpeg and ffprobe
```

`edge-tts` for narration, in its own environment:

```bash
python3 -m venv ~/.cache/film-crew/tts_env
~/.cache/film-crew/tts_env/bin/pip install edge-tts
```

Check everything at once, before starting anything expensive:

```bash
python3 skills/director/scripts/director.py doctor
```

---

## Trying the paper style on its own

```bash
cd skills/style-paper
python3 scripts/render.py examples/template/storyboard.json --sheet
```

`--sheet` writes a contact sheet in seconds instead of rendering for minutes,
and it exposes the two failures a single frame hides: elements piling up because
nothing is ever retired, and neighbours overlapping.
