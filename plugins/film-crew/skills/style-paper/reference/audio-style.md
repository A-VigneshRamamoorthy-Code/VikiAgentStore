# Audio style

Measured from the reference, then adapted. Audio is half the style and it is
the half people skip.

---
## 1. Narration is an input, not a product

**This skill does not synthesise speech.** Narration audio is produced
elsewhere — by the [`voice-booth`](../../voice-booth/) skill — and handed to the
renderer as one clip per line:

```jsonc
"narration": [
  { "id": "l1", "audio": "vo/l1.wav", "gap_after": 0.75 },
  { "id": "l2", "audio": "vo/l2.wav", "gap_after": 0.85 }
]
```

Paths are relative to the storyboard. Any format ffmpeg can read is accepted;
everything is resampled to 48 kHz internally.

What this skill *does* with that audio is the important part:

1. **Measures it.** Each clip is trimmed of leading and trailing silence and
   its real duration recorded.
2. **Lays out the timeline from those measurements**, so `"l4+0.35"` resolves
   against real speech rather than a guess.
3. **Ducks the bed under it** and masters the result.

Because timing is derived, **the pace of the read changes the edit**. A slower
or faster narration moves every beat with it automatically — you do not
re-time the board by hand. But it does mean a re-recorded narration changes the
total runtime, so re-run `--sheet` after any change to the narration audio.

### Blocking out timing before the narration exists

Use `duration` instead of `audio` to reserve silent time:

```jsonc
{ "id": "l1", "duration": 3.2, "gap_after": 0.75 }
```

The renderer prints a warning so a placeholder can never be mistaken for a
finished mix. This is for laying out a board early; it is not a deliverable.

### What the gaps are for

The reference never runs phrases together. Inter-phrase gaps of **0.4–0.9 s**
(average ≈ 0.65 s) are what make it read as documentary rather than
advertising, and in this schema they are `gap_after` — the renderer's
responsibility, not the voice's.

---
## 2. Wall-to-wall audio

`silencedetect` was run over the reference at −32 dB, and again band-limited at
−38 dB. **It found no silence anywhere.**

There is never a moment with nothing playing. Narration has gaps; the *mix* does
not, because a continuous music bed runs underneath from first frame to last.

> Digital silence reads as a playback failure and is a reliable point of
> abandonment. Never let the bed drop out — including under the lead-in and the
> tail.

---

## 3. The music bed

Synthesised, not sampled — so it is always exactly the right length and always
license-clean.

```json
"music": {
  "mood": "music_box",
  "scale": "major",
  "root": 65.41,
  "melody_root": 74,
  "bpm": 62,
  "gain": 0.95,
  "percussion": false,
  "seed": 5
}
```

| Field | Notes |
|---|---|
| `mood` | `music_box` (celesta, story) · `warm` (pad, reflective) · `tension` (drone, investigative) · `memorial` (bowed strings + toll, grave) · `crime` (driving pulse + ticks, procedural) |
| `scale` | `major` warm · `minor` sombre · `dorian` neutral-serious |
| `bpm` | **55–70**, or **44–50** for `memorial`, or **88–96** for `crime`. The bed should sit under the narration, never pull against it |
| `percussion` | `false` for story work. A pulse creates urgency the style does not want — except in `crime`, where the pulse *is* the mood |

Instruments are additively synthesised in `audio.py`: `celesta` (struck,
inharmonic, fast decay), `warm_pad` (slow-attack detuned stack), `low_drone`,
`bowed` (slow swell, slight vibrato, string-like), `toll` (deep bell, long
decay), `pulse_bass` (short punchy filtered bass), `pluck` (muted Karplus–Strong
string), `tick` (dry click above 4 kHz), `shaker`.

### Choosing the mood: match the *genre*, not just the emotion

This is the decision that goes wrong most often, so make it explicitly. Pick the
row that matches what kind of story it is:

| Story type | `mood` | Why |
|---|---|---|
| Children's story, whimsy, wonder | `music_box` | Struck celesta is the storybook sound |
| Personal essay, reflection, nostalgia | `warm` | Pad-led, no pulse, no forward push |
| Investigation, crime, conflict, "how did this happen" | **`crime`** | Driving eighth-note pulse — it asks a question and keeps asking |
| Remembrance, elegy, a named loss, a memorial | `memorial` | Bowed, falling, unhurried; mourns rather than investigates |
| Generic serious explainer | `tension` | Neutral drone; the safe default when nothing above fits |

### Supplying your own track instead

Set `music.file` and the synthesiser is bypassed entirely — `mood`, `scale`,
`bpm` and the rest are ignored:

```json
"music": {
  "file": "The_Redacted_Hour.mp3",
  "gain": 1.0,
  "crossfade": 3.0,
  "fade": 2.5,
  "highpass": 55.0
}
```

