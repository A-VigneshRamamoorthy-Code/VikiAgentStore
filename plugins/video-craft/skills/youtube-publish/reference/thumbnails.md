# Thumbnails

The thumbnail is judged at roughly **168 pixels wide** in a search result and
even smaller in a sidebar. Design for that size and it also works large; design
for the large version and it becomes mud.

## The layout

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
