# The cast

Nine voices, built and measured. `--voice` accepts the **key** or the **name**,
case-insensitively.

## Tamil

| Key | Name | Sex | F0 | Engine | Use for |
| --- | --- | --- | --- | --- | --- |
| `valluvar` | Valluvar | m | 145.5 Hz | edge | Formal Tamil narration, documentary, explainer. Textbook diction. |
| `karthik` | Karthik | m | 138.5 Hz | clone | Everyday Chennai **Tanglish** — conversational, wry, talking to a friend. |
| `pallavi` | Pallavi | f | 246.2 Hz | edge | News-presenter Tamil — bright, crisp, headline clarity. |
| `meera` | Meera | f | 238.8 Hz | clone | Warm Tamil storyteller — gentle, expressive, children's-story cadence. |
| `divya` | Divya | f | 258.1 Hz | clone | Bright Tamil service voice — professional, customer-support poise. |

## English

| Key | Name | Sex | F0 | Engine | Use for |
| --- | --- | --- | --- | --- | --- |
| `everett` | Everett | m | 108.1 Hz | clone | American storyteller — warm, deep, unhurried bedtime-story delivery. |
| `zane` | Zane | m | 158.4 Hz | clone | High-energy promo — bright, punchy, launch-trailer drive. |
| `harper` | Harper | f | 187.1 Hz | clone | Polished American product narrator — clear, confident, explainer pace. |
| `imogen` | Imogen | f | 173.9 Hz | clone | British broadcast journalist — measured, authoritative, documentary calm. |

## Every voice speaks every language

A character's `lang` is its **accent, not its limit**. The reference supplies
timbre; the script supplies language. Meera can read English (with a Tamil
accent); Imogen can read Tamil script. `lang` only picks the audition line and
groups the voice in the gallery.

For a Tanglish script this is a feature, not a compromise — a Tamil voice reading
embedded English words with a Tamil accent is what the register actually sounds
like.

## Engines

| | `edge` | `clone` |
| --- | --- | --- |
| Speed | ~1 s/clip | 45–60 s/sentence |
| Model | none | 2.5 GB, ~15 s load |
| Needs a reference | no | yes |
| Voice | what Microsoft ships | any specific person |

**For Tamil, prefer `edge`.** Cloning a native `ta-IN` Edge voice through
OmniVoice measurably degrades it: the raw voice carries 0–1 pitch spikes where
its own clone carries 2–3, and a listener comparing them picked the raw voice
unprompted. Reach for `clone` when the voice has to be a *specific* person, or
when you need a register Microsoft doesn't ship — colloquial Chennai Tanglish
(Karthik) has no Edge equivalent.

A script that uses only `edge` voices never loads the model at all.

## Never pitch-shift an Edge voice to make a new character

Valluvar and Pallavi originally shipped with `pitch` offsets (`+28Hz`, `-40Hz`)
to separate them from the cloned cast. Both were rejected on listening.

The cause is measurable: Edge's `pitch` is **not** an offset on the median F0.
`-40Hz` on `ta-IN-PallaviNeural` moved the measured median from **262.3 Hz to
181.8 Hz** — an 80 Hz drop, double what was asked for, dragging the voice out of
its natural register.

Both now ship unshifted. If you set `pitch` at all, re-measure with `median_f0`
afterwards and keep the result inside the gender range; beyond ±20 Hz it sounds
pitch-shifted rather than like a different person.

## Distinctness

Verified with `scripts/timbre.py` — cosine similarity of the average cepstrum:

- **< 0.90** different people
- **< 0.97** close; confirm by ear
- **≥ 0.97** listeners will not tell them apart

All 16 same-language pairs are separable. The closest are `karthik / valluvar`
(0.955) and `divya / meera` (0.959) — both just inside the line, and both
distinguished in practice by register rather than timbre (colloquial vs formal,
storyteller vs service). Do not add a tenth Tamil voice without re-running
`timbre.py`.

Do **not** use F0 for this judgement. Harper and Imogen sit 13 Hz apart yet are
the most distinct pair in the entire cast (0.808), because one is American and
one is British.

## Adding a voice

See `reference/building-a-cast.md`. In short: add an entry to
`templates/characters.json`, build with `--only <key>`, then re-run
`qa.py`, `timbre.py` and `analyze.py` before shipping it.
