# Thumbnails

The thumbnail is judged at roughly **168 pixels wide** in a search result and
even smaller in a sidebar. Design for that size and it also works large; design
for the large version and it becomes mud.

There are two renderers, and a third register with none — the photographic
composite below is assembled per film, because what it composites is whatever
that film's cleared library happens to hold. **Choose the one that matches the
film.**

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

## Three registers

Pick the register before picking the layout.

| register | text | built from | right for |
|---|---|---|---|
| **text** — the sections below | 2 lines | frames of the video | proceedings, comparisons, explainers |
| [**silent**](#the-silent-thumbnail) | none | flat drawn silhouettes | long-form documentary, unresolved subjects |
| [**photographic**](#a-photographic-register) | a hook, optionally a tail | cut-out stock over a graded plate | the same, when the brief asks for a click rather than a mood |

The silent and photographic registers answer the same brief and differ in
nerve: one poses the question quietly, the other builds an impossible picture
out of real photographs. Both beat a headline that restates the title.

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
10. **Never put a recognisable stock face on a crime.** The licence forbids it.
    See below.

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
surviving column. Across one session **43 of 43 published Shorts** were
affected: `மானியக் கோரிக்கை` was served as `ரிக்கை`, and the second line
was outside the crop altogether, leaving a **red band with nothing in it** —
which reads to a viewer not as truncation but as a broken, empty title card.
Both complaints, one cause.

Pass `"portrait_safe": true` in the thumbnail spec for any Short. It:

- fits the text to the 405px safe column instead of the full canvas,
- **centres** it there rather than left-aligning, so the crop keeps the line,
- and, if the speaker is off to one side, zooms slightly and pans onto them so
  they are inside the column too.

Verify it the same way YouTube will — crop and **look at the image**:

```python
im = Image.open(out); w, h = im.size
cw = int(h * 9 / 16); x = (w - cw) // 2
im.crop((x, 0, x + cw, h)).save("check_portrait.jpg")
```

Do not substitute a pixel metric for looking. Measuring ink coverage inside
the band scored 42 of these 43 broken thumbnails as "readable", because the
surviving fragment `ரிக்கை` is still ink — the check cannot tell a word from
the end of a word. A contact sheet of a dozen crops showed the defect
instantly. If the headline is not fully readable in `check_portrait.jpg`, it
is not shipped. This is rule 5 applied to the crop that actually gets served.

### Compose for the column, not just the text

`portrait_safe` rescues the *headline*. It does nothing for the picture, and a
composition whose subject sits off-centre loses the subject instead of the
words. Treat `x = 437..843` as the whole canvas: put the subject on its centre
line, stack the other elements above and below rather than beside, and let the
outer thirds carry only plate and texture.

Done that way the 16:9 render survives intact. Measured against the live
posters of three Shorts built this way: the safe column came back at **5.2**
mean absolute difference — JPEG noise — while the discarded wings scored
**14.8**. Nothing that mattered was in the wings.

Two consequences worth planning for:

- **Keep graphic elements inside the column too.** A redaction bar sized to the
  figure ran 14px past the crop edge and had to be pulled back; at feed size a
  bar clipped by the frame edge reads as a rendering fault.
- **A series of Shorts should differ.** Three identical compositions with one
  word changed look like an upload error on the channel's Shorts shelf. Vary
  the element positions and any random seed per Short and keep the palette, so
  they read as a set rather than as duplicates.

## Casting a person as the wrongdoer

A thumbnail about a crime wants a face on it, and the nearest face is whichever
stock model the film already cleared. That is a licence breach, not a shortcut.
Pexels, Unsplash and Pixabay all carve out **identifiable people**: their
footage may not be used in a way that shows the person in a bad light, implies
illegal activity, or implies endorsement. Cleared for the film, not cleared to
be the hijacker.

The register will not stop this, because it records assets and the restriction
attaches to the *use*. Marketing is where it bites, so it has to be caught
here.

**Remove the likeness, keep the photograph.** Crushing everything below a
highlight rolloff leaves a rim-lit silhouette: real hair, a real lapel, a real
collar — genuine photographic contour that no drawn shape matches — and nobody
identifiable in it. Measured settings that worked on a night-sky plate:

```python
keep = np.clip((lum - 0.46) / 0.54, 0, 1) ** 1.4   # rim only
body = (0.074, 0.090, 0.131)                        # not black
rim  = (0.70, 0.78, 0.90)
```

Two things this gets wrong on the first attempt:

- **Do not take the body to black.** Against a dark sky the figure disappears
  entirely at 168px. Lift it until it separates from the plate, then check at
  168px — the value that looks right at full size is too dark.
- **A redaction bar over the eyes must contrast with the silhouette, not the
  background.** Black-on-black reads as nothing; red reads instantly and doubles
  as the palette's one warm accent.

This also satisfies silent-thumbnail rule 4 for a different reason — it makes
no claim about who the person was, which is the point when the film's subject
is that nobody knows.

## A photographic register

The silhouette register above is drawn. Between it and the debate layout sits a
third, which is what a "flashy, high-CTR" brief usually means: **real cut-out
photography composited into an impossible picture** — a jet, a falling figure,
banknotes coming out of the sky — over a graded plate from the film's own
cleared library.

It earns the click the same way the silent register does, by posing the
question, but it survives a title across the bottom because the elements are
photographic and separate cleanly.

- **Cut out with `cutout.swift`, not by hand.** It wraps Vision's
  `VNGenerateForegroundInstanceMaskRequest` and is clean on people and
  aircraft. On-device, so no footage leaves the machine. macOS 14+:

  ```bash
  swiftc -O -o cutout <skill>/scripts/cutout.swift
  ./cutout plane.png out/plane
  # out/plane.png   every instance together
  # out/plane_1.png … one file per instance
  ```
- **It groups touching objects into one instance.** A fan of banknotes comes
  back as a single mask, so individual notes cannot be obtained this way. For
  anything that *is* a rectangle, crop the real texture and warp it — a crop of
  a real note beats a guessed matte.
- **Grade the cut-outs to the plate or the composite falls apart.** Push the
  plate cool in shadow and warm in highlight, then bring each element to it:
  the aircraft desaturated and cool (`sat=0.60`), the notes barely saturated
  (`sat=1.22`). Reaching for `sat=1.75` on the notes produced radioactive lime
  — at 168px the colour has to be *nameable*, not loud.
- **Position by the bounding box of the cut-out, never by the source frame.**
  A figure placed by frame coordinates ran off the bottom of the canvas.

### Fitting a full title under a hook

Rule 7 says the thumbnail must not repeat the title, and it is right. When it
is overridden anyway — a series where the title *is* the hook — do not shrink
one line until both fit. Set the hook at the size it needs and render the rest
as a **secondary line at ~55% of it**, fitted afterwards:

```
HE STOLE $200,000
~THEN JUMPED INTO THE NIGHT
```

The hook stays legible at 168px and the tail is there for anyone who reads it.
Keep both left- or centre-aligned: YouTube stamps the **duration badge over the
bottom-right corner**, so a line that ends there loses its last words.

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

### A Short is never served as uploaded

The comparison above is wrong for a Short, and wrong in the direction that
matters: it reports a perfectly good poster as rejected.

YouTube does not serve a Short's thumbnail as given. It centre-crops the 9:16
out of it and rebuilds a 16:9 frame around that from a **blurred enlargement of
itself**. So `maxresdefault` for a Short is part your artwork and part
YouTube's filler, and a whole-frame mean is measuring mostly filler.

The tell is that the number never moves and is the same for every Short in the
batch. Three different pictures scored **10.2 overall with an identical 38.86
worst block** — three different images cannot fail identically, so that is a
systematic difference, not three rejections. Cropping to the safe column first
and re-comparing gave **3.00 / 3.06 / 3.17**.

Two further things to know before believing either number:

- **Raise the local threshold for a Short.** Both sides have now been resampled
  twice, and the loudest thing on these thumbnails is white text hard against
  black, whose edges disagree on resampling alone. Correct posters scored 10.4,
  11.4 and 16.6 in the worst block — the worst of them sitting exactly on the
  glyphs of "THE JUMP", confirmed by zooming into the block. A genuinely wrong
  poster scored 38.9. Anything around 24 separates them.
- **`oardefault.jpg` is not yours and never will be.** That is the 1080x1920
  portrait poster used inside the immersive Shorts player, and YouTube
  generates it from the video frames. It stays an auto-generated still no
  matter what you attach. Custom art appears in search, the channel's Shorts
  shelf and subscriptions — which is where the click comes from.

The check that settles it is not a number at all: open
`youtube.com/@channel/shorts` and look at the shelf.

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
