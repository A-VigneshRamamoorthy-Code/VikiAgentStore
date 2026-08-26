# Documentary rhythm

Where this style's timing, grade and fallbacks come from, and — just as
importantly — which findings were **rejected** and why.

The reference point is [ColdFusion](https://www.youtube.com/@ColdFusion), which
is the most-watched example of the thing this style does: a documentary built
almost entirely from stock footage and narration, with no presenter.

Every rule below is marked with how well it is evidenced. Rules marked
*verified* come from a primary source — usually the creator's own words.

---

## The five-second rule · verified

> "Personally, as a rule of thumb, no scene should last more than five
> seconds. The images themselves should tell most of the story. If a viewer
> turns off the sound, they should have a rough idea of what I'm talking about
> just by looking at the visual images. The scenes also shouldn't be
> overwhelming. For this I tend to use fades to lead the viewer smoothly
> between concepts."
>
> — Dagogo Altraide, [Tubefilter, 19 October 2017](https://www.tubefilter.com/2017/10/19/youtube-millionaires-cold-fusion-tv/)

That one paragraph sets `MAX_SHOT = 5.0` and explains why. Past five seconds a
stock clip has shown everything it has; it was shot by a stranger with no
knowledge of this film, and it has no more story to give.

`compile.py` therefore does not merely warn about a long hold, it **cuts away**
from it — see `add_cutaways()`. The split is only made if the beat has an
alternate query to cut to, so the second piece is a genuinely different clip of
the same subject. A beat with nothing to cut away to is reported and left
alone, because the alternative is showing the same footage twice, which reads
as a dropped frame.

Disable with `--no-cutaways` if the story really does want a long hold.

### The silent test

"If a viewer turns off the sound, they should have a rough idea of what I'm
talking about" is a *checkable* property, and it is the reason `ABSTRACT`
exists in the compiler. A shot whose query reduces to abstractions fails the
silent test by definition: nothing is on screen that means anything.

---

## Atmosphere, not text cards · verified

The hardest problem in this style is the beat with no photograph — "investors
grew nervous", "the strategy was flawed".

The researched answer is **not** what you would guess. ColdFusion does not stop
on a text card or a diagram. It cuts to atmosphere: city traffic at night,
defocused light, weather, crowds in motion — footage chosen to match the
*energy* of the line rather than its subject. The film keeps moving.

That is what `ATMOSPHERE` implements, keyed by the same mood the score uses.

### Why this does not break the honesty rule

The production designer's first rule is that a style never invents a picture,
and warns specifically against "a stock crowd standing in for a real one".
Atmosphere is not that, and the difference is worth being precise about:

- Cutting to a **specific** building, crowd or person under an abstract line
  claims something the story never said. That is forbidden, and still is.
- Cutting to **weather, traffic or bokeh** claims nothing at all. There is no
  proposition in a defocused light. A viewer reads it as mood because it *is*
  mood.

Every atmosphere shot is flagged `"atmosphere": true` in the storyboard and
raises a note, so a human can see at a glance which pictures are evidence and
which are mood. The style still says what it cannot shoot; it just no longer
stops the film to say it.

---

## Category-level matching · verified

Footage matches narration at the **category** level, not the instance level.
When ColdFusion says "Dropbox's servers", the picture is a data centre — not
*that* data centre.

This is worth knowing because it sets the standard the fetcher is held to. A
query does not need to find the literal object; it needs to find something in
the right genre. What is forbidden is the *wrong* genre — a beach under a line
about Silicon Valley — and footage that makes a specific false claim.

---

## The grade · partially verified

Sources agree ColdFusion's grade is **cool and desaturated** with lifted rather
than crushed blacks. That is the `reportage` grade.

They do **not** agree on teal-and-orange split-toning. Every source asserting it
also described it as a general convention of the genre rather than something
observed in a frame, so the warm-midtone half is deliberately **not**
implemented. A split-tone applied wrongly is visible on every shot of every
film, and the failure is silent — it just looks slightly off forever.

If you can confirm warm midtones from actual frames, the parameters to add are
`rm=0.03:gm=-0.01:bm=-0.02` in the `colorbalance` stage.

---

## Typography · verified

Display type is **Bebas Neue** — confirmed from the CSS that ColdFusion's own
site loads, not inferred by looking at frames:

```css
/* coldfusioncollective.com */
@import url(https://fonts.googleapis.com/css?family=Bebas+Neue);
font-family: "Bebas Neue", cursive; text-transform: uppercase;
```

It is an open-licence face, so `render.py` prefers it when installed and falls
back to the platform sans otherwise. It is not bundled. Bebas Neue has no
lowercase glyphs, which is consistent with the all-caps chips this style
already draws.

Body/label type on the site is Titling Gothic FB, which is licensed and
therefore not a dependency; Barlow Condensed and Oswald are close free
substitutes.

---

## Rejected: the 2.35:1 letterbox

Widely repeated, and **not implemented**, because it could not be verified.

Every source claiming ColdFusion letterboxes its videos throughout turned out
to trace back to the same unsourced assertion, and one source said the base
format is plain 16:9 with bars used only occasionally. Many documentary
channels letterbox the cold open and nothing else.

Bars are the single most visible decision in a frame. Shipping them on
inference would put a wrong, permanent, obvious signature on every film this
style makes — so 16:9 stands until someone measures actual frames.

**If you verify it, measure the video body, not the thumbnail and not the
intro.** Thumbnails are designed separately and prove nothing.

---

## Structure · measured, not implemented here

Act boundaries land at consistent fractions of runtime across six analysed
films: roughly **8% / 25% / 47% / 67% / 84%**, giving context → ascent →
inflection → consequence → synthesis, with each act running about 2:45–3:45.

This style does **not** implement that, and should not: the beat plan owns
structure, and it arrives here already written. It is recorded because it is
useful to whoever writes the beat plan — see the screenwriter and story-editor
skills, which is where a structural template belongs.

The same applies to the hook findings (first spoken word inside 2s, central
question by 0:45, the turn word at 10–25s) and to the audio findings
(narration around 150 wpm, 2–4s of music-only air at act boundaries, risers at
act boundaries only and never on every cut). Those belong to `screenwriter`,
`voice-booth` and `sound-designer` respectively.

One picture-side consequence *is* implemented: keyword chips are already
throttled, which keeps the opening clean of text overlays.
