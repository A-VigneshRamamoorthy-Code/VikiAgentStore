# Shorts

A Short is a **trailer**, not a highlight reel. Its job is to reach people who
have never heard of the channel and send them to the long-form video.

## Framing

Chamber footage is a wide 16:9 shot of a room. A centre crop to 9:16 throws away
whoever is speaking, which is the only thing worth showing.

`shorts.py` instead scales the source to fill 1080×1920, blurs and darkens it as
a background, then overlays the **real footage at full width** in the middle.
Nothing is cropped away, and the padding reads as a deliberate frame rather than
as letterboxing.

## Structure

| Seconds | What happens |
|---|---|
| 0.0–2.8 | Hook card burned **over** moving footage |
| 2.8–end | The moment, uninterrupted |
| last 3.0 | CTA naming the long-form video |

The hook is composited over the footage rather than played before it. Vertical
feeds are swiped, not browsed: if the first frame is a static title card, the
viewer is already gone. Motion buys the two seconds needed to read the claim.

## Text rendering

Text is composited as **CoreText-rendered PNG cards**, not with ffmpeg's
`drawtext`. Two reasons, both hard blockers:

1. `drawtext` has no complex-script shaping. Tamil, Devanagari and Arabic come
   out as unshaped glyph sequences — conjuncts do not form.
2. Many ffmpeg builds ship without the filter at all. The build used here has
   `overlay` but no `drawtext`.

Shorts are overwhelmingly watched muted, so burned text is not optional.

## Routing back to the long-form

Every planned Short records a `parent` episode id. Use it:

- Name the episode in the CTA card.
- Link it in the first line of the description.
- Publish the Short **after** the long-form is live, or the traffic has nowhere
  to land.

A Short that does not route viewers anywhere converts nothing. This is the whole
reason `plan.py` assigns a parent — falling back to the nearest episode by
timeline position when a moment did not itself make an episode.

## Selection

`plan_shorts()` takes clashes first, then the strongest remaining moments, up to
`shorts.max_count` (default 6). Moments within 30 seconds of one another are
deduplicated so two Shorts never show the same exchange.

A confirmed clash **always** gets a Short. It is the single most watchable thing
a legislature produces.

## Length

20–58 seconds (`shorts.min_len` / `max_len`). Staying under 60 seconds keeps it
eligible as a Short. Shorter is usually better: one moment, one claim.

Like long-form clips, Short boundaries are snapped to speech pauses, so they do
not begin or end mid-word.

## Output

`out/shorts/<id>.mp4` — 1080×1920, 30 fps, AAC 48 kHz, loudness-normalised to
−14 LUFS, `+faststart`.

## Rules

1. **One moment per Short.** Two claims sell neither.
2. **Never a Short that is only a title card.** Lead with footage.
3. **Do not repost the same moment** as several Shorts — it is suppressed as
   duplicate content.
4. **The hook must be true.** The same confirmation rule as everywhere else: if
   the clash is unconfirmed, the hook cannot call it a fight.
