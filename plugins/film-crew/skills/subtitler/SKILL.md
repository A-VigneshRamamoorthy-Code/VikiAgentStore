---
name: subtitler
description: >
  Writes the caption file the platform indexes: timed from the rendered
  storyboard, broken for reading speed, and spelled the way the ledger spells
  things. Use when preparing captions, subtitles, SRT or VTT for a film, or
  when accessibility and search indexing matter. Part of film-crew, normally
  dispatched by the director skill.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "1.0.0"
---

# Subtitler

YouTube will caption the film for you. It will do it with a speech recogniser,
and it will guess worst at exactly the words the film was researched to get
right — the names, the places, the figures. *D.B. Cooper* becomes *DB cooer*.

Uploading our own file replaces a guess with the script. That is the whole job.

---

## Why this is not optional

- A large minority of viewers watch with captions on, many of them muted in
  public. For them the caption **is** the narration.
- An uploaded caption track is the only full-text signal the platform gets
  about what a film actually says. Auto-captions are not indexed the same way.
- Accessibility is a floor, not a feature.

---

## Non-negotiables

1. **Time from the renderer's published timeline, not from the audio files.**
   The renderer trims each clip's recorded silence before laying the voice
   down, so the wav on disk runs about a second longer than what plays.
   Measuring the clips instead walks the captions off the picture — on a
   12-minute film, by over two minutes.
2. **Never re-transcribe.** The words already exist in the script. Recognising
   them again only introduces errors.
3. **Reading speed ≤ 20 characters/second.** That is the figure Netflix's
   English spec uses; a stricter 17 flags about half the cues of a
   professionally captioned documentary, which is noise rather than signal.
4. **At most two lines, 42 characters each.** A third line pushes the safe area
   on a phone.
5. **Break at a clause.** A caption split mid-phrase is measurably slower to
   read than the same words split at a comma.
6. **Verify against the finished film.** A caption file built from a different
   cut is worse than none.

---

## Use

```bash
S=skills/subtitler/scripts/captions.py

python3 $S storyboard.json -o meta/captions.srt --vtt meta/captions.vtt \
        --check film.mp4
```

| flag | why |
|---|---|
| `--vtt` | WebVTT as well as SRT — some players want it |
| `--check FILM` | catch a caption file built from an older cut |
| `--script lines.json` | words for a storyboard that times by audio and carries no `text` |
| `--timeline JSON` | the renderer's `*.timeline.json`; found automatically beside the film or the storyboard |
| `--no-timeline` | ignore it and measure the clips — only right when there is no rendered cut |
| `--strict` | exit non-zero on any problem, for CI |

The checker reports reading speed, line length, cue overlap and drift against
the film's real duration. It prints problems rather than fixing them silently,
because the fix is usually to shorten the *line*, which is a writing decision.

---

## Handing off

[`publisher`](../publisher/) uploads `captions.srt` alongside the video, and
the caption file is part of what the director's approval binds — so re-writing
the words after approval lapses the gate, exactly as re-rendering the picture
does.

Details on cue design, speaker changes and what to do with on-screen text:
[`reference/caption-craft.md`](reference/caption-craft.md).
