# Caption craft

## Cue design

One cue per narration line is the default, because the line is what the
renderer timed. Split a line into two cues only when it exceeds the reading
budget:

```
characters in the cue ÷ seconds on screen ≤ 17
```

A cue must sit on screen for at least **1 second** even if the line is short —
below that it flickers and cannot be read at all.

## Line breaking

Break at a clause boundary, in this order of preference:

1. After a comma, semicolon, colon or dash.
2. Before a conjunction — *and*, *but*, *because*, *which*, *who*, *that*.
3. At the space nearest the middle that keeps both halves ≤ 42 characters.

Never break:

- between an article and its noun (*the / bomb*)
- between a preposition and its object (*into / the night*)
- inside a name (*D.B. / Cooper*)
- before a number's unit (*200,000 / dollars*)

The difference is measurable: a clause-broken caption is read faster and
remembered better than the same words broken by width alone.

## Spelling

The ledger is the authority. If the researcher wrote *Northwest Orient
Airlines*, the caption says that — not *Northwest Orient airline*, and
certainly not whatever the recogniser heard.

Numbers follow the narration, not the ledger's storage form: if the voice says
*"two hundred thousand dollars"*, the caption says `$200,000`. A viewer reading
along wants the figure; a viewer listening wants the words. Both get what they
came for.

## On-screen text

When the picture already carries the words — a headline card, a kicker, a
quoted document — the caption still carries the narration. Do not caption the
graphic. A viewer using captions is reading the caption *and* seeing the
graphic; duplicating it wastes the line.

The exception is a document the narration reads aloud. Then the caption is the
narration, which happens to match.

## Speaker changes

This pipeline is single-narrator, so speaker labels are noise. If a film ever
carries an interview clip, prefix the cue with a dash and the name:

```
- COOPER: I have a bomb in my briefcase.
```

## What to upload

Upload the **SRT**. YouTube accepts it, indexes it, and it survives a re-upload
of the video. WebVTT is written too, for players that prefer it and for a web
embed.

Do not rely on the platform's auto-captions as a fallback: once a caption track
is uploaded, YouTube stops offering the automatic one, so a broken upload means
*no* captions rather than mediocre ones. This is why `--check` verifies against
the finished film before the publisher touches it.
