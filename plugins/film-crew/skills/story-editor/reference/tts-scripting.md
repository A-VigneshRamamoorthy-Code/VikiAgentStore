# Writing for the ear and for edge-tts

Two constraints at once. The listener cannot re-read, and the engine cannot be
told what to stress.

---

## Pace

**Gross wpm** — total words ÷ total running time, pauses included — is what the
audience experiences. A read that "feels slow" is usually not stretching
syllables; it is leaving air between phrases.

| Register | Gross wpm | Feels like |
|---|---|---|
| Memorial, grief | 90–100 | Silence carries meaning |
| Intimate / documentary story | 100–115 | Weight, "this matters" |
| Explainer | 120–140 | Authoritative, clear |
| Conversational | 150–160 | Peer-to-peer |
| High-energy short-form | 160–190 | Urgent, keep up |
| 200+ | — | Comprehension collapses on first hearing |

`--rate="-15%"` on a neural voice yields roughly **128–136 articulatory** wpm;
with punctuation pauses that lands near **120–128 gross**. For the intimate band
you generally need **`-25%`**. *Measure, do not assume* — run the file and divide.

**Do not pair a slow rate with long sentences.** Slow rate plus short sentences
reads as weight; slow rate plus clause-heavy sentences reads as sedated.

**Pace is a contour:** open slightly under your average → cruise → accelerate
into a list or climax → **brake into the reveal** → land on a falling close.
Urgency is a *delta*, not a setting.

---

## Writing for the ear

| Rule | Before | After |
|---|---|---|
| One idea per sentence | "The city, which had been built on trade, and which after the canal opened became a warehouse, began to empty." | "The city was built on trade. Then the canal opened. Then it began to empty." |
| Active voice | "A decision was made to utilise the facility." | "They opened the warehouse." |
| No parentheticals | "Maya (then nineteen, already lead engineer) refused." | "Maya was nineteen. She was already the lead engineer. She refused." |
| Numbers the ear can hold | "Revenue grew from $1,847,332 to $3,201,004." | "Revenue nearly doubled. From just under two million, to just over three." |
| Positive over negated | "He didn't think she couldn't have known." | "He thought she knew." |

Also: contractions (a neural voice sounds more human on *don't* than *do not* —
save the full form as a hammer); titles before names; no pronoun with two
possible antecedents; avoid near-rhymes in one clause and stacked sibilants.

**Devices that land aurally:** tricolon ("She ran. She hid. She waited."),
anaphora, antithesis ("Not the map. The ground."), light alliteration, and the
periodic sentence used sparingly — which with TTS only works if you pause before
the landing.

Read every line aloud. If you stumble, the engine will glide through it and the
*viewer* will stumble instead.

---

## edge-tts does not support SSML

This is enforced, not a documentation gap. `edge-tts` **XML-escapes your text**
into a fixed envelope permitting exactly one `<voice>` containing one
`<prosody>`:

```xml
<speak version='1.0' xml:lang='en-US'>
  <voice name='{voice}'>
    <prosody pitch='{pitch}' rate='{rate}' volume='{volume}'>
      {escaped_text}
    </prosody>
  </voice>
</speak>
```

A `<break time="500ms"/>` in your script is therefore **spoken aloud as words**.
Same for `<emphasis>`, `<say-as>`, `<phoneme>`, `<sub>`, `<mstts:express-as>`.

| Feature | Azure Speech | edge-tts |
|---|---|---|
| `<break>` | Yes (0–20000ms) | **No** |
| `<emphasis>` | Partial | **No** |
| `<say-as>` | Yes | **No** |
| `<phoneme>` | Yes | **No** |
| Per-phrase prosody | Yes | **No** — one global rate/pitch |
| Global rate/pitch/volume | Yes | **Yes** |
| Punctuation-driven timing | Yes | **Yes — this is your instrument** |

---

## Punctuation as timing

The pause values below are **approximate, measured against `en-GB-RyanNeural`
via edge-tts**. They shift with voice, rate, service version and surrounding
syntax, so treat them as ranges for planning and confirm anything load-bearing
against the rendered duration.

