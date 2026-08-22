---
name: head-of-marketing
description: >
  Positions a finished video for an audience: SEO titles, descriptions,
  chapters, tags, thumbnails, channel branding, intro/outro stings and vertical
  Shorts, all linted against the platform caps and the fact ledger. Handles
  bilingual discoverability. Use when asked to write metadata, make a
  thumbnail, add chapters, brand a channel or cut Shorts. Uploading is the
  publisher skill's job, not this one.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "1.1.0"
---

# Film Head of Marketing

Everything between "the video is rendered" and "the video is live and
findable". Nothing here knows what the video is about, so any project can use
it.

## Non-negotiables

These are rules of the job. The Studio traps that used to live here moved with
the uploader — see [`upload.md`](../publisher/reference/upload.md) in the
publisher skill.

1. **`meta/youtube_metadata.json` is the only file the uploader reads.** A
   generator that writes anywhere else uploads stale metadata with no error at
   all. This has already shipped a wrong title once.
2. **Confirm the active channel before uploading.** One login usually owns
   several similarly named brand accounts and Studio lands on whichever was
   last active. Match the handle exactly; refuse otherwise.
3. **Search reads text, never audio.** Every concept a viewer might type must
   appear in the title, description or tags — and in *their* language, not only
   the spoken one.
4. **Respect the caps before uploading, not after:** title 100 chars,
   description 5000, all tags together 500, thumbnail 2 MB. Studio reports tag
   overflow only as "Cannot save until errors are resolved".
5. **Upload private, verify from outside, then publish.** Studio's own
   visibility field reads "Pending" while processing.
6. **Never claim more than the film delivers.** If the production is marked
   `unverified`, nothing in the metadata may describe it as researched, sourced
   or fact-checked.
7. **Never kill the browser process** — close the context, or the signed-in
   session is destroyed.
8. **Wait for the transfer, not the Done button.** Studio says "saved" while the
   file is still uploading; closing the browser abandons it unresumably.
9. **Set text with one `insert_text`,** then read it back. Per-character typing
   lets Studio steal focus and silently truncate the description.
10. **Navigate Studio in a fresh tab.** Its router rewrites any navigation
   issued from a tab already on another Studio route.
11. **Verify artwork from the CDN, not from Studio.** The thumbnail step fails
   silently — compare `i.ytimg.com/vi/<id>/maxresdefault.jpg` against the render.
12. **A new channel cannot link a Short to a film or pin a comment** until a
   one-time human verification is done. Detect it, fall back to a description
   link plus a comment, and tell the user the one-line fix.

## Quick start

```bash
cd myvideo                                  # holds publish.json
python3 <skill>/scripts/stings.py .         # intro + outro (once per channel)
python3 <skill>/scripts/metadata.py .       # meta/metadata_spec.json → metadata
python3 <skill>/scripts/seocheck.py .       # lint it, before anyone sees it
python3 <skill>/scripts/thumb_doc.py .      # meta/thumbnail.json → out/thumbnail.jpg
```

A brand-new channel also needs an identity before its first video:

```bash
python3 <skill>/scripts/brand.py .          # icon (800x800) + banner (2560x1440)
```

And to cut vertical clips that feed the long-form film:

```bash
python3 <skill>/scripts/shorts.py .         # meta/shorts_spec.json → out/short_*.mp4
```

## Where this stops

This skill produces **files**, never a live video. Applying any of it to a
channel — uploading, setting the thumbnail, going public, linking a Short back
to its film — belongs to the **publisher** skill, which is gated on the
director's approval. Keeping the two apart is deliberate: writing a title is
reversible and cheap, and publishing one is neither.

## Scripts

| Script | Purpose |
|---|---|
| `metadata.py` | Title, description, chapters and tags from `meta/metadata_spec.json` |
| `seocheck.py` | Lints metadata against the platform caps and the fact ledger |
| `thumbnail.py` | 1280x720 news-debate thumbnail (red band, VS burst) |
| `thumb_doc.py` | 1280x720 documentary thumbnail, reusing the film's own artwork |
| `brand.py` | Channel icon (800x800) and banner (2560x1440) |
| `shorts.py` | Cuts vertical 1080x1920 Shorts from the finished film |
| `stings.py` | Channel intro and subscribe/bell outro |
| `ct_text.py` | CoreText rasteriser — required for any non-Latin script |

Every script takes `--help`. Details of each are in the reference modules below.

**Pick the thumbnail renderer to match the film.** The debate style earns clicks
on an argument show; on a documentary about people who were killed it reads as
tasteless — and a thumbnail that misrepresents the video is the one thing never
worth the click.

## Reference

Load only what the task needs.

| | |
|---|---|
| [`titles.md`](reference/titles.md) | title anatomy, hook formulas, the keyword tail, one title in two languages |
| [`seo.md`](reference/seo.md) | description structure, chapters, tag budgeting, cross-language discoverability |
| [`thumbnails.md`](reference/thumbnails.md) | choosing a style, surviving a 168px result, the legibility guards, the CoreText whitespace trap |
| [`shorts.md`](reference/shorts.md) | cutting Shorts, and linking one back when the obvious routes are locked |
| [`branding.md`](reference/branding.md) | channel icon and banner: sizes, safe areas, applying them |
| [`virality.md`](reference/virality.md) | what drives clicks and retention, and which common advice does not |

Uploading any of this is the [`publisher`](../publisher/SKILL.md) skill, and
the fields of a `publish.json` are documented there.

## Requirements

`Pillow` and `ffmpeg`. Text rendering uses CoreText and is **macOS-only**.
Nothing here needs a browser or a signed-in channel; that is the publisher's
dependency, not this skill's.
