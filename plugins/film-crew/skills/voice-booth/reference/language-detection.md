# Language detection

`voice.py` decides Tamil / Tanglish / English **from the text**, per sentence
chunk. A character's `lang` field is only its native accent — it never limits
what the voice can say. `--lang` overrides detection when you need to force it.

`core.detect_lang(text)` returns:

```python
{"lang": "ta"|"en",           # what the model is asked for
 "label": "tamil"|"tanglish"|"english",   # what a human would call it
 "tamil_ratio": 0.0-1.0,      # share of letters in Tamil script
 "hint": str|None}            # advice shown to the operator
```

## The rules, in order

1. **No letters at all** → `english`. Digits and punctuation alone have no
   language.
2. **Tamil script present, no multi-letter Latin word** → `tamil`.
3. **`tamil_ratio >= 0.15`** → `tanglish`.
4. **Romanised Tamil markers** (no Tamil script):
   one STRONG marker, or two WEAK markers with fewer than two English
   stopwords → `tanglish`, synthesized as `en`, plus a hint.
5. **Otherwise** → `english`.

## Why the thresholds are what they are

**A ratio alone cannot separate Tamil from Tanglish.** The obvious approach —
"≥85 % Tamil characters means Tamil" — is wrong. One English word in a long
Tamil sentence still leaves the ratio near 0.95, but the sentence is Tanglish
and needs Tanglish handling. The discriminator is the *presence of a Latin
word*, not a ratio.

**`len(word) > 1` matters.** A lone Latin letter is not an English word. Tamil
text routinely carries stray single characters — a list marker, an initial, a
transliterated particle — and counting those as code-switching would push pure
Tamil into the Tanglish path. Only a Latin run of **two or more** letters counts.

Note that `special-ஆ இருக்கும்` *is* Tanglish, and correctly so: `special` is a
real English word, and the attached `-ஆ` is a Tamil particle. That mix — Tamil
script with English words dropped in — is the single most common register in
Tamil media, and it is exactly what rule 2 is designed to catch.

**Markers are split STRONG / WEAK because romanised Tamil is ambiguous.**
`enna`, `illa`, `pannunga`, `irukku` are Tamil and essentially nothing else, so
one is enough. But `naan` is also bread, `sari` is also a garment, and `ava` and
`anna` are also names — those are WEAK and need corroboration.

**English stopwords veto weak markers.** "Anna and Ava ate naan with
sari-wrapped gifts" trips three WEAK markers and is unambiguously English. The
words `the`, `and`, `with`, `of`… never appear in romanised Tamil, so two or
more of them override weak evidence. This single rule fixed the only remaining
failure in the test set.

## Romanised Tamil is routed to the English model

There is no Tamil-phonetics path for Latin script, so `lang="en"` is used and
English letter-to-sound rules approximate the Tamil. It is intelligible but not
correct, so a hint is attached recommending Tamil script for anything that
matters. **Tamil script always produces better pronunciation than romanised
Tamil.**

## Changing the rules

The marker sets and thresholds live at the top of `core.py`. If you add a
marker, add a case to `scripts/test_detect.py` and run the **whole** set:

```bash
.venv/bin/python scripts/test_detect.py
```

The sets interact, and a marker that looks safe alone often collides with an
English word — checking only the new case is how regressions get in. The
`tamil_ratio` threshold of 0.15 is deliberately low: mixed sentences are far
more common than pure ones in real Tamil speech.