| You type | Pause | Intonation | Use for |
|---|---|---|---|
| `,` | 0.20–0.40s | slight hold | Lists, breath |
| `;` | 0.35–0.55s | level | Two related clauses |
| `:` | 0.35–0.60s | anticipatory | Setup → payload |
| `.` | 0.50–0.90s | **fall** | Claims, landings |
| `?` | 0.50–0.90s | **rise** | Real questions only |
| `!` | 0.50–0.90s | fall, louder | Sparingly — can shout |
| `...` | 0.60–1.20s | level | **The primary dramatic beat** |
| `—` | 0.35–0.70s | lift then fall | Cut-in thought |
| blank line | 0.60–1.20s | reset | Scene change |
| `...` + newline | 1.0–1.8s | — | Reveal, chapter break |
| `()` | unreliable | messy | **Never** — rewrite |

Never put a question mark on a claim you want believed. Never put a period on a
line you want to hang.

**Emphasis without `<emphasis>`:** put the payload word **last**, in its own short
sentence, with air around it. End-focus is the only stress you control.

**Exact pauses** are only achievable by splitting the line, synthesising each
span, and concatenating with digital silence in ffmpeg.

---

## Spell what you want spoken

Without `<say-as>` the normaliser guesses.

| Don't write | Do write |
|---|---|
| 2024 | `twenty twenty-four` |
| 1990s | `the nineteen nineties` |
| $1.4m | `one point four million dollars` |
| 10:30 | `ten thirty` |
| 10/11/12 | `the tenth of November, twenty twelve` |
| No. 5 | `number five` |
| St. | `Saint` or `Street` |
| km | `kilometres` |
| FAQ | `F A Q` |

**Homographs — never leave these bare:** read, lead, live, bow, tear, wind, bass,
content. Give each a disambiguating neighbour or rewrite the line. For unusual
names, respell: `Saoirse` → `Seersha`, `Worcestershire` → `Woostersher`.

### Clock times: use the digital idiom

Spelling a time out is not enough — *which* English you choose matters. Say
**"nine twenty"**, **"ten thirty"**, **"twelve forty-five"**. Never "half past
ten", "quarter to nine" or "twenty past nine".

The analogue idiom reads as storybook narration and breaks a documentary
register instantly; it also forces the listener to do arithmetic while you are
still talking, which is fatal in a piece whose whole spine is a timeline. In a
factual reconstruction the digital form additionally sounds like *evidence* —
it is how a log, a call record or a witness statement puts it.

Audit the whole script for this before synthesis, not line by line as you
write. It is the kind of phrase that reappears once you have stopped watching
for it.

---

## CLI facts

```bash
edge-tts --voice en-GB-RyanNeural --rate="-25%" --pitch="-5Hz" \
  --file script.txt --write-media out.mp3 --write-subtitles out.srt
```

- **Negative values need `=`.** `--rate="-15%"`, never `--rate -15%` — otherwise
  it is parsed as a flag and fails.
- **Always pass `--write-subtitles`.** A free SRT, and captions are an
  accessibility requirement regardless of what they do for retention.

  *The 69% figure, stated correctly:* a 2019 US survey found that 69% of
  **respondents said** they watch video with sound off in public. That is
  self-report about one context — not a measurement that 69% of all plays are
  muted, and its completion findings were self-reported too. Caption for access
  and sound-off resilience; verify any completion effect on your own audience
  before claiming it.
- Input chunks on a **4096-byte** boundary; keep paragraphs short.
- Built-in subtitles are **sentence-level**. For short-form burn-in you want 3–5
  words per cue — build them from `WordBoundary` events
  (`edge_tts.Communicate(..., boundary="WordBoundary")`), which the
  `SubMaker` API does not merge for you.

**Voices by register:** `en-GB-RyanNeural` (weight, documentary) ·
`en-IE-EmilyNeural` (warmth, story) · `en-SG-LunaNeural` (clarity on phone
speakers).

---

## Mix

**Choose music by function, not by tempo.** The previous "55–70 BPM, no
percussion for documentary" is retired as a universal: no reviewed study
establishes an optimal BPM or any retention effect for one. It survives only as
a `[HOUSE HEURISTIC]` starting point for a sombre documentary bed.

Select for what the scene needs — anticipation, propulsion, unease, warmth,
release — then test two things on the render: **narration intelligibility** and
whether the arousal matches the beat.

What *is* measured `[EXPERIMENT]`: music increases arousal and improves the
accuracy of duration estimates, and slow-motion footage is under-estimated in
duration and produces lower perceived and physiological arousal (Wöllner et al.,
2018). Useful for knowing that music and speed genuinely move arousal and the
sense of time — not a licence to claim a watch-time benefit.

