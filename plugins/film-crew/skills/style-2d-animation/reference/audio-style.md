# Audio

The picture is cut like a cartoon, so the sound has to behave like one. A
documentary bed under a comedy chase kills it dead.

This style **reuses `style-paper`'s audio engine** — synthesis primitives, the
SFX library, ducking, and the mastering chain that delivers −14 LUFS with a
true peak under −1 dBFS. It is loaded by explicit file path, never by name, for
the reason documented in `style-flat`: `import audio` from inside a file called
`audio.py` silently imports *itself*.

What this style adds is what a comedy chase needs and a documentary does not.

---

## Narration is optional

Two modes, both first-class:

**Narrated.** One clip per line from [`voice-booth`](../../voice-booth/), and
the whole timeline derives from measuring them. The board's `narration` list is
the film's clock.

**Wordless.** Leave `narration` out of the board entirely. Music and SFX carry
everything, every shot's `at` is absolute seconds, and every shot must state
its own `dur` or an absolute `until`. This is how *Summit* works, and no board
style in this crew can do it, because they all assume a voice to hang beats on.

The music bus also comes up on its own — see [the mix](#the-mix).

## The `radio` filter

```jsonc
{ "id": "l1", "audio": "vo/l1.wav", "gap_after": 0.5, "filter": "radio" }
```

Band-limits the voice to **300 Hz – 3.4 kHz**, lifts a presence peak at
1.8 kHz for intelligibility, saturates, band-limits **again**, compresses, adds
a little hiss, and puts a squelch burst at the head and tail of the line.

The second bandpass is not a mistake. Saturation is a non-linearity, so it
manufactures harmonics: a 2 kHz formant comes back with energy at 4, 6 and
8 kHz — exactly the band the first filter just removed. Filter only before the
drive and the result measures *wider* than the radio channel it is supposed to
have been squeezed through, and stops sounding like a radio.

This is a **diegetic** decision, not a sweetener. Use it when the narrator
exists inside the film — a reporter in a helicopter, a tannoy, a phone. Never
use it on a neutral voice-over: a documentary narrator is not in the world, and
band-limiting her just sounds like a fault on the recording.

`audio.FILTERS` accepts twelve spellings of four things, so a board can name
the *object* rather than the process:

| filter | aliases |
|---|---|
| `none` | `dry`, `clean` |
| `radio` | `walkie`, `comms` |
| `tannoy` | `pa`, `megaphone` |
| `phone` | `telephone`, `call` |

An unknown name warns and is left unfiltered rather than guessed at.

## Music

The bed should be **driving and light** — walking bass, off-beat stabs, brushed
percussion — and it must be able to build and release across the film.

Four moods exist for this style specifically, and they are the ones to reach
for: `chase`, `caper`, `romp`, `scramble`. They break the engine's 92 bpm
ceiling on purpose. `audio.MOOD_ALIASES` maps the words a story is likelier to
use — `pursuit` and `action` → `chase`, `comedy`/`comic`/`funny` → `romp`,
`heist`/`sneaky` → `caper`, `panic`/`frantic` → `scramble` — so a beat plan
that says "pursuit" gets the right cue without knowing the vocabulary. A mood
the engine does not have falls back rather than failing.

Do not reach for the `crime`, `dread` or `tension` moods the documentary style
uses for an investigation. They are technically "chase music" and they will make
a comedy look like it thinks it is serious, which is the one thing a comedy may
never look like.

For completeness, `audio.MOODS` has **17** entries — the four chase moods, the
three above, and `curious` `drive` `elegy` `memorial` `music_box` `pastoral`
`reflective` `voyage` `warm` `wonder`, all inherited from the board styles.
`drive` is the only one of those ten worth a second look here: it suits a film
that is *going somewhere* without anyone being chased. The other nine are
documentary and memorial registers, and reaching for one in a comedy is the
same mistake as reaching for `dread`, in a quieter key.

The score is spotted into cues per act rather than looped wall to wall, exactly
as in `style-paper`, and the arc runs `0.45 → 0.72 → 1.00 → 0.55`: set up,
build, peak, get out. A single loop under ninety seconds of comedy flattens
every beat to the same weight.

## Sound effects

`audio.SFX` ships **34** cues:

```
bell birds boing chime clang clock crack crash creak crowd draw engine fire
heart horn paper pin pop radio_squelch rain rotor siren skid slide_whistle
stamp steps thud thunder tyres water waves whoosh wind zip
```

They split into two families, and the split is not the one you would guess.

**Cartoon accents** — the **16** names in `audio.ACCENTS`:

```
bell boing chime clang crack crash horn pop radio_squelch skid slide_whistle
stamp thud tyres whoosh zip
```

These are *jokes*. They are limited to a ceiling of `0.55` and then used as the
trigger of a second ducker that pushes the music down `accent_duck_db` (5 dB),
the beds 3 dB and the ambience 3.5 dB — so an accent **punches through** the
mix rather than ducking under it. An accent buried in the mix is a gag that did
not happen.

Note what is in that list: `skid`, `tyres`, `crash`, `horn` and
`radio_squelch` are **accents**, not world sound. In this style a skid is a
punchline with tyres in it. Treating it as ambience is the single most common
way to flatten a chase.

**Beds** — everything else, and in practice `siren`, `rotor`, `engine`,
`wind`, `rain`, `crowd`, `steps`, `clock`. These sit in the bed, ride the
normal narration ducker, and take a `dur` because they last.

That asymmetry is the one thing about this mix that differs structurally from a
documentary's, and it is easy to lose: a naive ducking rule applied to
everything will quietly delete every punchline in the film.

The accent ducker is a **separate** ducker, not the speech one. The speech
ducker is tuned for a sentence — 8 ms attack, 260 ms release — and by the time
it had opened again the 400 ms accent would be long over, leaving an audible
hole where the music used to be. `_duck_by` runs at 3 ms attack and 180 ms
release for exactly that reason.

### Accents land on the frame, not near it

A comic accent is only funny if it is exactly on the contact frame. Late reads
as a mistake; early reads as a different joke.

`shots[].sfx[].at` therefore has two forms, and the difference matters:

```jsonc
{ "kind": "boing", "at": 0.4 }        // shot-local seconds
{ "kind": "boing", "at": "l4+0.2" }   // the film clock, symbolically
```

A **number** is shot-local, so a re-timed shot carries its sound with it — that
is what you want for a contact inside the shot. A **string** is the film clock
in the board's own time grammar, for a cue that belongs to a *line* rather than
to a shot. Never write an absolute number against a wall-clock guess: narration
clips are trimmed of their recorded silence, so the film's clock is not the sum
of the source files, and any guess is stale before it is saved.

A bare string in the list — `"sfx": ["radio_squelch"]` — is shorthand for
`{"kind": "radio_squelch", "at": 0.0}`: the cue on the cut.

### Aliases, so a board can say what it means

`audio.ALIASES` maps 38 everyday words onto the 34 real cues, applied after
lower-casing and turning `-` into `_`. A board may write either.

| write | get |
|---|---|
| `helicopter` `chopper` `blades` | `rotor` |
| `police` `police_siren` `wail` | `siren` |
| `screech` `tires` `squeal` | `tyres` |
| `impact` `smash` `collision` | `crash` |
| `beep` `honk` | `horn` |
| `spring` `bounce` | `boing` |
| `bonk` `bump` `land` | `thud` |
| `swoosh` `swish` `dash` | `whoosh` |
| `squelch` `static` | `radio_squelch` |
| `whistle` `slide` | `slide_whistle` |
| `bang` `metal` | `clang` |
| `footsteps` `run` `running` | `steps` |
| `car` `motor` `traffic` | `engine` |
| `people` `chatter` | `crowd` |
| `snap` `break` | `crack` |

Aliases resolve *before* the accent test, so `"bounce"` is an accent because
`boing` is one. The same table backs `ambience`: a bed named `chopper` or
`traffic` resolves through it too.

## Ambience

One bed under the whole film. `audio.AMBIENCE` answers to **16** names, many of
them synonyms so a board can say what the story says:

```
city street urban traffic   → the street bed
chopper helicopter rotor    → the air
sirens pursuit              → the chase
wind waves rain water crowd engine fire
```

Either a bare name or `{ "name": "city", "gain": 0.8 }`. It sits at `0.45` and
ducks under narration at 45% of the voice ducker's depth — well under
everything, continuous. A name that is not a bed but *is* an effect —
`birds`, `clock` — is looped as one instead; `none`, `silence` and `silent`
run dry; anything else warns and runs dry too.

Six seconds of the bed is generated and looped, which is long enough that the
loop is not obvious and short enough that a ninety-second film does not spend a
second of CPU on room tone.

It is the cheapest way to stop a flat-colour world sounding like a slideshow,
and the first thing to check when a film feels oddly dead despite a good mix.
There is no `sky` or `office` bed; an interior is silence plus what is in it,
which is usually right.

## The mix

`board.mix` overrides the bus levels. The defaults:

| bus | level | behaviour |
|---|---|---|
| `voice` | `1.0` | the reference; everything else is placed around it |
| `music` | `0.62`, or **`0.86` in a wordless film** | ducks under narration by `duck_db` |
| `ambience` | `0.45` | ducks under narration at 45% of that |
| `sfx` | `0.55` | beds duck; accents do not |
| `duck_db` | `11.0` | how far the voice pushes music down |
| `accent_duck_db` | `5.0` | how far an accent pushes the music down |
| `accent_ceiling` | `0.55` | the limiter the accents pass through first |

The wordless default is the interesting one: with no voice to sit politely
behind, the score comes up almost half a bus, because nothing is competing with
it and a 0.62 bed under a silent film just sounds quiet.

Delivery is unchanged from `style-paper`: **−14 LUFS, true peak ≤ −1 dBFS, 0
clipped samples**, measured after mastering and re-run with a wider guard band
if the encode broke the ceiling.

Verify with the renderer's own metering. If loudness is off, **the mix is wrong
— do not fix it by re-encoding.**

## Rebuilding just the audio

```bash
python3 scripts/render.py sb.json --audio-only
```

Remuxes a new mix into an existing render with `-c:v copy`, so a music-level or
ducking change costs seconds instead of a full re-render. Only the audio may
have changed — regenerate the board first and confirm the duration still
matches, or picture and sound will drift.

## Auditioning the engine on its own

```bash
python3 scripts/audio.py --out ~/.cache/film-crew/2d-selftest
python3 scripts/audio.py --digest
```

The first writes every accent, every bed, one cue of each chase mood and a
metered mix, and asserts the comedy ducking actually works — that an accent
pushes the music down where it lands and, more importantly, **nowhere else**.
The second prints one line, a SHA-256 over the rendered mix, which is how you
tell whether an audio change was intended.

With no `--out` it writes to `$FILM_CREW_SCRATCH`, or
`~/.cache/film-crew/2d-selftest`.
