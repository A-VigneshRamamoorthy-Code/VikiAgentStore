# Loudness, and why the target is sometimes unreachable

## The target

YouTube normalises playback to roughly **−14 LUFS integrated**. Deliver louder
and the platform turns it down, so the only thing loudness-war mastering buys
is a squashed mix. Deliver much quieter and the platform does *not* turn it up
past its ceiling, so it is simply quiet against everything around it.

True peak should stay at or below **−1.0 dBFS**. Lossy transcode adds
intersample peaks; a file that peaks at 0.0 dBFS clips after YouTube re-encodes
it, even though it measured clean locally.

## Why measuring matters more than targeting

`loudnorm` is a filter, not a guarantee. Given narration with a high **crest
factor** — a big gap between peak and average, which is exactly what clean,
close-mic'd speech has — it cannot raise the integrated level to target without
pushing peaks past the ceiling, so it stops short and says nothing.

The result is a film that *claims* −14 LUFS in its config and *is* −20 LUFS on
disk. The only way to know is to measure the finished file:

```bash
ffmpeg -hide_banner -nostats -i film.mp4 \
       -af ebur128=peak=true:framelog=quiet -f null -
```

or, with the report written out:

```bash
python3 skills/sound-designer/scripts/mix.py film.mp4 --report mix.json
```

## Reading the report

```json
"loudness_after": { "lufs": -19.4, "true_peak_dbfs": -1.2, "lra_lu": 7.8 }
```

| symptom | cause | fix |
|---|---|---|
| `lufs` well below target, peak near ceiling | crest factor too high | compress the **voice clips**, then reassemble |
| `lufs` at target, `lra_lu` above ~12 | inconsistent takes | level the individual clips before assembly |
| `lufs` at target, `lra_lu` below ~4 | over-compressed — the dynamics were flattened to hit the number | back the limiter off and accept a quieter integrated level |
| `true_peak_dbfs` above −1.0 | bed too loud, or limiter absent | lower the bed's `gain` |
| `lufs` above target | over-normalised | let the platform do it; do not pre-compensate |

**Hitting −14 LUFS is not the same as sounding good.** The target is a
normalisation reference, not a quality score, and it is trivially reachable by
brick-walling the mix — which removes exactly the transients that make speech
intelligible and a score feel like it has an arc. A film that lands at −17 LUFS
with its dynamics intact is a better deliverable than one at −14 that had them
compressed out. Read `lra_lu` and `lufs` together; neither means anything alone.

The fix is nearly always **upstream, at the voice**, not downstream at the
master. A limiter that fixes the number on a finished mix does it by crushing
the narration, which is the one element that must stay clear.

## What to do when it is genuinely unreachable

Report it. A film at −19 LUFS that says so is fine; a film at −19 LUFS that
claims −14 is a bug that will be rediscovered every time someone checks.

If the film is a Short, it matters less — Shorts are watched at whatever level
the phone is at, and the feed normalises aggressively. For a long-form episode
sitting between other channels' videos, close the gap at the voice stage.