| Field | Notes |
|---|---|
| `file` | Any format ffmpeg reads. A relative path resolves against the storyboard, so keep the track beside it and the project stays portable |
| `crossfade` | Seconds of equal-power overlap when the track is tiled to reach the runtime. **2–4 s.** Below ~1.5 s a seam is audible on sustained material |
| `fade` | Seconds of fade in and out at the two ends of the video |
| `highpass` | Optional corner in Hz. Worth setting to 50–60 on a dense track so it does not fight the voice's chest register |

The track is peak-normalised before `gain` is applied, so `gain: 1.0` is a
sensible starting point whatever the source level, and `mix.music` remains the
control you actually balance against the narration.

Two things follow from a supplied bed. It is almost certainly shorter than the
video — a thirty-second loop under twelve minutes is tiled twenty-four times —
so pick something without a strong arc or the repetition becomes obvious.

And because it was not written to leave room for a voice, **it needs a far
lower `mix.music` than the synthesised beds** — which is the one number people
get wrong. The synthesised beds carve out 1–4 kHz for the narration, so they
tolerate `mix.music` around 0.4. A real track has no such gap and sits directly
on top of the voice. Measured on a twelve-minute piece, the verification check
in [verification.md](verification.md) reads:

| `mix.music` | voice over bed @1–4 kHz |
|---|---|
| 0.42 | +7 dB — fails |
| 0.22 | +10 dB — fails |
| 0.14 | +14 dB |
| 0.10 | +16 dB |
| **0.08** | **+18 dB — comfortable** |

Start at **0.08–0.12** for a supplied track. Note the check compares narration
against an *un-ducked* stretch of music, so `duck_db` does not move it at all —
only `mix.music` does. Ducking is then chosen purely for feel, and once the bed
is that quiet a deep duck just makes it vanish: **−8 to −10 is plenty.**

> Note: `warm` is currently an **alias** — it falls through to the same branch as
> `tension` and renders an identical bed. Use it for intent/readability, but do
> not expect a different sound until it gets a branch of its own.

**Reportage about an atrocity is a *crime* story, not a funeral.** This is the
trap: the subject is grave, so an elegy feels like the respectful choice — but
an explainer about an attack is asking *what happened*, and an elegy answers a
different question. Use `memorial` only when the piece is genuinely a tribute.

### Matching the mood to the subject

**The timbre carries the claim, not the scale.** Putting `tension` in a minor
key over an atrocity does not make it respectful: `tension` is celesta-led, and
a struck bell is a *storybook* sound. It reads as whimsy over horror — the worst
possible mismatch. Nothing about `scale: "minor"` fixes that, because the
problem is the attack envelope, not the pitches.

`memorial` differs from `tension` in three ways:

- **No celesta at all.** The melodic line is `bowed` — slow attack, no transient,
  so it never sounds struck.
- **A falling line.** The figure descends through the scale; a rising line reads
  as hopeful no matter how slow it is.
- **A sparse `toll`** on every fourth step only. One every few bars reads as
  remembrance; four to the bar reads as a horror trailer.

The result measures much darker — spectral centroid around 880 Hz against
`tension`'s ~1600 Hz. Suggested settings: `root: 55.0` (A1), `bpm: 46`,
`scale: "minor"`, `percussion: false`, and drop `mix.music` to ~0.50 — a grave
bed wants to be felt rather than heard.

### `crime`: fitted against the reference

`crime` is not a guess. It was measured off the reference film and tuned until
the numbers matched. What the reference actually does:

| Property | Reference | Measured how |
|---|---|---|
| Root | **D1, 36.71 Hz** | 4.7× the energy of the next candidate |
| Beat | **92.75 bpm**, eighths at 185.5 | Sub-band autocorrelation; alternate onsets differ 6.3 vs 8.0, so the beat is the *slower* value |
| Low onsets | 18.9 / s | Spectral flux, 30–90 Hz |
| High onsets | 4.7 / s | Spectral flux, 2–8 kHz |
| Speech over bed | +6.2 dB broadband, **+20.2 dB at 1–4 kHz** | RMS of speech windows vs music-only windows |

Three findings from that fit are worth keeping:

1. **The pulse must sit in the body, not the sub.** The eighth-note
   `pulse_bass` is voiced at `root*4` so its fundamental lands in 80–250 Hz.
   Voiced an octave down it scooped the mids out and the bed stopped reading as
   music — 80–250 Hz measured 0.152 against the reference's 0.355.
2. **Percussion belongs above 4 kHz.** A click in the 1–4 kHz band lands on top
   of the narration. Moving `tick` from 2.4 kHz to 5.4 kHz cut voice-band energy
   more than threefold and let `mix.music` come *up* rather than down.
3. **`pluck` is low-passed hard (two poles at 1.6 kHz)** for the same reason —
   a bright pluck competes with the voice.

Settings: `root: 36.71`, `melody_root: 62`, `bpm: 93`, `scale: "minor"`,
`percussion: true`, `mix.music` ~0.55.

**What the fit achieved.** Band profile L1 distance to the reference bed, all
four moods measured in a single pass over an identical window:

