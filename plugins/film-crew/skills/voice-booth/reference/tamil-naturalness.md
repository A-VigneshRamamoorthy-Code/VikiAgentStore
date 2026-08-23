# Making Tamil TTS sound natural

Ordered by impact. The first item matters more than which model you use.

---

## 1. Register — the biggest lever, by a wide margin

Tamil is strongly **diglossic**. Literary Tamil (செந்தமிழ்) and spoken Tamil
(பேச்சுத் தமிழ்) are effectively different grammars. Synthesizing written Tamil
sounds like a textbook read aloud, no matter how good the acoustics are.

```
written    அவர்கள் அங்கே சென்றார்கள்      avargal ange sendraargal
spoken     அவங்க அங்க போனாங்க             avanga anga ponaanga

written    இருக்கிறது                      irukkiradhu
spoken     இருக்கு                         irukku
```

Corroboration: **AI4Bharat's own Tamil demo prompt is colloquial**, not literary —
`நான் நெனச்ச மாதிரியே அமேசான்ல பெரிய தள்ளுபடி வந்திருக்கு` (`நெனச்ச` is the
spoken form of `நினைத்த`).

**Fix — normalise before synthesis.** An LLM does this well:

> Rewrite this formal Tamil text into natural spoken Chennai Tamil as a YouTube
> narrator would say it. Keep common English words in English. Do not translate.

Two consequences for this skill:

- The audition line in `core.py` is deliberately colloquial.
- If someone hands you formal Tamil to narrate, convert it first. Skipping this
  wastes the entire rest of the pipeline.

---

## 2. Allophonic voicing — the #1 robotic tell

Tamil orthography systematically under-represents its phonology. The stops
**க ச ட த ப** change voicing by position, and this is **never written**:

| Written | Position | Actually said |
| --- | --- | --- |
| கப்பல் | word-initial | **k**appal |
| அகம் | intervocalic | a**g**am / a**h**am |
| சிங்கம் | post-nasal | sin**g**am (not "sin**k**am") |

A naive engine maps க → /k/ everywhere and says "Sinkam". Native listeners flag
this instantly — it is the single most common giveaway.

**Test any voice with a post-nasal word** (சிங்கம், தங்கம், பங்கு) before
approving it.

---

## 3. The retroflex/alveolar series: ழ ள ண ற ன

Second-tier but disqualifying. If **ழ** collapses toward L or Y, the voice is not
usable for Tamil regardless of what the measurements say.

There is **no acoustic metric for this** — it needs a native ear. It is the one
acceptance check in `PENDING.md` that cannot be automated.

Test words: தமிழ் / வாழ்க / அழகு (ழ), வெள்ளை (ள), மண் (ண), மற்றும் (ற), நான் (ன).

---

## 4. Tanglish is the norm, not an edge case

Conversational Tamil media is heavily code-mixed. Common English words stay in
English — "special", "actually", "video", "channel", "comment". Translating them
into pure Tamil is *less* natural, not more.

Keep them in Latin script in the input; OmniVoice handles the switch.

---

## 5. Prosody: vary per phrase, not per passage

One rate and pitch across a whole paragraph is what makes TTS drone. Vary
per-sentence. `voice.py` already chunks by sentence, which gives natural phrase
boundaries; the remaining variation comes from the writing.

Write with the rhythm you want: short sentence, short sentence, long one. Direct
address ("நண்பர்களே", "கேட்க தயாரா?") reads as speech; nested clauses read as
prose.

---

## Which models can actually speak Tamil

Verified by reading tokenizers and vocab files — **the HuggingFace language tags
are frequently wrong**.

### Genuinely support Tamil

