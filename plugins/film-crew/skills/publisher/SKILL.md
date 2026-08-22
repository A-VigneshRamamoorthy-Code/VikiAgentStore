---
name: publisher
description: >
  Puts a finished, approved video onto YouTube and nothing further: signs in,
  uploads private, verifies what actually went live, applies the thumbnail,
  links Shorts back to their film, and flips visibility. Every command that
  touches a live video is gated on the director's sha256 approval. Use when
  asked to upload, publish, go live, fix metadata on an existing video, or set
  a thumbnail. Writing the metadata itself is the head-of-marketing skill.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "1.0.0"
---

# Publisher

The last step, and the only one that cannot be undone by running it again.

Everything before this produces files. This skill produces **an audience**. A
wrong title can be edited and a bad render replaced, but people who have
already watched something have already watched it. That asymmetry is why this
is a separate skill from the one that writes the metadata, and why it refuses
to act on bytes nobody approved.

## Non-negotiables

1. **Upload private. Always.** Verify what actually went live, *then* change
   visibility. Uploading straight to public means any mistake — a truncated
   description, the wrong thumbnail, a bad encode — is in front of viewers
   before anyone has looked at it.
2. **`meta/youtube_metadata.json` is the only file read.** A generator that
   writes anywhere else uploads stale metadata with no error at all. This has
   already shipped a wrong title once.
3. **The thumbnail step fails silently.** Studio accepts the file, the log says
   it worked, and YouTube serves an auto-generated frame instead. The only
   honest confirmation is reading the poster back off the CDN.
4. **Never work around a refused approval.** If the gate says no, the answer is
   to get the bytes approved, not to delete the lock. Deleting it is a real
   workflow for videos the director never touched — it is not a way past a
   refusal.
5. **The Data API is deliberately not used.** Browser automation against Studio
   is what survives the quota and the OAuth review; the reasoning is in
   [`upload.md`](reference/upload.md).

## Quick start

```bash
cd myvideo                                  # holds publish.json
python3 <skill>/scripts/config.py init . --channel handle --name "Channel Name" \
        --video ep1/film.mp4 --thumbnail meta/thumbnail.jpg   # write publish.json
python3 <skill>/scripts/upload.py login .   # only for a fresh Chrome profile
python3 <skill>/scripts/upload.py recon .   # confirm the signed-in channel
python3 <skill>/scripts/upload.py upload .  # uploads, leaves it PRIVATE
python3 <skill>/scripts/upload.py thumbnail .  # apply + verify the poster
python3 <skill>/scripts/upload.py verify .
python3 <skill>/scripts/upload.py publish . # make it public
```

Shorts, and channel identity:

```bash
python3 <skill>/scripts/upload.py shorts .    # uploads each cut Short
python3 <skill>/scripts/upload.py promote .   # links each one back to the film
python3 <skill>/scripts/upload.py branding .  # applies icon + banner in Studio
```

`upload.py edit <project> --video <id>` fixes metadata on a video that is
already up, which is far cheaper than re-uploading a large file.

## The approval gate

**Every command that touches a live video** — `upload`, `edit`, `thumbnail`,
`publish`, `shorts` — refuses to run unless `publish.lock.json`, written by the
`director` skill, covers exactly what is about to go out. That includes:

- being pointed at a video id the approval did not produce;
- making something public that was only approved private;
- a file that changed by a single byte since it was approved;
- a Short in a batch that has no approval of its own.

Approved bytes are copied aside and the copy is what gets attached, so a file
rewritten between the check and the upload cannot reach the channel.

No lock file means the director is not driving this upload. That is allowed,
and it is announced rather than assumed. Full detail:
[`approvals.md`](reference/approvals.md).

## Scripts

| Script | Purpose |
|---|---|
| `upload.py` | Studio automation: `login`, `recon`, `upload`, `edit`, `thumbnail`, `publish`, `verify`, `shorts`, `promote`, `branding` |
| `config.py` | `publish.json`, project paths, and the approval protocol. Shared with the marketing skill |

Both take `--help`.

## Reference

Load only what the task needs.

| | |
|---|---|
| [`upload.md`](reference/upload.md) | every Studio automation gotcha, in the order you hit them |
| [`approvals.md`](reference/approvals.md) | the lock file, what is checked where, and every refusal message |
| [`publish-config.md`](reference/publish-config.md) | `publish.json` in full |

## Requires

`playwright` with a signed-in persistent Chrome profile, and `ffmpeg` for the
verification probes.
