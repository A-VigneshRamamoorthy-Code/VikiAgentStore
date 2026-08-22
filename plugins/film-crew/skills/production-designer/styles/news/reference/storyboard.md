# Storyboard reference — `news`

What `compile.py` writes and `render.py` reads. You are meant to **edit the
storyboard between the two**; that is where the design work happens.

## Top level

| field | meaning |
|---|---|
| `schema` | `1` |
| `style` | `"news"`. The renderer refuses a storyboard belonging to another style. |
| `title` | used for the opening title card |
| `seed` | shifts the generated plate colours; any integer |
| `narration` | copied from the beat plan. **This is the film's clock.** |
| `output` | `width`, `height`, `fps`, `crf`, `preset`, `path` |
| `brand` | see below |
| `graphics` | the list, in time order |
| `hooks` | carried through for the editor cutting Shorts; unused when rendering |

## `brand`

| field | default | meaning |
|---|---|---|
| `name` | the plan's `channel` | up to 4 alphanumerics become the bug |
| `accent` | `#bb1919` | headline bar, astonisher, straps, stings |
| `bar` | `#f2f0eb` | kicker bar and list items |
| `ink` | `#111111` | text on `bar` |
| `chip` | `#3d3d3d` | the location chip |

Change these and the whole film re-brands. Nothing else in the style hardcodes
a colour.

## Timing grammar

Every `at` and `until` is one of:

| form | means |
|---|---|
| `"l4"` | when narration line `l4` starts |
| `"l4.end"` | when it stops |
| `"l4+0.25"` / `"l4-0.25"` | offset in seconds from that point |
| `12.5` | an absolute second, used for "the end of the film" |

Pinning to lines rather than seconds is the point: re-record a line at a
different length and every graphic after it moves with it.

`compile.py` sets `until` on every full-width graphic so they tile the timeline
with no gap and no overlap. If you edit one by hand, keep that property — the
contact sheet will show you the moment you break it.

## Graphics

All of them take `id`, `kind`, `at`, `hold`, `until`, `emphasis`, `safe` and
`plate`. `hold` is only used when `until` is absent.

`plate` is `{"kind": "footage"|"still"|"graphic", "hint": "..."}`. The renderer
draws a neutral graded field from the hint; it never fabricates the thing the
hint describes. Swapping in real footage is a job for the editor.

| `kind` | extra fields |
|---|---|
| `headline` | `kicker`, `headline` |
| `astonisher` | `figure`, `caption`, `kicker` |
| `namestrap` | `name`, `role` |
| `locator` | `place` |
| `split` | `left`, `right` |
| `bullets` | `items` (up to 4), `kicker` |
| `callout` | `mark` (`circle`\|`box`), `label` |
| `sting` | `label` |

### Which ones are exclusive

`headline`, `astonisher`, `split`, `bullets` and `namestrap` take the screen —
only one is up at a time. `locator` is an **overlay**: the place stays in the
corner underneath whatever else is showing, until the report moves somewhere
else. `callout` and `sting` sit on top.

## Frame shapes

`compile.py --aspect` writes the matching `output`:

| aspect | pixels |
|---|---|
| `16:9` | 1920 × 1080 |
| `9:16` | 1080 × 1920 |
| `1:1` | 1080 × 1080 |

Chrome scales off the **short** edge, so the bug and the chip do not collide on
a vertical frame, and headlines wrap to a second line rather than shrinking
into illegibility. Check a vertical cut on its own contact sheet regardless —
what fits at 16:9 routinely does not at 9:16.
