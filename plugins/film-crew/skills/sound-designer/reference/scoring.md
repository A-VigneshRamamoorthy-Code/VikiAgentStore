# Scoring a film

The `music` and `mix` blocks in a storyboard are this role's output. The style
renders them; you decide them.

```json
"music": {
  "mood": "tension", "scale": "minor", "root": 43.65,
  "melody_root": 67, "bpm": 60, "gain": 0.85,
  "percussion": false, "seed": 11
},
"mix": {
  "voice": 1.0, "music": 0.5, "sfx": 0.5,
  "duck_db": -10.0, "lufs": -14.0
}
```

## Choosing a mood

| subject | mood | scale | bpm | percussion |
|---|---|---|---|---|
| unsolved mystery, investigation | `tension` | minor | 58–66 | no |
| disaster, loss of life | `elegy` | minor | 50–58 | no |
| discovery, science, how-it-works | `curious` | dorian | 72–84 | light |
| business, rise and fall | `drive` | minor | 84–96 | yes |
| archival history, distance | `reflective` | aeolian | 54–64 | no |

Two rules that matter more than the table:

- **One mood per film.** A bed that changes character mid-way makes the film
  feel like two films. Change *intensity* with `gain`, not the mood.
- **Slower than you think.** Narration is already carrying the pace. A bed at
  90 bpm under a 145 wpm read fights it; at 60 bpm it supports it.

## Levels

`duck_db: -10` means the bed drops 10 dB while a word is landing. Less than 6
and the voice loses intelligibility; more than 14 and the bed pumps audibly.

`gain` is the bed's level *before* ducking. 0.7–0.9 for tension, 0.5–0.7 for
elegy where the silence is doing the work.

## Sound effects

Effects earn their place by marking a *transition* or a *reveal*, not by
illustrating a noun. A page turn under a cut to a document is a beat; a plane
sound because the script said "plane" is noise.

Keep them at least 6 dB under the bed's un-ducked level, and never place one
under the first syllable of a sentence.

## Silence

Two useful places, both deliberate:

- **Before a reveal.** Drop the bed to zero for 0.6–1.2 s, then bring it back
  with the answer. The absence is what makes the return land.
- **Under the final line.** Let the last sentence sit dry, then fade the bed up
  for the tail.

Anything longer than about 1.5 s of total silence reads as a technical fault.

## Verifying

```bash
python3 skills/sound-designer/scripts/mix.py film.mp4 \
        --report meta/mix_report.json
```

Read `loudness_after`. If the bed pushed true peak above −1 dBFS, lower `gain`
rather than limiting harder — a limiter working on a full mix squashes the
voice, which is the one thing that must stay clear.
