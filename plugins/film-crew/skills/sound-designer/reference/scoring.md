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

**The story chooses it.** `style-paper/scripts/score.py` reads the narration and
picks a mood, tempo, scale and effect set; you override it only when you
disagree. An explicit `music` block in the beat plan **suppresses** the automatic
choice entirely — which is correct when you want control, and a silent trap when
you copied the block from another film and forgot it was there.

```bash
python3 skills/style-paper/scripts/score.py --explain narration.txt
python3 skills/style-paper/scripts/score.py beat-plan.json   # full JSON block
```

### The two knobs

Mode and tempo move **independently**, and they carry different things
(Husain, Thompson & Schellenberg, 2002):

- **Mode carries valence** — how good or bad this is. Major/lydian/mixolydian
  read positive; minor/aeolian/phrygian read negative.
- **Tempo carries arousal** — how urgent it is. Slow is not sad and fast is not
  happy; slow is *calm* and fast is *activated*.

A sad-but-urgent story is minor and fast. A happy-but-still one is major and
slow. Picking mode and tempo as a single "sad/happy" dial is what makes a score
sound like stock music.

### The vocabulary

| mood | scale | bpm | reads as |
|---|---|---|---|
| `music_box` | major | 68 | childhood, small and precious |
| `warm` | major | 66 | domestic, safe, remembered fondly |
| `wonder` | lydian | 72 | awe, scale, the sublime |
| `pastoral` | mixolydian | 78 | countryside, open air, the ordinary |
| `curious` | dorian | 78 | discovery, science, how-it-works |
| `voyage` | dorian | 72 | travel, distance, setting out |
| `drive` | minor | 88 | business, momentum, rise and fall |
| `crime` | minor | 92 | heist, pursuit, something illicit |
| `tension` | minor | 62 | unsolved, investigation, dread held back |
| `reflective` | aeolian | 58 | archival history, distance |
| `elegy` | aeolian | 54 | disaster, loss of life |
| `memorial` | minor | 47 | the named dead, remembrance |
| `dread` | phrygian | 56 | something is wrong and it is coming |

### The timbre carries the claim, not the scale

Two cues in the same key and tempo can read as *grief* or as *threat*. What
separates them is not the notes:

| | elegy | threat |
|---|---|---|
| attack | bowed, no transient | struck, hard transient |
| contour | falling | close-interval, circling |
| toll density | every 4th step — remembrance | 4-to-the-bar — horror trailer |

A bell tolling once a bar is a funeral. The same bell four times a bar is a
trailer. Nothing else changed.

### Two rules that matter more than the table

- **One mood per film.** A bed that changes character mid-way makes the film
  feel like two films. Change *intensity* with `gain`, not the mood.
- **Slower than you think — but with a floor.** Narration already carries the
  pace, so a bed must not outrun it. The rule is a *ceiling*, not a target:

  ```
  bpm = min(mood_bpm, max(mood_bpm, words_per_minute / 2.2))
  ```

  Applied as a hard clamp instead, this pins every mood to roughly 66 bpm and
  makes a heist sound like a lullaby. The narration limits how far arousal may
  push tempo; it never drags a cue below its own mood's tempo.


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

### The registry

`score.sfx_for(line)` maps a line to one of fifteen synthesised effects. They
are generated, not sampled, which has one large advantage: **randomise the
parameters per render** and the same effect never repeats identically, which is
the thing that makes a sample library sound like a sample library.

`wind` · `waves` · `fire` · `steps` · `rain` · `thunder` · `creak` · `birds`
· `engine` · `crowd` · `clock` · `heart` · `water` · `bell` · `crack`

Before this existed, three effects were ever emitted and all three were the
sound of paper being handled — correct for the medium, and identical in a story
about a shipwreck and a story about a bank.

`paper` remains the fallback. It is honest about what is on screen and it keeps
a cut from feeling silent.

### Footsteps have a surface

`steps` takes `sfx_params: {"surface": …}` and the physics differ enormously —
snow is 2% low-band and 83% high; floorboards are 98% low. Using one footstep
for every floor is the single most audible tell of a cheap mix.

`snow` · `wood` · `stone` · `gravel` · `grass` · `water`

Resolve the surface from the **whole story**, not the one line, so a blizzard
established in act one still governs a later line that only says "she climbed".

### Reserve the body

`heart` is not an anxiety effect. It is an *embodied* one: it works when the
film has put us inside someone, and it is silly when it has not.

## Ambience

A bed of continuous texture — `wind`, `waves`, `rain`, `fire`, `crowd`,
`engine`, `birds` — under the whole film, chosen from the story's setting.

```json
"ambience": { "type": "waves", "gain": 0.45 }
```

Two rules:

- **Duck it like the music**, at about 0.7× the music's depth. It is texture
  rather than melody so it needs less removal, but an unducked bed sits directly
  on top of the voice and costs intelligibility for nothing.
- **Never fire a one-shot of the sound already running underneath.** A `waves`
  effect over a `waves` bed just makes the bed briefly louder for no reason.
  One-shots *are* ducked differently from beds — they are punctuation and should
  cut through.


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
