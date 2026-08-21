---
name: youtube-publish
description: >
  Packages a finished video for YouTube and publishes it: writes the title,
  description, chapters and tags for search, renders a click-worthy 1280x720
  thumbnail, renders channel intro and outro stings including a subscribe-and-
  bell animation, lints everything against YouTube's hard limits, then uploads
  through Studio and verifies what actually went live. Handles bilingual
  metadata so a video in one language is still discoverable in another. Channel,
  brand and language all come from a project file, so it works for any channel
  and any video. Use when asked to upload to YouTube, write a video title or
  description, optimise a video for YouTube SEO or search, make a thumbnail, or
  publish and verify a video.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "1.0.0"
---

# YouTube Publish

Everything between "the video is rendered" and "the video is live and
findable". Nothing here knows what the video is about, so any project can use
it.

## Non-negotiables

1. **`meta/youtube_metadata.json` is the only file the uploader reads.** A
   generator that writes anywhere else uploads stale metadata with no error at
   all. This has already shipped a wrong title once.
2. **Confirm the active channel before uploading.** A Google login usually owns
   several similarly named brand accounts and Studio lands on whichever was
   last active. Match the handle exactly; refuse otherwise.
3. **Search reads text, never audio.** Every concept a viewer might type must
   appear in the title, description or tags — and in *their* language, not only
   the spoken one.
4. **Respect the caps before uploading, not after:** title 100 chars,
   description 5000, all tags together 500, thumbnail 2 MB. Studio reports the
   tag overflow only as "Cannot save until errors are resolved".
5. **Upload private, verify, then publish.** Studio's own visibility field
   reads "Pending" while processing; confirm privacy from outside.
6. **Never kill the browser process.** Always close the context, or the
   signed-in session is destroyed.
7. **Wait for the transfer, never for the Done button.** Studio enables Done
   and reports the video as saved while the file is still uploading — the
   transfer runs in the background *of that tab*. Closing the browser then
   abandons it and leaves a draft frozen at 12% with flawless metadata, which
   is exactly what makes it convincing. `upload` now blocks on the progress
   label until it stops saying "Uploading". A draft stuck mid-transfer cannot
   be resumed; cancel it and upload again.
8. **Set text with one `insert_text`, not per-character typing.** A 4,400-char
   description typed at 6 ms/char holds focus for half a minute, and Studio
   will steal it mid-way, leaving a silently truncated description. Read the
   value back and check the length.
9. **Navigate Studio in a fresh tab.** Its router silently rewrites any
   navigation issued from a tab that already rendered another Studio route, so
   `goto` from the dashboard lands back on the dashboard — three retries in a
   row, identically. A new tab is always a first navigation and always lands.
10. **Verify artwork from the CDN, not from Studio.** The wizard's thumbnail
   step fails *silently*: the input accepts the file, the log says "attached",
   and YouTube serves an auto-generated frame. Compare
   `i.ytimg.com/vi/<id>/maxresdefault.jpg` (cache-busted) against the render.
11. **A new channel cannot link a Short to a film, or pin a comment.** Both sit
   behind a one-time verification that wants a selfie video or a photo ID —
   a human step, never an automated one. Detect it, fall back to the link in
   the description plus a comment, and tell the user the one-line fix.

## Quick start

```bash
cd myvideo                                  # holds publish.json
python3 <skill>/scripts/upload.py login .   # only for a fresh Chrome profile
python3 <skill>/scripts/stings.py .         # intro + outro (once per channel)
python3 <skill>/scripts/metadata.py .       # meta/metadata_spec.json → metadata
python3 <skill>/scripts/seocheck.py .       # lint before uploading
python3 <skill>/scripts/thumb_doc.py .      # meta/thumbnail.json → out/thumbnail.jpg
python3 <skill>/scripts/upload.py recon .   # confirm the signed-in channel
python3 <skill>/scripts/upload.py upload .  # uploads, leaves it PRIVATE
python3 <skill>/scripts/upload.py thumbnail . # apply + verify the poster
python3 <skill>/scripts/upload.py publish . # make it public
python3 <skill>/scripts/upload.py verify .
```

A brand-new channel also needs its identity before the first video:

```bash
python3 <skill>/scripts/brand.py .            # icon + banner from publish.json
python3 <skill>/scripts/upload.py branding .  # applies both in Studio
```

And to cut vertical clips that feed the long-form film:

```bash
python3 <skill>/scripts/shorts.py .           # meta/shorts_spec.json → out/short_*.mp4
python3 <skill>/scripts/upload.py shorts .    # uploads each Short
python3 <skill>/scripts/upload.py promote .   # links each one back to the film
```

`upload.py edit <project> --video <id>` fixes metadata on a video that is
already uploaded, which is far cheaper than re-uploading a large file.

## Scripts

| Script | Purpose |
|---|---|
| `metadata.py` | Builds title, description, chapters and tags from `meta/metadata_spec.json`. Chapters come either from per-clip files (offsets measured, so they cannot drift) or from explicit `at:` timestamps for a single rendered film — the latter are validated against the real duration and against YouTube's silent rules. |
| `seocheck.py` | Lints metadata: caps, missing 0:00 chapter, title keywords absent from the opening lines, single-language description on a bilingual audience. |
| `thumbnail.py` | Renders 1280x720 in the news-debate style (red band, VS burst) from `meta/thumbnail.json`. |
| `thumb_doc.py` | Renders 1280x720 in the paper-explainer documentary style, reusing the film's own artwork. Refuses to emit text below the 168px legibility floor, or any layout where the headline overlaps the illustration. |
| `brand.py` | Renders the channel icon (800x800) and banner (2560x1440) from `publish.json` brand tokens. |
| `shorts.py` | Cuts vertical 1080x1920 Shorts from the finished film per `meta/shorts_spec.json`. |
| `stings.py` | Renders the channel intro and the subscribe/bell outro. |
| `upload.py` | Studio automation: `login`, `recon`, `channels`, `switch`, `branding`, `upload`, `shorts`, `promote`, `edit`, `thumbnail`, `publish`, `verify`. |
| `ct_text.py` | CoreText rasteriser — required for any non-Latin script. |

Pick the thumbnail renderer to match the film. The debate style earns clicks on
an argument show; on a documentary about people who were killed it reads as
tasteless, and a thumbnail that misrepresents the video is the one thing that
is never worth the click.

## Reference

Load only what the task needs.

- **`reference/titles.md`** — title anatomy, hook formulas, the keyword tail,
  and writing one title that works in two languages.
- **`reference/seo.md`** — description structure, chapters, tag budgeting, and
  making a non-English video discoverable in English.
- **`reference/thumbnails.md`** — the layout that survives a 168px search
  result, legibility rules, and the CoreText whitespace trap.
- **`reference/upload.md`** — every Studio automation gotcha, in the order you
  hit them.
- **`reference/shorts.md`** — cutting Shorts, and the three ways to link one
  back to the film when the first two are locked.
- **`reference/branding.md`** — channel icon and banner: sizes, safe areas,
  and applying them in Studio.
- **`reference/virality.md`** — what actually drives clicks and retention, and
  which common advice does not.
- **`reference/publish-config.md`** — every `publish.json` and spec field.

## Requirements

`playwright` with a signed-in persistent Chrome profile, `Pillow`, `ffmpeg`.
The YouTube Data API is deliberately not used — see `reference/upload.md`.
Text rendering uses CoreText and is **macOS-only**.