Duck **−10 dB** under narration (WCAG G56 wants 20 dB if accessibility is the
priority). Drop the bed entirely for **exactly one** emotional line per piece;
twice is a habit.

Master **−14 LUFS integrated, true peak ≤ −1 dBTP**. Verify:

```bash
ffmpeg -nostdin -i out.mp4 -af ebur128=peak=true -f null - 2>&1 | tail -12
```

**Hitting the LUFS target is not the same as sounding good.** Platforms
normalise to a flat integrated loudness, so the only thing that distinguishes an
energetic mix from a fatiguing one is dynamic range. Compressing hard to reach
−14 flattens exactly the transients that carry arousal. Keep the loudness range
alive rather than brick-walling the narration.

Never let the whole mix hit true digital silence — under a static frame on a
phone it reads as a playback failure. Keep room tone under every pause.

---

## What the linter checks

`scripts/hookcheck.py`:

**TTS safety and cadence**

| Check | Level |
|---|---|
| SSML tags or `[[slnc]]` markers in the text | error |
| Parentheses or square brackets | error |
| Digits, `$`, `%`, or abbreviations like `St.` / `No.` | error |
| Bare homographs without a disambiguating neighbour | warning |
| Sentence longer than the register's cap | error |
| Sentence longer than the register's target | warning |
| Throat-clearing opener ("hey guys", "welcome back", "today I want to…") | error |
| Opening sentence over the register's limit | warning |
| No `...` anywhere (no engineered beat) | warning |
| File over 4096 bytes | warning |
| Mean sentence length outside the register's cadence band | warning |
| Estimated duration at a given `--wpm` | info |

**Promise and payoff** — these check what the script *owes the viewer*, which
is the part that actually decides retention:

| Check | Level |
|---|---|
| `empty-tease` — "watch until the end", "you won't believe" with no named payoff | warning |
| `unsupported-superlative` — "world's", "largest", "first ever" without a `{c…}` claim reference | warning (info if the script has no ledger) |
| `hype-without-execution` — the opening minute is all future tense | warning |
| `loop-ledger` — a loop closed before it opens, closed twice, or never closed | error |
| `late-loop` — a loop opened in the final tenth of the script | warning |
| `sponsor-reset` — a sponsor mention with no story bridge | warning |

### Directives

The story-editor's annotations live on their own `>` lines, immediately below
the narration line they describe:

```markdown
l5  Why did the bell ring thirteen times?
> loop A open
l7  The thirteenth strike was a flood warning.  {c14}
> loop A close
```

| Directive | Says |
|---|---|
| `> loop <name> open\|progress\|close` | The loop ledger, in the script itself |
| `> execution` | The promising has stopped and the thing is now happening |
| `> payoff: <what it pays>` | This tease names its payload; stop warning about it |
| `> sponsor: story-bridge` | The sponsor segment is bridged into the story |

**Why `>` and not braces.** The screenwriter's `scriptcheck` reads a trailing
`{...}` as a comma-separated list of *claim ids* and errors with "cites unknown
claim" on anything not in the ledger — so an inline `{loop:A:open}` would break
the tool upstream of this one. A `>` line matches neither its line pattern nor
its continuation rule, so it is ignored by `scriptcheck`, ignored by
`narration_of`, and never reaches edge-tts.

**What it deliberately does not check:** cut intervals, re-hook timers, a 70%
thirty-second threshold, a 50% APV rule, or a universal opening word count
across registers. Every one of those is either folklore or a house preference,
and a linter that enforced them would be asserting things nobody can source.

---

## Sources

github.com/rany2/edge-tts (README and `mkssml()`) · Azure Speech SSML docs
(`<break strength>` 250/500/750/1000/1250ms) · ITU-R BS.1770 · EBU R128 ·
WCAG 2.1 Technique G56 · Yuan, Liberman & Cieri, Interspeech 2006 ·
Rodero on radio pace ·
Verizon Media × Publicis Media, 2019 (sound-off viewing — a survey of stated
behaviour, not a measurement of plays) ·
Wöllner, Hammerschmidt & Albrecht, *PLOS ONE*, 2018,
[10.1371/journal.pone.0199161](https://doi.org/10.1371/journal.pone.0199161)
(music, slow motion, arousal and perceived duration).
