# Voiceover Generation Details

## Setup

`edge-tts` is a Python package, so install it in its own virtual environment.
Use this path — it is one of the locations `paper-explainer`'s `tts.py` searches
automatically:

```bash
python3 -m venv ~/.cache/video-craft/tts_env
~/.cache/video-craft/tts_env/bin/pip install edge-tts
```

It needs **no account, no API key and no credential**. Override the location
with `EDGE_TTS_BIN` if you keep it elsewhere.

## Preferred voices

| Accent | Voice |
|---|---|
| British male | `en-GB-RyanNeural` |
| Irish female | `en-IE-EmilyNeural` |
| Singaporean female | `en-SG-LunaNeural` |

Defaults in `tts.py` are `en-IE-EmilyNeural` at `--rate="-15%"`, `--pitch="-5Hz"`.

That default suits a **short** piece — a 2–3 minute hook-driven film, which is
what the rate was calibrated against (see `hook-engineering/reference/
tts-scripting.md`, whose word budgets assume it). For anything long-form, pass
`--rate="+0%"` explicitly and control the pace with gaps instead; see *Pacing
and pauses* below for why.

## Pacing and pauses

**Do not slow a documentary down with a negative `--rate`.** It is the obvious
lever and it is the wrong one: it stretches the vowels rather than opening up
the spaces, so the delivery reads as sedated instead of deliberate. A 12-minute
film cut at `-33%` was rejected by its viewer as "too slow" even though its
gross rate was a normal 105 wpm — the words themselves were the problem.

Record at the natural rate (`--rate="+0%"`) and buy the pace back **entirely in
the gaps between lines**. Natural speech near 175 wpm with generous gaps reads
as measured and confident; the same 175 wpm with tight gaps reads as urgent.
That single control gives you both without ever touching the voice.

Size the gaps by solving rather than guessing: give each line a *relative*
weight (a beat after a revelation is worth ~3x a beat mid-sentence), then scale
every weight by one constant so that
`speech + Σgaps + lead_in + tail` equals the target duration exactly. Clamp to
a floor and ceiling (0.3 s / 4.2 s works well) and redistribute the remainder.

A small pitch drop (`--pitch="-5Hz"`) is still worth having for a sombre read —
it costs no intelligibility. It is only the *rate* that must stay at zero.

Ellipses and line breaks in the source text produce *some* natural breathing,
but they are approximate. When a pause has to be exact — because a visual beat
lands on a word — use `[[slnc N]]` (milliseconds) and let the renderer split the
line on each pause, synthesise every span separately and butt-join them. That
gives a pause of exactly N ms rather than whatever the model felt like.

## Three things to know about edge-tts

1. **It ignores SSML, and it has no emphasis markup.** `*word*` is silently
   dropped, not spoken with stress. If you need emphasis, get it from word
   choice and from pauses either side, or use Gemini/OpenAI TTS, which accept a
   style prompt.
2. **It is materially slower than macOS `say` at the same nominal rate.** A
   script that timed to 29.7 s under `say` came out at **33.5 s** on the first
   edge pass — 13 % longer. That is the difference between fitting a 30 s slot
   and missing it.
3. **So never assume a timeline survives a provider change.** Re-measure after
   switching. In `paper-explainer` that means re-running `--sheet`, which
   re-synthesises and re-times everything.

## Proper nouns: respell them, and use hyphens

An English-language voice mangles unfamiliar names, and it does so most often by
**swallowing the final vowel** — `Karkare` becomes "kar-KAIR", `Omble` becomes
"OM-bl", `Vile Parle` becomes "vyle parl". In a film that names real people this
is not a cosmetic problem.

edge-tts ignores SSML, so `<phoneme>` is unavailable. Respell the word phonetically
in the text instead, and keep the display spelling separate from the spoken one —
a `SAY_AS` dict applied when the lines are built, so the script on disk still
reads `Karkare` while the synthesiser receives `Kar-ka-ray`.

**Hyphens are safe, and they help.** Measured on `en-IE-EmilyNeural`:

| spoken text | duration |
|---|---|
| `Karkaray` | 1.78 s |
| `Kar-ka-ray` | 1.87 s |
| `Chhatrapatee` | 2.02 s |
| `Chha-tra-pa-tee` | 2.18 s |

Each hyphen costs roughly **0.05–0.15 s** of extra syllable separation. The
hyphen is *not* voiced as the word "dash" — that would add ~0.4 s apiece and is
the failure everyone fears. The mild separation it does produce is an asset for
a name the audience has never seen, so prefer the hyphenated form.

Verify a respelling by synthesising it alone and comparing against the
unhyphenated spelling; a duration far beyond the table above means the voice is
reading punctuation and the respelling needs rewording.

## Example

```bash
~/.cache/video-craft/tts_env/bin/edge-tts \
  --voice en-IE-EmilyNeural --rate="-13%" --pitch="-8Hz" \
  --file script.txt --write-media voiceover.mp3
```

## Checking the result

Measure, do not guess:

```bash
ffprobe -v error -show_entries format=duration -of csv=p=0 voiceover.mp3
```

Gross pace for documentary narration is **100–115 words per minute**. Below ~95
it drags; above ~120 it stops sounding like a documentary and starts sounding
like a corporate explainer.