| Mood | `<80` | `80–250` | `250–1k` | `1–4k` | `>4k` | L1 |
|---|---|---|---|---|---|---|
| *reference* | 0.428 | 0.355 | 0.170 | 0.013 | 0.034 | — |
| **`crime`** | 0.478 | 0.346 | 0.094 | 0.029 | 0.053 | **0.170** |
| `memorial` | 0.770 | 0.150 | 0.077 | 0.001 | 0.001 | 0.682 |
| `tension` | 0.783 | 0.088 | 0.116 | 0.010 | 0.002 | 0.709 |
| `music_box` | 0.161 | 0.043 | 0.748 | 0.046 | 0.002 | 1.221 |

`crime` is four times closer than anything else, and the residual is almost all
in 250 Hz–1 kHz — the reference has more midrange body there than our pluck
supplies. That is the obvious next improvement if you want to push further.

In the finished mix the voice sits **+21.1 dB over the bed at 1–4 kHz** against
the reference's +20.2 — within a decibel in the band that governs
intelligibility, which is the number to tune `mix.music` against.

**A caution on band ratios.** Compare spectra only between signals of the *same
length*, using an averaged fixed-window PSD. Magnitude-sum ratios taken from a
0.55 s reference clip and a 20 s bed are not comparable — the longer FFT gives
the wide bands far more bins, which made an early bed look 2.4× too bright when
it was not. Spectral centroid is similarly unreliable here: it barely moved
across tick settings that changed the sound completely.

---

## 4. Sound design: everything is paper

Sound effects reinforce the physical conceit. Every one is a *material* sound,
not a UI sound.

| Cue | What it is | Attach to |
|---|---|---|
| `paper` | filtered noise burst, fast decay | anything sliding or landing |
| `stamp` | low thud + brief high snap | chip and stamp entrances |
| `pin` | short bright tick | pinned scraps, stars |
| `draw` | sustained band-passed friction | marker strokes |
| `whoosh` | swept noise | the opening, scene-scale moves |
| `chime` | soft bell | the resolving beat, once |

Rules:

- **Every entrance that is physical gets a sound.** Silent arrivals feel like
  compositing; sounded arrivals feel like placement.
- **Never two identical SFX in a row.** Vary `sfx_gain` (0.4–1.0) so repeats
  don't machine-gun.
- **`chime` is used once.** It marks the resolution. Twice and it means nothing.
- **SFX sit low** — `"sfx": 0.5` in the mix. They are texture, not events.

---

## 5. Mixing

```json
"mix": { "voice": 1.0, "music": 0.60, "sfx": 0.5, "duck_db": -10.0, "lufs": -14.0 }
```

### Ducking

The music is side-chained to the narration envelope and pulled down ~10 dB
whenever the voice is present, recovering smoothly in the gaps. This is what
lets the bed be genuinely audible — you can afford a present, musical bed
because it steps out of the way of every word.

Without ducking you are forced to mix the music so quietly it may as well not be
there.

### Mastering targets

| Target | Value | Why |
|---|---|---|
| Integrated loudness | **−14 LUFS** | YouTube / Spotify / Apple normalisation point |
| True peak | **≤ −1 dBTP** | headroom for lossy transcode |
| Loudness range | 2.5–4 LU | tight, consistent, "broadcast" |

The reference itself measures **−7.2 LUFS with a +0.7 dBFS true peak** — hot and
already clipping. That is the "social loud" arms race, and it is a mistake:
every major platform simply turns it back down, so all the clipping buys you is
distortion.

> **Master to −14 LUFS / −1 dBTP.** You lose nothing on a normalising platform
> and you keep the transients intact.

Soft clipping (`audio.soft_clip`) catches the last few peaks without the
brittleness of a hard limiter, and `audio.master` finishes with `loudnorm`
followed by an `alimiter` set to the true-peak ceiling. The limiter is not
redundant: `loudnorm` in `linear=true` mode applies a flat gain and will happily
overshoot the ceiling it was given.

### Verifying

```bash
ffmpeg -nostdin -i out.mp4 -af ebur128=peak=true -f null - 2>&1 | tail -12
```

Expect I ≈ −14.0, LRA ≈ 3, peak ≤ −1.0.

---

## 6. Sync: measure first, then lay out

**This is the most important technique in the whole skill.**

Narration is loaded and *measured* before any frame is composed. Each line
gets a resolved start and end, and beats are then authored as offsets from those:

```json
"in": { "t": "l4+0.35" }        // 0.35 s after line 4 starts
"out": { "t": "l3.end+0.15" }   // 0.15 s after line 3 ends
```

Because everything is relative, **rewriting the script re-times the visuals
automatically**. Change a word, re-run, and every chip still lands on its
keyword. Hard-coded seconds break the moment anyone edits a sentence — and
someone always edits a sentence.

### Where to place a chip

On the stressed syllable of the word it names, or up to ~0.3 s after. Never
before — a label that precedes its word reads as a caption error.

In practice: `"l4+0.8"` when the keyword is mid-line, `"l4+0.05"` when the line
opens on it.
