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
- **Always pass `--write-subtitles`.** A free SRT, and roughly 69% of social video
  is watched muted in public; captions raise completion substantially.
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

Bed, not song — 55–70 BPM and no percussion for documentary. Duck **−10 dB**
under narration (WCAG G56 wants 20 dB if accessibility is the priority). Drop the
bed entirely for **exactly one** emotional line per piece; twice is a habit.

Master **−14 LUFS integrated, true peak ≤ −1 dBTP**. Verify:

```bash
ffmpeg -nostdin -i out.mp4 -af ebur128=peak=true -f null - 2>&1 | tail -12
```

Never let the whole mix hit true digital silence — under a static frame on a
phone it reads as a playback failure. Keep room tone under every pause.

---

## What the linter checks

`scripts/hookcheck.py`:

| Check | Level |
|---|---|
| SSML tags or `[[slnc]]` markers in the text | error |
| Parentheses or square brackets | error |
| Digits, `$`, `%`, or abbreviations like `St.` / `No.` | error |
| Bare homographs without a disambiguating neighbour | warning |
| Sentence longer than 24 words | error |
| Sentence longer than 16 words | warning |
| Throat-clearing opener ("hey guys", "welcome back", "today I want to…") | error |
| Opening sentence over 12 words | warning |
| No `...` anywhere (no engineered beat) | warning |
| File over 4096 bytes | warning |
| Estimated duration at a given `--wpm` | info |

---

## Sources

github.com/rany2/edge-tts (README and `mkssml()`) · Azure Speech SSML docs
(`<break strength>` 250/500/750/1000/1250ms) · ITU-R BS.1770 · EBU R128 ·
WCAG 2.1 Technique G56 · Yuan, Liberman & Cieri, Interspeech 2006 ·
Rodero on radio pace · Verizon Media × Publicis Media 2019 (sound-off viewing)
