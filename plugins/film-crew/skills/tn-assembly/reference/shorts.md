# Shorts

A Short is a **trailer**, not a highlight reel. Its job is to reach people who
have never heard of the channel and send them to the long-form video.

## Framing

Chamber footage is a wide 16:9 shot of a room, and a 9:16 Short keeps only
about a third of that width. The original approach avoided the problem by
scaling the source to fill the frame, blurring and darkening it as a
background, and overlaying the real footage at full width in the middle.
Nothing was cropped away.

**That is no longer the default, and the reason is not technical.** A blurred,
mirrored backdrop with a letterboxed strip in the middle reads as a repost —
it is what an account that did not shoot the footage does to someone else's
video. It signals second-hand material on a feed where the first impression is
the whole impression.

The default is now `fill`: scale to cover 1080×1920 and crop. But the original
objection was correct and still applies — a *fixed centre* crop removes the
speaker whenever the feed is not centred on them, which in a chamber wide shot
is most of the time.

So the crop is aimed rather than centred. The face sweep already records a
horizontal position for every close-up it sees, and `subject_focus()` averages
the ones falling inside the Short to place the crop window on the person
speaking. It falls back to centre when there is no face data, and clamps to
0.15–0.85 so the window always stays inside the frame.

Averaging rather than tracking is deliberate. A crop that follows a face frame
by frame looks like a handheld camera; a Short is brief enough that one
well-chosen fixed position reads as intentional framing.

| Setting | Effect |
|---|---|
| `shorts.framing` | `fill` (default) or `blur` for sources that genuinely cannot be cropped |
| `shorts.focus_auto` | `true` (default) — aim the crop from face data |
| `shorts.focus_x` | manual 0–1 horizontal position, used when `focus_auto` is false or no faces were found |

Face data only exists if `vip.enabled` is on and `faces.py --scan` has run.
Without it every Short falls back to a centre crop, which is the case the
original blur approach existed to avoid — so on a session with no face scan,
check the framing before publishing.

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

**Let the moment decide.** A Short runs as long as the exchange it contains and
no longer — there is no editorial virtue in a fixed target, and truncating a
90-second argument at some round number cuts off the payoff that made it worth
publishing.

The only hard number is the platform's: **180 seconds**. Past that YouTube
publishes the upload as an ordinary video and it never enters the Shorts feed.
That ceiling lives in `config.SHORTS_HARD_MAX`, `shorts.max_len` defaults to it,
and `doctor` rejects a project that configures more.

`shorts.min_len` (default 20s) is a floor, not a target: it stops a three-second
blip being promoted into a Short, growing the window symmetrically if a
candidate comes in under it.

Shorter still tends to retain better, so if a moment genuinely ends at 30
seconds, let it end — but that is a judgement about the clip, not a rule the
pipeline imposes.

Like long-form clips, Short boundaries are snapped to speech pauses, so they do
not begin or end mid-word. Snapping uses the **Shorts** length band; earlier
versions fell back to the longform band (34–95s), which silently refused every
candidate boundary for a short clip and shipped it unsnapped.

## How a Short is actually measured

Two numbers, and they mean different things:

| Metric | Counted when | Use it for |
|---|---|---|
| **Views** | The Short starts to play — including scroll-bys and loops | Reach, nothing else |
| **Engaged views** | "the viewer stayed to watch past the initial seconds, **and does not include any loops**" | Whether the thing actually worked |

That sentence is YouTube's own, from the Partner Program post. Two consequences
the pipeline depends on:

1. **Judge a Short by engaged views, not views.** A Short with a big view count
   and few engaged views was scrolled past, not watched. The first seconds
   failed, and the fix is the hook, not the distribution.
2. **A loop seam earns no ranking bonus.** Editing the last frame to flow back
   into the first is a *legitimate craft choice* — it makes a rewatch pleasant —
   but loops are explicitly excluded from engaged views, so a seam cannot be
   sold as a metrics tactic. Do it because the ending rhymes, not because it
   farms replays.

The two-stage shape also says where to spend effort: the first seconds decide
whether a view becomes an engaged view, and nothing later in the clip can
recover a viewer who never got past them.

Source: [Qualified watch hours and Shorts views](https://blog.youtube/news-and-events/youtube-monetization-qualified-watch-hours-shorts-views/) `[PLATFORM]`

## Publishing cadence

**Publish one Short at a time, spaced by hours.** This matters more than
anything else in this file.

Of nine Shorts published in a single day, exactly one was ever given a Shorts
feed test batch — it took 1,325 views, while its three siblings, uploaded one
to two minutes behind it with identical styling, took 2, 3 and 3. One Short
checked directly had received a single feed view in its entire lifetime.

The platform appears to test roughly one Short per channel at a time. A queue
emptied in an afternoon is a queue mostly thrown away, and the unshown ones are
stale by the time you notice. A session's worth of Shorts is a **week** of
publishing.

Judge a Short on its first 48 hours; after that the test batch is spent and
editing it will not restart anything. Full measurements in
`reference/distribution.md`.

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
5. **One Short per publish window.** Never release a batch; see *Publishing
   cadence* above.
6. **Link the parent by video id, and read the link back.** Matching the
   episode by title silently attaches the wrong one.
