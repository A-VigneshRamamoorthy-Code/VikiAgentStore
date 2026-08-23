# The toolbox

Two entry points speak; everything else exists to build, measure or audition the
voices they speak with.

## Speaking

| Script | Does |
| --- | --- |
| `voice.py` | **script + voice → one audio file.** The front door. |
| `narrate.py` | **lines.json → one clip per line + `voice.json`.** The pipeline stage; `animation-director` calls it. |
| `tts.py` | provider chain behind `narrate.py`: `cast → edge → gemini → openai → say`. |

## Building the cast

| Script | Does |
| --- | --- |
| `build_cast.py` | `characters.json` → verified cast + `out/cast/manifest.json` |
| `core.py` | tuned constants, language detection, cloning, mastering, measurement |
| `check_refs.py` | verify every `ref_text` actually matches its reference audio |
| `transcribe.py` | produce an exact `--ref-text` from a recording |
| `list_voices.py` | free Edge voices usable as references |

## Measuring

| Script | Does |
| --- | --- |
| `analyze.py` | measure output against the acceptance criteria |
| `qa.py` | screen for uneven pauses and pitch spikes |
| `timbre.py` | prove same-gender voices read as different people |
| `intelligibility.py` | synthesize → transcribe → score pronunciation |

## Auditioning

| Script | Does |
| --- | --- |
| `serve.py` | gallery in a browser; `--verify` decode-checks every clip |
| `build_samples.py` | demo clips for the language detector |
| `build_ab.py` | reproducible Tamil reference comparison |

## Tests

`test_detect.py` (17 cases), `test_nonverbal.py` (34), `test_qa.py` (22). Run all
three after touching `core.py` or `qa.py`:

```bash
for t in test_detect test_nonverbal test_qa; do .venv/bin/python scripts/$t.py; done
```

## Layout

```
SKILL.md              entry point
crew.json             pipeline registration (stage: voice, order: 50)
scripts/              the tools above
templates/
  characters.json     the 9-character cast definition
  characters.example.json   schema + worked example
  samples.json        demo lines for language detection
  gallery.html        manifest-driven review page
reference/            these docs
out/
  refs/               denoised reference clips — required at synthesis time
  cast/               the built cast + manifest.json
voice-reference/      source recordings the clones are built from
```

`out/refs/` is **not** disposable: cloned voices read it on every render, and
regenerating it needs the 2.5 GB model. It ships with the skill.