| Model | Evidence |
| --- | --- |
| `k2-fsa/OmniVoice` | 423.09 h of Tamil in a 581 k-hour corpus — **what this skill uses** |
| `bosonai/higgs-tts-3-4b` | Tamil in the top "WER/CER < 5" tier |
| `ai4bharat/IndicF5` | 1,417 h across 11 Indian languages; ships a colloquial Tamil prompt |
| `SPRINGLab/SPRING_F5` | Ships `example1_ta.wav` and `codemix_ta.wav`; `lang='ta'` first-class |
| `kenpath/svara-tts-v1` | `ta_male` / `ta_female` profiles |

### Output confident gibberish for Tamil — do not use

| Model | Proof |
| --- | --- |
| **XTTS-v2** | `tokenizer.py` dispatches on 17 languages; `[ta]` is not among them |
| **Chatterbox** | 23 languages — Hindi yes, Tamil no |
| **Kokoro-82M** | `misaki` G2P has no Tamil module |
| **Bark** | no `ta_` speaker prompts exist |
| **StyleTTS2** | English-only checkpoints |
| **Zonos** | 5 languages; also Linux + NVIDIA only |
| **F5-TTS (base)** | Tamil exists only via the IndicF5 / SPRING_F5 forks |

### Tagged for Tamil but degraded

- `facebook/mms-tts-tam` — vocab is broken (digit "8", ஔ and ஃ all missing).
- `ai4bharat/indic-parler-tts` — Tamil is its worst language by AI4Bharat's own
  metric; only 52 h of Tamil.
- Community Piper Tamil voices — the model card admits Tanglish failure.
- ⚠️ The widely repeated claim that Piper ships `ta_IN-ketaka-medium` is **false**;
  the path 404s.

---

## Free Tamil Edge voices (reference sources)

Eight neural voices across four locales, no API key:

| Locale | Female | Male |
| --- | --- | --- |
| ta-IN | Pallavi | Valluvar |
| ta-LK | Saranya | Kumar |
| ta-MY | Kani | Surya |
| ta-SG | Venba | Anbu |

These are genuinely different speakers — prefer them over pitch-shifting one
voice. Confirm with `scripts/list_voices.py --lang ta`.

---

## Cross-lingual note

An English reference clones into Tamil speech successfully — measured 1.2 % median
F0 drift (192.8 → 195.1 Hz). **But pronunciation comes from the model, not the
reference speaker.** A cross-lingual Tamil voice still has to pass the ழ/ள/ண/ற/ன
check by ear.

---

## Measured: which Tamil reference actually pronounces best

Guessing is useless here. `scripts/build_ab.py` synthesizes the **same lines**
through each candidate, transcribes them back with Whisper and scores the match.
It is a *proxy* — it cannot hear ழ — but it reliably catches mush.

**Score over several lines, never one.** A single line ranked these candidates in
almost the opposite order: Pallavi scored 85.0 % on one line and 93.4 % on
another, which was enough to move it from last to first. `build_ab.py` therefore
averages three lines in different registers and reports the spread.

Mean of three lines (dramatic / greeting / plain), higher is better:

| Reference | Mean | Spread |
| --- | --- | --- |
| **Pallavi** — `ta-IN` Edge clone | **92.2 %** | 5.4 |
| **Valluvar** — `ta-IN` Edge clone | **91.0 %** | 6.8 |
| no reference — OmniVoice "smart voice" | 90.2 % | 10.1 |
| ElevenLabs Tamil female | 89.4 % | 6.8 |
| ElevenLabs Tamil male, full reference | 89.3 % | 6.0 |
| ElevenLabs Tamil male, trimmed reference | 88.0 % | 9.0 |
| any of the above **+ `instruct`** | worse, → 0.0 % with no reference | — |

Conclusions:

- **A free native `ta-IN` Edge voice is the best Tamil reference available here.**
  Pallavi and Valluvar top the table *and* have the tightest spread, meaning they
  degrade least on lines they were not tuned for. They cost nothing and need no
  consent negotiation.
- The model's own no-reference voice is respectable but the **least consistent**
  (spread 10.1) — good on plain prose, weakest on conversational greetings.
