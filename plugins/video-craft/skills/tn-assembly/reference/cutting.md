# Cutting: sync and boundaries

Two defects that both look like sloppy editing but have precise causes.

## The desync trap

Cutting a section with

```bash
ffmpeg -ss <t> -i <url> -t <d> -c copy out.mp4
```

snaps the **video** back to the nearest preceding keyframe, while the **audio**
starts exactly at the seek point. On a webcast with sparse keyframes the
measured result was the picture running **5.00 seconds behind the sound**.

What makes this dangerous is that it is undetectable by inspection:

- Both streams report `start_time` 0 in the container.
- Durations match.
- `ffprobe` shows nothing unusual.

The only way to find it is to locate each stream on the **source** timeline
independently, by correlation. That is what `checks.py` does.

### The fix

```bash
yt-dlp -f "137+140" \
  --download-sections "*<start>-<end>" \
  --force-keyframes-at-cuts \
  --merge-output-format mp4 -o out.mp4 <url>
```

`--force-keyframes-at-cuts` re-encodes around the cut so both streams begin on
the requested frame.

Measured after the fix: **+0.04 s** on the raw clip, **+0.06 s** on the final
render. Costs roughly 40 seconds to fetch a 60-second 1080p section — perfectly
acceptable, since only the planned seconds are ever downloaded.

Format `137+140` is 1080p video plus m4a audio. Override with
`source.format` in `project.json`.

### Verify after every cutting change

```bash
python3 checks.py <project> <clip.mp4> <expected_source_start_seconds>
```

It reports where each stream actually landed and a verdict. Anything beyond
±0.35 s is a failure. Exit code is non-zero when out of sync, so it can gate a
build.

## Boundary snapping

A fixed window slices through the middle of a sentence, which is the single
most obvious sign of an automated edit.

`boundaries.py` uses `silencedetect` to find every pause in a padded window
around the target, then:

- **In-point** = the **end** of a silence, i.e. the moment speech resumes.
- **Out-point** = the **start** of a silence, i.e. the moment speech stops.

Candidate pairs are scored:

```
score = min(in_pause, 2.0) + min(out_pause, 2.0)
        − 0.05 × (|in − target_in| + |out − target_out|)
```

This prefers a **strong, natural pause** over one that merely sits closest to
the target, while still penalising drift. Pairs outside the length limits are
rejected outright.

### Settings

- `noise_db` default **−38 dB**. A debating chamber floors around −24 to −26 dB
  mean, so −38 dB cleanly separates room tone from speech. A hotter or quieter
  mix needs this retuned — set `audio.noise_db` in `project.json` rather than
  editing the script.
- `min_silence` default **0.30 s**. Shorter gaps are breaths, not boundaries.

### When there is no boundary

If no valid pair exists, `snap()` returns the **original** points with
`snapped: false` and a reason. That is deliberate: a clip that must cut
mid-sentence is honest, whereas silently stretching it somewhere arbitrary
produces a clip that does not contain what the plan says it does.

Preview every planned clip's snapping without downloading anything:

```bash
python3 boundaries.py <project>
```

## Audio sample rate

`loudnorm` **upsamples internally** — 96 kHz was observed here — and the result
is muxed at that rate unless corrected. Always chain `aresample=48000` and pass
`-ar 48000`:

```
-af "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000" -ar 48000
```

`I=-14` LUFS matches YouTube's normalisation target, so the platform leaves the
audio alone.

## Concatenation

The concat demuxer copies streams without re-encoding and produces a broken
file if they differ. Every segment — including the intro and outro stings —
must be normalised to identical resolution, frame rate, SAR, sample rate and
channel count **before** concatenation. `build.py`'s `normalise_sting()` exists
for this: stings usually have no audio track at all, so a silent one is
generated for them.
