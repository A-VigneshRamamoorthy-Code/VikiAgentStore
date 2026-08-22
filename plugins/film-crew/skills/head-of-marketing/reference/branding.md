# Channel branding: icon and banner

A new channel has no identity, and the first video arrives on a page with a
grey avatar. `brand.py` renders both assets from the same `publish.json` brand
tokens the video uses, so the channel and the film look like one thing.

```bash
python3 <skill>/scripts/brand.py .            # → out/channel_icon.png, out/channel_banner.jpg
python3 <skill>/scripts/upload.py branding .  # applies both
```

## Sizes and caps

| Asset | Size | Cap | Format |
|---|---|---|---|
| Icon | 800x800 | 4 MB | PNG |
| Banner | 2560x1440 | 6 MB | **JPEG** |

The banner must be JPEG. A 2560x1440 field of paper texture is about 5 MB as
PNG — close enough to the 6 MB cap that a slightly grainier variant fails, and
Studio's rejection does not say why. Check the file size before uploading, not
after.

## The banner safe area is the whole design

A banner is displayed at wildly different crops. Only the central
**1235x338** is guaranteed visible; TV shows the full 2560x1440.

Everything that carries meaning — wordmark, tagline, any label — belongs
inside that box. Two failures worth knowing:

- Timeline *ticks* fitted the safe area but their **labels** did not, so on a
  phone the design was sliced through the text.
- Ticks laid out on a fixed grid speared the tagline. Lay out decoration
  *after* measuring the text boxes, and suppress any that collide.

## Drawing a believable hand-drawn stroke

Per-point random jitter does not read as a marker; it reads as a sawtooth,
because the noise is at the same frequency as the sampling. Real wobble is
low-frequency: sum two or three sinusoids at random phase and amplitude along
the stroke.

A ring around a wide, short wordmark collapses into a thin lens and looks like
a mistake. Underline it instead.

## Studio's branding page

`/editing/images` redirects to `/editing/profile`. Page order is **Banner →
Picture → Name → Handle**.

All three file inputs share `id=file-selector`, so index order is the only way
to tell them apart — and index order is exactly what changes silently between
Studio revisions. Target the custom elements instead:

```
ytcp-banner-upload
ytcp-profile-image-upload
ytcp-video-watermark-upload
```

Playwright's CSS engine pierces shadow roots, which is what makes this work.
If you need to walk up from a matched node, remember `parentElement` returns
`null` at a shadow boundary — hop with `getRootNode().host`.

Each upload opens a crop dialog that must be confirmed before the change
registers. `ytcp-button#publish-button` stays disabled until something has
actually changed, so a disabled Publish button means the upload did not take.

## Verifying

The icon can be read straight from the public channel page. The **banner
cannot** — scraped HTML has no `c4TabbedHeaderRenderer` without JavaScript.
Use Studio's own device preview instead, which renders all three crops.
