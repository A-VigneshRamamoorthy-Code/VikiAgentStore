# Thumbnails

The thumbnail is judged at roughly **168 pixels wide** in a search result and
even smaller in a sidebar. Design for that size and it also works large; design
for the large version and it becomes mud.

There are two renderers. **Choose the one that matches the film.**

| | `thumbnail.py` | `thumb_doc.py` |
|---|---|---|
| Look | news debate: crimson band, real stills, `VS` burst | archive paper: parchment, drawn illustration, typed kicker |
| Built from | frames of the video | the film's own paper style artwork |
| Right for | argument shows, reactions, sport, verdicts | documentary, history, anything about real harm |

The debate style earns clicks on an argument show. On a film about people who
were killed it reads as tasteless — and a thumbnail that misrepresents the
video is the one click never worth having.

## The debate layout

```
+--------------------------------------------------+
|  BAND: two lines of heavy type, white on crimson |  ~36%
+--------------------------------------------------+
|                                                  |
|  live footage from the video, punchy grade       |  ~64%
|          (optional) VS burst / lightning         |
|                                       [WORDMARK] |
+--------------------------------------------------+
```

Why a full-width band rather than a side panel: at 168px the headline still
occupies a third of the area, it never overlaps a face, and a saturated red bar
is the strongest colour signal in a feed of mostly blue-grey stills.

Driven by `meta/thumbnail.json`:

```json
{
  "bg": "meta/frames/left.jpg",
  "bg_right": "meta/frames/right.jpg",
  "line1": "first line",
  "line2": "second line",
  "kicker": "small label",
  "vs": true,
  "out": "out/thumbnail.jpg"
}
```

Supplying `bg_right` splits the lower area into two stills with a `VS` starburst
between them.

## Two registers