- **Trimming a reference did not measurably improve pronunciation.** The 1.3-point
  gap between the trimmed and untrimmed ElevenLabs male sits inside both spreads.
  An earlier single-line measurement suggested a 7.7-point win; averaging showed
  that was noise. Trim for *alignment*, not for intelligibility — see below.

---

## Reference hygiene — what it does and does not buy you

`ref_text` must be **what the audio actually says**. OmniVoice aligns the two; a
mismatch makes it rush, slur or skip. `scripts/check_refs.py` transcribes every
reference and flags disagreement.

The worst case found here: a Tamil reference whose final sentences contained an
**English brand name and an English verb** mid-utterance:

```
… கூவுச்சு. ElevenLabs பேமன்ட் வரும்ன்னு wait பண்ணிட்டிருந்தேன். ஒன்னும் வரல.
```

**Fix — trim to the clean, single-language span** and cut `ref_text` to match:

```json
{
  "key": "karthik",
  "ref_audio": ".../tamil-male.mp3",
  "ref_trim": [0.0, 3.98],
  "ref_text": "அன்னைக்கி காலையிலா ஆறு மணி இருக்கும். கோழி கொக்கரக்கோன்னு கூவுச்சு."
}
```

What trimming reliably fixed, measured and repeatable:

| | Before | After |
| --- | --- | --- |
| `check_refs` match (harper, zane) | 64.8 %, 64.5 % | **100 %, 100 %** |
| F0 drift vs reference (karthik) | 15.2 % worst draw | **0.9 %** |
| Noise floor (harper) | −72.3 dB | **−99.0 dB** |
| Clone running short (karthik) | yes | no |

What it did **not** fix: round-trip intelligibility, which stayed inside the
measurement noise. Trim to make the reference honest, not to make it clearer.

A **short clean reference beats a long dirty one.** `prepare_ref` only warns
below 3 s: 4–5 s of clean speech clones very well, and every reference in the
shipped cast that needed trimming ended up in that range.

Note the related trap: `REF_MAX_S` must stay at **10.0 s**, because that is
OmniVoice's own cap and it truncates silently. A 12 s reference passes every
check while the model reads only the first 10 s, leaving the tail of `ref_text`
describing audio it never heard.

Find the cut point with word timestamps rather than by eye:

```bash
.venv/bin/python scripts/check_refs.py --characters templates/characters.json
```

**Read the diff before editing a `ref_text`.** Whisper's error rate on colloquial
Tamil is high enough that a correctly aligned Tamil reference lands in the
mid-70s — `karthik` scores 76.2 % with every word right and only the spelling
different (`ஆறு`/`ஆரு`, `மணி`/`மனி`), and it produces a 0.9 %-drift clone.
`check_refs.py` uses a lower threshold for Tamil for exactly this reason.

---

## Two traps that waste a lot of time

### `instruct` does nothing good

OmniVoice's `generate()` accepts free text wrapped in
`<|instruct_start|>…<|instruct_end|>`, so it looks like a style dial. **This
checkpoint is not instruction-tuned.** Passing a style instruction measurably
*hurt* every variant, and with no reference it collapsed completely — repeating
`நான் நான் நான்…` at 400 Hz, 5.8 s for a 10.5 s script, **0.0 % intelligibility**.

The parameter is still plumbed through `core.synth`, `voice.py --instruct` and the
character schema, because it is real and may work on a future checkpoint. It
defaults to off and prints a warning when used. Do not reach for it to fix
prosody.

### Prosody was never the problem

The obvious theory — "the clone sounds flat" — was tested first and was **wrong**.
`core.pitch_range_st()` measures expressiveness as the p10–p90 F0 spread in
semitones:

| | Source | Clone |
| --- | --- | --- |
| male | 10.37 st | 10.85 st |
| female | ~6–11 st | ~6–11 st |

Clones already matched their sources. Roughly 5–8 st is lively; below ~2.5 st is
genuinely monotone. Measure before rewriting a prosody pipeline you do not need.

