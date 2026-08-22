---
name: sound-designer
description: >
  Designs what a film sounds like after the voice is recorded: music bed and
  mood, ducking under narration, sound effects, and one measured final mix at
  the platform's loudness target. Use when a cut feels flat or silent, when
  scoring a film, or when loudness and levels need checking. Part of film-crew,
  normally dispatched by the director skill.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "1.0.0"
---

# Sound designer

An unscored cut does not sound neutral. It sounds like a mistake — the silence
between sentences reads as dead air rather than as a beat, and viewers leave
without being able to say why.

This role owns everything audible that is not the voice itself.
[`voice-booth`](../voice-booth/) records the narration; this decides what sits
underneath it and proves the result is at the right level.

---

## Non-negotiables

1. **Duck by envelope, not by a fixed level.** A bed at one constant gain is
   both too loud in a pause and inaudible under speech. Key it off the
   narration.
2. **A bed is felt, not heard.** Around 12 LU under the voice. If a listener
   can hum it back, it is fighting the script.
3. **Measure the finished file.** Adding a bed changes integrated loudness, so
   any level measured before the mix is no longer true after it.
4. **Report the number you got, not the one you targeted.** Peak-constrained
   narration cannot always be lifted to target; say so rather than claim it.
5. **Silence is a tool with a cost.** Use it before a reveal, never by accident.
6. **The mix is a new artifact.** Never overwrite the render — it has to stay
   re-checkable.

---

## Workflow

| | Step | Detail in |
|---|---|---|
| 1 | Choose the mood, and write it into the storyboard's `music` block | [`reference/scoring.md`](reference/scoring.md) |
| 2 | Set `mix` levels — voice, music, sfx, duck depth, target LUFS | [`reference/scoring.md`](reference/scoring.md) |
| 3 | Render (the style does this; the score is part of the storyboard) | — |
| 4 | Mix, or verify a style that scored itself | below |
| 5 | Read the report; fix the voice masters if target is unreachable | [`reference/loudness.md`](reference/loudness.md) |

```bash
S=skills/sound-designer/scripts/mix.py

python3 $S film.mp4 --report meta/mix_report.json          # measure only
python3 $S film.mp4 -o film.mixed.mp4 --bed bed.wav \
        --report meta/mix_report.json                       # score and measure
```

Some styles score themselves — [`style-paper`](../style-paper/) synthesises a
bed from the storyboard's `music` block. For those, this stage is the
**measurement and the sign-off**, not a second bed. Adding one on top is how a
film ends up with two pieces of music fighting.

---

## Loudness

YouTube normalises to about **−14 LUFS**. Delivering louder gains nothing —
the platform turns it down — and delivering much quieter is simply quiet.

The target belongs in the style's `style.json`, so the encoder and the check
read the same number. What matters here is that the reported figure is
*measured*: [`reference/loudness.md`](reference/loudness.md) explains why a
high crest factor can make the target unreachable, and what to do instead of
pretending otherwise.
