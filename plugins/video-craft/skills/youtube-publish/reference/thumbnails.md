# Thumbnails

The thumbnail is judged at roughly **168 pixels wide** in a search result and
even smaller in a sidebar. Design for that size and it also works large; design
for the large version and it becomes mud.

There are two renderers. **Choose the one that matches the film.**

| | `thumbnail.py` | `thumb_doc.py` |
|---|---|---|
| Look | news debate: crimson band, real stills, `VS` burst | archive paper: parchment, drawn illustration, typed kicker |
| Built from | frames of the video | the film's own paper-explainer artwork |
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
