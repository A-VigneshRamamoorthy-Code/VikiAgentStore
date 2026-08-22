# Script format

The dialect `scriptcheck.py` parses. It is plain Markdown, so it renders
readably anywhere, and it is strict enough to lint.

---

## Skeleton

```markdown
---
title: The Longest Winter
topic: The 1709 European cold wave
target_duration: 600
wpm: 100
tolerance: 0.08
ledger: ledger.json
sensitive: false
---

# The Longest Winter

## [00:00] The night it arrived

l1  On the night of 5 January 1709, the temperature across western Europe collapsed.  {c-onset-date}
l2  At least 100,000 people in France died over the months that followed.  {c-france-toll}

## [00:57] What froze

l3  Rivers froze to the seabed at their mouths, and coastal shipping stopped.  {c-rivers, c-shipping}
```

---

## Frontmatter

| Key | Required | Meaning |
|---|---|---|
| `title` | yes | Working title |
| `topic` | yes | Subject, for the report header |
| `target_duration` | yes | Seconds |
| `wpm` | yes | Gross words per minute — see [duration-model.md](duration-model.md) |
| `tolerance` | no | Fraction, default `0.08` |
| `ledger` | yes | Path to `ledger.json`, relative to the script |
| `sensitive` | no | `true` enables the vocabulary checks in [sensitive-subjects.md](sensitive-subjects.md) |

---

## Chapters

```markdown
## [MM:SS] Chapter title
```

The timecode is the chapter's **intended start**. The linter recomputes the real
start from the cumulative word count and warns on a drift over ±12 s.

---

## Lines

```
l<N>  <narration text>  {claim-id, claim-id}
```

- `l<N>` is a stable id. It is what the storyboard and the TTS timing map onto,
  so **do not renumber lines** once a storyboard references them. Insert `l7a`
  rather than shifting everything below.
- Narration text is what is spoken, and only what is spoken.
- The trailing brace lists every claim the line depends on.

### Continuation

Indent to wrap a long line. The brace goes on the last physical line:

```
l19  The commission concluded that the signalling fault had been reported twice
     in the preceding year, and closed both times without repair.  {c-fault-reports}
```

### Unsourced lines

A line that asserts nothing factual is marked `{~}`:

```
l30  Nobody was coming.  {~}
l31  Not for a long time.  {~}
l32  That is where the official account stops, and the argument begins.  {~}
```

`{~}` is for rhythm, transition and rhetoric. **A `{~}` line may not contain a
digit, a date, a time or a figure** — the linter rejects it. If it needs a
number, it needs a claim.

Use `{~}` sparingly. Above roughly one line in six, the script has stopped being
reported and started being written.

### Direction

Bracketed direction is ignored by the word count and never spoken:

```
l44  [[pause 1.2]]
l45  A third of the dead were under sixteen.  {c-age-profile}
```

`[[pause N]]` is the portable form. `paper` style consumes the
`[[slnc N]]` millisecond form; convert at hand-off.

---

## Hedges

If a claim is marked `"contested": true`, every line using it must contain a
hedge:

> at least · about · around · roughly · more than · nearly · some · an
> estimated · up to · over · approximately · in excess of · close to

```
l7  At least 100,000 people died.  {c-france-toll}     ✅
l7  100,000 people died.  {c-france-toll}              ❌ contested claim, no hedge
```

---

## Attribution

Prefer an attributed sentence to a bare one wherever the fact is `medium`
confidence or politically live:

```
l64  The manufacturer's own service bulletin describes the part as
     "not intended for continuous load".  {c-bulletin}
```

Attribution is not hedging. Both may be needed; neither substitutes for the
other.

---

## What the linter checks

`scriptcheck.py` reads the script, resolves `ledger` relative to it, and reports
at three severities. Errors fail the run; `--strict` makes warnings fail too.

| Check | Severity |
|---|---|
| Word count fits `target_duration` at `wpm`, within `tolerance` | error |
| Every line carries `{claim-ids}` or an explicit `{~}` | error |
| Every referenced claim exists in the ledger | error |
| Every claim has ≥ 2 **distinct** sources, all of which exist | error |
| A `{~}` line contains a number, date or figure | error |
| A `contested` claim is spoken without a hedge word | error |
| Duplicate line id, or a claim with an invalid `confidence` | error |
| A source is missing a URL or an access date | warning |
| A `high` confidence claim rests only on tier C sources | warning |
| A `contested` claim records no `note` | warning |
| Chapter drifts more than ±12 s from its heading timecode | warning |
| A line runs over 18 words, or a chapter is empty | warning |
| Dramatising vocabulary while `sensitive: true` | warning |
| A ledger claim is never used | info |

The figure test that governs `{~}` matches digits **and** the number-words
*one* through *twelve*, *dozen*, *hundreds*, *thousands*, *million*, *billion*.
It is word-boundary guarded, so "someone" is safe but "no one" is not.

---

## Hand-off

To **`paper` style**: line ids become `narration.lines[].id`, so beats
can be authored as `l12+0.35` rather than against wall-clock guesses. Convert
`[[pause 1.2]]` to `[[slnc 1200]]` and set `gap_after` from the chapter breaks.

To **`voice-booth`**: strip the ids, the braces and the direction; keep
the line breaks, which is where the breaths go.

```bash
python3 scriptcheck.py script.md --plain > narration.txt
```
