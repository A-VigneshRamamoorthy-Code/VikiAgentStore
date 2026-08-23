# Distribution: what actually happened to the first fourteen videos

The first session published under this skill — a 7h52m sitting cut into 5
episodes and 9 Shorts — produced one video with 1,325 views and thirteen with
between 0 and 9. This document records what the analytics actually said,
because the conclusion is the opposite of what everyone assumed at the time.

Every number below was read from Studio analytics, not inferred.

## The headline: long-form is invisible on a cold channel

The best-performing episode had **ten impressions**. Ever.

| Metric | ep04 (best episode) |
|---|---|
| Impressions | **10** |
| Impressions CTR | **20.0%** |
| Views | 5 |
| Unique viewers | 1 |

A 20% click-through rate is *excellent* — YouTube's own guidance puts typical
at 2–10%. The thumbnail and title were doing their job on every one of the ten
occasions they were shown. There were only ten occasions.

**This kills the natural assumption.** When a video gets no views the instinct
is to rewrite the title, re-cut the thumbnail, and stuff the tags. On this
channel that would have been optimising a step that was never the bottleneck.
The videos were not being rejected by viewers; they were not being *offered* to
viewers.

A new channel has no subscriber base to seed browse, no watch history for the
suggested-video graph to attach to, and no authority to rank in search. Those
are the only three ways long-form gets distributed. All three were empty, so
long-form got approximately zero impressions regardless of its packaging.

## The exception: Shorts get a free test batch

One Short, `sh01`, got **1,325 views, 31 likes and +2 subscribers**, and
**99.5% of those views came from the Shorts feed**.

The Shorts feed does not require authority. It gives essentially any upload a
small test audience and then decides. That is the *only* distribution mechanism
on the platform that pays out to a channel with no history — which is why one
Short outperformed all five episodes combined by a factor of about a hundred.

The shape of the view graph matters as much as the total: a single sharp spike
across day 0–1, then flat. That is one test batch being spent. It was not
"picked up by the algorithm" in an ongoing sense; it was tested once, performed
well (2.3% like rate), and the wave ended.

**Therefore: on a channel without an audience, Shorts are not promotion for the
episodes. They are the product.** The episodes are what the Shorts convert
*into*, once there is anyone to convert.

## The cadence finding

All nine Shorts and their gaps:

| id | published | gap | length | views |
|---|---|---|---|---|
| sh01 | 03:45:51 | — (first ever) | 58s | **1325** |
| sh02 | 03:48:40 | +2m | 42s | 2 |
| sh03 | 03:51:33 | +2m | 39s | 3 |
| sh04 | 03:52:47 | +1m | 45s | 3 |
| sh05 | 16:52:34 | +779m | 62s | 4 |
| sh07 | 16:53:55 | +1m | 61s | 4 |
| sh09 | 16:55:13 | +1m | 61s | 2 |
| sh06 | 18:13:35 | +78m | 75s | 5 |
| sh08 | 23:02:05 | +288m | 102s | 9 |

Two things fall out.

**Only one Short was ever published alone.** Every other upload had a sibling
landing one or two minutes later. `sh09`, checked directly, had received *one*
single Shorts-feed view in its lifetime — it was never given a test batch at
all.

**Views track the gap.** 288 minutes → 9 views. 78 minutes → 5. One to two
minutes → 2 to 4. The correlation is weak in absolute terms because every
number is tiny, but it points the same direction throughout, and it is
consistent with the platform testing roughly one Short per channel at a time.

**Length is not the variable here.** The 61–102s clips were all valid Shorts —
YouTube's ceiling has been 180s since October 2024 — and `sh09` at 61s did draw
Shorts-feed traffic, so they were being treated as Shorts. The four *shortest*
clips (39–45s) include three of the worst performers. Nothing in this data
supports trimming clips to hit a number.

### Be honest about the confound

`sh01` was also the channel's **first Short**, which plausibly earns a larger
new-channel test allocation on its own. Spacing and first-ever-ness are
entangled here and this session cannot separate them.

What *is* separable, and worth knowing:

- **It was not the metadata.** `sh01` was retitled to the "improved" format
  *after* it had already earned its 1,325 views, and the retitle revived
  nothing. `sh02`–`sh04` shipped within seven minutes of `sh01` carrying the
  same styling, hashtags and hook treatment, and got 2–3 views each.
- **It was not the thumbnail.** Shorts are served from the feed, not from a
  thumbnail grid; and on the long-form side CTR was 20%.
- **It was not conversion.** 2.3% like rate and +2 subscribers on the one video
  that was actually shown to people.

The failure was distribution, at every level, and only one lever in this
session's data moved it.

## What to do instead

1. **Publish Shorts one at a time, spaced by hours, not minutes.** One per
   day is a reasonable default. Never empty a nine-Short queue in an afternoon
   — eight of them will never be tested, and they are then stale.
2. **Treat the Shorts queue as a schedule, not a batch.** A session yields a
   week of uploads. `plan.py` producing N Shorts is not an instruction to
   publish N Shorts today.
3. **Publish the episode first, then drip its Shorts**, so every test batch
   that does land has somewhere to send people.
4. **Do not respond to a flat video by rewriting its metadata.** Read
   *impressions* first. Near-zero impressions with a healthy CTR means the
   packaging is fine and the channel has no distribution — a different problem
   with a different fix. Rewriting a title that was never shown to anyone
   changes nothing, and re-uploading thumbnails burns a hard daily quota
   (see `reference/publishing-limits.md`).
5. **Judge a Short in its first 48 hours.** The test batch is spent by then.
   A Short sitting at single digits after two days was not shown, and no
   amount of editing will restart it.

## Where the effort actually belongs

Ranked by measured return in this session:

| Effort | Return |
|---|---|
| Getting a Short into the feed at all | ~1,325 views |
| Everything else combined | ~40 views |

Thumbnail polish, title formulae, tag research and description SEO all operate
downstream of an impression. Until the channel earns impressions, they are
rounding errors. That is not an argument for shipping sloppy packaging — it is
an argument for not spending a day on packaging while the distribution problem
goes unexamined.
