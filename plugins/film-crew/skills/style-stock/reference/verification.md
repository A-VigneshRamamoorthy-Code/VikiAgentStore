# Verification before shipping

Do not ship straight from fetch to full render. The failures that matter in a
stock film are easy to miss in playback and obvious in a grid.

## 1. Validate the style and the board

```bash
cd <repo>/plugins/film-crew/skills
python3 production-designer/scripts/registry.py doctor stock
```

Then validate compile:

```bash
cd <repo>/plugins/film-crew/skills/style-stock
python3 scripts/compile.py examples/heist/beat-plan.json --check
```

A blocking note means the storyboard would contain a placeholder. Fix the beat
or accept the placeholder consciously; do not let it pass unnoticed.

## 2. Fetch and read the unresolved list

```bash
python3 scripts/fetch.py storyboard.json
```

The final lines report how many shots have footage and list `UNRESOLVED` shots.
Any unresolved shot renders as a labelled `NO FOOTAGE` slate and exits non-zero
from fetch. This is intentional. A wrong substitute would be a false picture.

Check `assets.json` exists beside the storyboard after a non-dry run.

## 3. Render the contact sheet

```bash
python3 scripts/render.py storyboard.json --sheet
```

The contact sheet is the gate. It writes one labelled frame per shot. Look at
it before a full render.

Specifically check:

- the same clip or same composition answering two different beats;
- a run of shots flattened to one colour by the grade;
- labelled `NO FOOTAGE` plates;
- obvious synthetic/vector footage that escaped rejection;
- title and keyword plates covering important picture content;
- vertical or square crops when the storyboard aspect is `9:16` or `1:1`.

The two practical failures are duplicate-looking clips and a grade that turns a
sequence into one colour. A single frame will not catch either.

## 4. Understand what render normalises

Each shot is rendered as its own normalised segment before concat. The segment
pass enforces fps, SAR, pixel format and no source audio. This is necessary
because stock clips arrive at mixed resolutions, frame rates, pixel formats and
with or without audio. Joining raw clips with the concat demuxer silently makes
broken files.

Text is PIL PNG plus `overlay`, never `drawtext`. The ffmpeg build used for
this style has no `drawtext` because it lacks `libfreetype`.

Push-ins use `scale` with `eval=frame`, not `zoompan`, to avoid integer-crop
judder on hard edges.

Auto-exposure is partial gamma correction before the grade: strength `0.5`,
gamma clamped to `[0.78, 1.30]`, luma sampled by `signalstats`/`YAVG` at `3fps`,
median not mean. If a contact sheet goes milky, compare once with
`--no-auto-exposure`; do not replace this with brightness correction.

## 5. Full render and sidecars

```bash
python3 scripts/render.py storyboard.json -o film.mp4
```

Render writes:

- `film.mp4`;
- `film.timeline.json`, built from the rendered segments;
- audio mixed with sidechain ducking and `loudnorm=I=-14` when narration or bed
  exists.

The manifest's verification targets are: `1920x1080`, `30fps`, loudness
`-14 LUFS`, true peak `-1 dBFS`, mean motion minimum `1.0`, target `3.0`, and
loudness tolerance `1.5 LU`. The current scripts do not implement a separate
verifier; treat these as the contract for manual or external checks.

## 6. Final human checks

Watch the film once with the timeline open. For each suspicious shot, compare
`timeline.shots[].query`, `timeline.shots[].clip`, storyboard `clip.page` and
`assets.json`.

For true-crime and reportage, ask one extra question: could this clip imply an
identifiable person or place is connected to the allegation? If yes, replace it
with neutral B-roll or another style.
