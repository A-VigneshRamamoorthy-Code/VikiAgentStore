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

## Quick start

```bash
cd myvideo                                  # holds publish.json
python3 <skill>/scripts/stings.py .         # intro + outro (once per channel)
python3 <skill>/scripts/metadata.py .       # meta/metadata_spec.json → metadata
python3 <skill>/scripts/seocheck.py .       # lint before uploading
python3 <skill>/scripts/thumbnail.py .      # meta/thumbnail.json → out/thumbnail.jpg
python3 <skill>/scripts/upload.py recon .   # confirm the signed-in channel
python3 <skill>/scripts/upload.py upload .  # uploads, leaves it PRIVATE
python3 <skill>/scripts/upload.py verify .
```

`upload.py edit <project> --video <id>` fixes metadata on a video that is
already uploaded, which is far cheaper than re-uploading a large file.

## Scripts

| Script | Purpose |
|---|---|
| `metadata.py` | Builds title, description, chapters and tags from `meta/metadata_spec.json`. Chapter offsets are measured from the rendered files, so timestamps cannot drift. |
| `seocheck.py` | Lints metadata: caps, missing 0:00 chapter, title keywords absent from the opening lines, single-language description on a bilingual audience. |
| `thumbnail.py` | Renders 1280x720 from `meta/thumbnail.json`. |
| `stings.py` | Renders the channel intro and the subscribe/bell outro. |
| `upload.py` | Studio automation: `recon`, `channels`, `switch`, `upload`, `edit`, `verify`. |
| `ct_text.py` | CoreText rasteriser — required for any non-Latin script. |

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
- **`reference/virality.md`** — what actually drives clicks and retention, and
  which common advice does not.
- **`reference/publish-config.md`** — every `publish.json` and spec field.

## Requirements

`playwright` with a signed-in persistent Chrome profile, `Pillow`, `ffmpeg`.
The YouTube Data API is deliberately not used — see `reference/upload.md`.
Text rendering uses CoreText and is **macOS-only**.