Everything below the next section is the **text thumbnail**, which is right for
proceedings, comparisons and explainers. Long-form investigative documentary
uses a different and equally proven layout —
[the silent thumbnail](#the-silent-thumbnail) — where the text count is zero.
Pick the register before picking the layout.

## Rules

1. **Two lines maximum, four or five words each.** A third line is unreadable
   small.
2. **Use real frames from the video.** A split showing two people who never
   spoke to each other is a lie the video then fails to deliver. Take both
   stills from the *same exchange*.
3. **Faces should be large, cropped at the shoulders, and looking into frame.**
4. **Outlines must be hard, never blurred.** Stamp the glyph alpha in a ring of
   offsets. A soft drop shadow disappears entirely when downscaled to 168px.
5. **Test at 168px.** Downscale the finished file and look at it. If you cannot
   read it in under a second, rewrite the headline.
6. **Under 2 MB**, or YouTube rejects it outright. `thumbnail.py` enforces this.
7. **The thumbnail must not repeat the title verbatim.** Together they should
   deliver two pieces of information, not one twice.
8. **Choose the frame; never take the midpoint.** See below.
9. **A Short's thumbnail must survive a centre crop to 9:16.** See below.

## Choosing the frame

The background frame used to be the clip's midpoint. A midpoint is an arbitrary
instant, and a legislature broadcast spends much of its running time not
looking at anybody: wide shots of a half-empty chamber, the Chair's desk,
graphics, slates between items, and dissolves in and out of all of those.

A published batch of episodes came back with **no person in the picture at
all** — the frame that got grabbed was the episode's own branded intro card.
And because `_place_block` positions the headline against a detected face, a
frame with no face also lost its lower-third and left the text stranded across
the middle of the picture. One bad frame choice produced both defects.

`thumbframe.py` picks the frame instead of assuming it:

```bash
python3 <skill>/scripts/thumbframe.py VIDEO --start 6545 --end 6597 \
        --out meta/frame.jpg --json
```

It samples nine stills across the clip — skipping the first and last tenth,
where cuts and dissolves live — and scores each on whether a face is present
and large (68%), sharpness (17%) and exposure spread (15%). Scored against the
frame that actually shipped:

| Frame | Score | Face |
|---|---|---|
| the shipped intro card | **0.29** | none |
| what the scout picks from the same clip | **0.94** | 31% of frame height |

Sharpness rejects dissolves and motion blur; exposure spread rejects slates and
fades, which are a couple of flat colours and score near zero. A clip that
genuinely never shows a face still returns its best frame, flagged
`"face": false` so the caller can decide rather than being surprised.

Two things follow from this:

- **Never source the frame from the built episode.** Its opening seconds are
  branding by construction. Scout the raw footage.
- **With no face, the headline goes to the bottom**, where a broadcast
  lower-third belongs — not to a fraction of the height. A mid-height bar on a
  wide shot reads as a mistake.

## Shorts thumbnails and the portrait crop

A thumbnail is authored 16:9, but every portrait surface **centre-crops it to
9:16**. On a 1280×720 canvas that keeps a column just `720 × 9/16 = 405px`
wide — **under a third of the image**. Everything outside it is gone.

Left-aligned full-width text therefore falls almost entirely outside the
surviving column. A published batch rendered `மானியக் கோரிக்கை` as
`ரிக்கை`, with an empty red band beneath it, because only the last few glyphs
were inside the crop.

Pass `"portrait_safe": true` in the thumbnail spec for any Short. It:

- fits the text to the 405px safe column instead of the full canvas,
- **centres** it there rather than left-aligning, so the crop keeps the line,
- and, if the speaker is off to one side, zooms slightly and pans onto them so
  they are inside the column too.

Verify it the same way YouTube will — crop and look:

```python
im = Image.open(out); w, h = im.size
cw = int(h * 9 / 16); x = (w - cw) // 2
im.crop((x, 0, x + cw, h)).save("check_portrait.jpg")
```

If the headline is not fully readable in `check_portrait.jpg`, it is not
shipped. This is rule 5 applied to the crop that actually gets served.

## The silent thumbnail

The reference documentary — 24 million views — carries **no text at all**.
Measured from the image itself:

```
+--------------------------------------------------+
|  warm dark red  <-- gradient -->  cool dark blue  |
|                                                   |
|                              ^ small pale jet,    |
|                                upper right, tiny  |
|         RED SILHOUETTE                            |
|         falling figure,                           |
|         large, lower left                         |
|            grain + scratches over everything      |
+--------------------------------------------------+
```

| property | measured value |
|---|---|
| words of text | **0** |
| distinct subjects | 2 — one large, one small |
| palette | two complementary darks: `#112236` blue, `#441a1b` red |
| mean brightness | RGB 56/37/44 — very dark |
| rendering | flat silhouettes, no photography, no faces |
| texture | film grain and fine scratches across the whole frame |
| composition | strong diagonal; subject lower-left, counter-subject upper-right |

### Why zero text beats five words here

The title already says *The Search For D. B. Cooper*. A thumbnail repeating
"D.B. COOPER" spends the viewer's whole first glance telling them something
they just read. Spending it instead on **a man falling out of the sky** poses
the question the title only names.

### The rules for this register

1. **No text.** Not a small line, not a date. Zero.
2. **Exactly two elements**, at very different sizes. The size ratio *is* the
   drama — a tiny plane makes the fall enormous.
3. **Two complementary colours, both dark.** Warm subject against cool ground,
   or the reverse. Not a bright palette; the feed is bright, and dark reads as
   serious.
4. **Silhouettes, not photographs.** A silhouette is legible at 168 px where a
   face at that size is mush, and it makes no claim about who the person was —
   which matters when the whole film is that nobody knows.
5. **Grain over everything.** It reads as archival and hides the flatness.
6. **One diagonal.** The eye should travel from the large subject to the small
   one and back.

Use this register when the film is over ~15 minutes, the subject is unresolved,
and the title carries the naming. Use the text layout when the value is a
specific claim the viewer must read to want.

## The documentary layout

```
+--------------------------------------------------+
| [CASE FILE]                                      |
|  SIXTY                          ,--~~--.  smoke  |
|  HOURS                         /  hotel  \       |
|  ====                         |___________|      |
|  MUMBAI · 26 NOV 2008                            |
+--------------------------------------------------+
```

Headline left, illustration right, on the same parchment the film is drawn on
— so the thumbnail and the first frame are visibly the same object. A stamp
sits above the headline, a marker rule under it, a typed kicker below that.

Two rules are **enforced, not advised**, because both failures are invisible in
a full-size preview and fatal at 168px:

- **Cap height below 96px is refused.** Long headlines shrink until they are
  unreadable; the renderer stops instead.
- **Text overlapping the illustration is refused.** `_headline()` returns the
  widest right edge of the text, and `render()` compares it with the
  illustration's left edge. The fix is `headline_width` or `subject.x`, and the
  error message says so.

Both were added after a first render buried the "S" of `HOURS` and the whole
kicker behind the hotel — which looked perfectly fine until it was downscaled.

### When the right answer is no text at all

A good deal of the documentary work that performs best carries **no title on
the thumbnail** — the image makes the whole claim and a headline only competes
with it for the same second of attention. `"layout": "art-only"` centres
`subject` and skips the headline, kicker and both enforced rules above, which
no longer have anything to measure.

```jsonc
{ "seed": 19, "layout": "art-only", "stamp": "UNSOLVED",
  "subject": { "fn": "parachute", "w": 620, "h": 660 } }
```

It is selected by name rather than inferred from an absent `headline`, so
misspelling the key still fails loudly instead of silently shipping a picture
with the title missing. `stamp` and `tape` still apply; an art-only spec with
no `subject.fn` is an error, because then there would be nothing on it.

## Confirming what YouTube actually serves

Rendering a thumbnail and attaching it are two different things, and the second
one fails silently. `set_input_files` succeeds, the log says "thumbnail
attached", and YouTube serves an auto-generated frame instead — on a
documentary, a random mid-scene still with a caption stuck across it.

Studio's edit page is not proof either; it shows the *pending* selection.

Compare against the CDN, cache-busted, because that is what a viewer sees:

```
https://i.ytimg.com/vi/<id>/maxresdefault.jpg?bust=<timestamp>
```

Downscale both it and the local file to 160x90 and compare mean absolute
difference — identical files land under 1.0. Use `maxresdefault` only;
`hqdefault` is cropped to 4:3 and never matches. Allow a minute for
propagation. `upload.py thumbnail` re-applies and polls this automatically.

## The CoreText whitespace trap

CoreText **trims leading and trailing whitespace from each rendered segment**.
Composing `" VS "` and expecting padding produces `"VS"` jammed against its
neighbours. Add spacing in **pixels** when positioning, never as spaces in the
string.

This also means measuring a string with spaces and then rendering it gives two
different widths. Measure what you actually render.

## Non-Latin text

All type goes through `ct_text.py` (CoreText). Pillow's default text stack has
no HarfBuzz here, so Tamil, Devanagari, Arabic and similar scripts render as
unshaped, broken glyph sequences — conjuncts do not form and vowel signs land in
the wrong place. This is also why `ffmpeg`'s `drawtext` filter must not be used
for these scripts.

The trade-off: **rendering is macOS-only.**
