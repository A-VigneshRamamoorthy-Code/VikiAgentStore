# PENDING — what still needs a human

The voice cast is **built, measured and screened**. Nine named characters exist,
all pass `analyze.py`, all pass `qa.py` (no uneven pauses, every clip inside the
3-spike budget), all decode in a browser, and every same-gender pair is timbrally
separable. What remains cannot be settled by measurement.

Everything below except §5 needs a **native Tamil ear**. None of it is a code
task; §5 is a rebuild that only needs an idle machine.

## 1. Tamil pronunciation

No script in this skill can check pronunciation. `intelligibility.py` gets
closest — it transcribes the output back and scores the match — but Whisper
cannot hear a botched **ழ**, and it has its own error rate on colloquial Tamil.
Treat its numbers as "where to listen first", never as a verdict.

Listen to `karthik`, `meera`, `divya`, `valluvar` and `pallavi` and confirm:

- **ழ / ள / ல** are distinct (`வாழை` vs `வாளை` vs `வாலை`)
- **ண / ன / ந** are distinct
- **ற / ர** are distinct
- post-nasal voicing is right — `பந்து` is *pandhu*, not *panthu*;
  `சிங்கம்` is *singam*, not *sinkam*
- the Tanglish samples don't mangle the English words inside Tamil sentences

If a sound is consistently wrong it is a limitation of the model, not the
reference; the fix is rephrasing, not re-cloning.

## 2. Pick the Tamil house voice from the A/B

`build_ab.py` renders the **same three lines** through every candidate reference
and the gallery ranks them by the mean. The free native `ta-IN` Edge
voices win: **Pallavi 92.2 %**, **Valluvar 91.0 %**, ahead of the model's own
no-reference voice (90.2 %) and all the ElevenLabs clones (88.0-89.4 %). The Edge
voices are also the most consistent across lines.

**Resolved.** Both native `ta-IN` Edge voices now ship as first-class characters
(`valluvar`, `pallavi`) with `engine: "edge"` — spoken directly, never cloned,
never pitch-shifted. Raw Edge measured cleaner than its own clone (0-1 pitch
spikes vs 2-3) and was preferred on listening.

`out/ab/` is **not** shipped with the skill — it was audition scratch, and the
question it settled is closed. Re-open this only if a *third* Tamil voice is
needed, in which case regenerate the comparison and let it decide:

```bash
.venv/bin/python scripts/build_ab.py     # regenerate
.venv/bin/python scripts/serve.py        # listen
```

## 3. Confirm the close same-gender pairs by ear

`timbre.py` compares MFCC profiles, but the threshold is a heuristic. Check the
pairs it reports as `close` in continuous speech — a card-length audition is not
long enough to tell two similar voices apart.

```bash
.venv/bin/python scripts/timbre.py --manifest out/cast/manifest.json
```

If a pair reads as the same person, **re-cast one from a different reference
recording**. Do *not* reach for a `pitch` offset: Edge's `pitch` is not an offset
on the median (`-40Hz` moved a voice 80 Hz), and the two voices that shipped that
way were both rejected on listening. See `reference/voices.md`.

## 4. Romanised Tanglish has never been checked by ear

Latin-script Tamil is synthesized with the **English** model (see
`reference/language-detection.md`). It is expected to be approximate. Nobody has
yet confirmed it is *acceptable* rather than merely intelligible. Render one to
hear it:

```bash
.venv/bin/python scripts/voice.py \
  --script "Indha vaaram oru special-aana topic paakalam." \
  --voice karthik --out /tmp/tanglish.mp3
```

If it turns out to be bad, the honest fix is to make `voice.py` refuse romanised
Tamil and tell the operator to supply Tamil script, rather than quietly producing
something wrong.

## 5. Optional: re-roll the three high-drift voices

Not an ear task — just machine time. Three characters sit above the 5 % pitch-drift
target: **Everett 8.5 %**, **Divya 6.1 %**, **Imogen 5.9 %**. They pass every other
acceptance check, so this is polish rather than a defect.

```bash
.venv/bin/python scripts/build_cast.py --characters templates/characters.json \
  --only everett,divya,imogen --tries 5
```

Run it on an **idle** machine. Each candidate costs ~45-60 s when the box is free;
under heavy load (this one was sharing with a video render at load average 17-20)
the MLX process drops into I/O wait at ~3 % CPU and a five-candidate voice can
take hours. If a rebuild appears hung, check `ps -o state=` for `U` and
`sysctl vm.swapusage` before assuming the code is at fault.

`--only` merges into the existing manifest, so rebuilding three characters will
not discard the other six.

---

## Not pending

- ~~Create the named voice cast~~ — done, 9 characters in
  `templates/characters.json`.
- ~~Language decided per text rather than per character~~ — done,
  `detect_lang()`, 17/17 on the test set.
- ~~Objective distinctness check~~ — done, `scripts/timbre.py`.
- ~~Add Valluvar and Pallavi~~ — done, both native `ta-IN` Edge references.
- ~~"The clone stopped matching the source"~~ — diagnosed as stochastic
  generation, fixed by best-of-N (`--tries`).
- ~~"Tamil lacks natural pronunciation"~~ — measured across six references and
  three lines; the native `ta-IN` Edge voices (Valluvar, Pallavi) rank highest
  and are now in the cast.
- ~~Misaligned references~~ — `REF_MAX_S` exceeded OmniVoice's own 10 s cap, and
  three references described more audio than the model read. Fixed via
  `REF_MAX_S = 10.0` and `ref_trim`; `check_refs.py` now reports 0 suspect.
