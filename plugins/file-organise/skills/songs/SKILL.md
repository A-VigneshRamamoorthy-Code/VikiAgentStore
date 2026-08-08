---
name: songs
description: >
  Repairs and organises messy music libraries at scale. Fixes invalid filenames, missing or wrong
  metadata (title, album, artist, album artist, genre, year), piracy-site spam in tags and embedded
  album art, duplicate tracks, ALL-CAPS and nested folder structures, and leading track numbers.
  Uses acoustic fingerprinting (Chromaprint + AcoustID) as ground truth to identify untagged files
  and find duplicates that name matching cannot see. Use when asked to clean up, organise, tag,
  de-duplicate or fix a music/song/MP3 collection.
license: MIT
metadata:
  author: Copilot Research
  version: "1.0.0"
---

# Music Library Repair & Organisation

Use this skill when a user asks to clean up, tag, rename, de-duplicate or restructure a
collection of music files. It is written from a real 1843-file repair and encodes the traps
that cost the most time.

## Modules

Load the module for the phase you are working on:

| Module | Covers |
|--------|--------|
| [metadata.md](metadata.md) | Tag I/O, filename & folder hygiene, metadata completion, album art |
| [fingerprinting.md](fingerprinting.md) | Chromaprint + AcoustID, identifying untagged files, the non-English title trap |
| [deduplication.md](deduplication.md) | Three dedup passes, bit-error-rate thresholds, keeper selection |

## Golden rules

1. **Never delete. Quarantine.** Move rejects to `_Duplicates/` and `_Unplayable/`, and take a
   full pristine backup of the original tree *before touching anything*. Every destructive
   decision in this playbook is reversible only because of this.
2. **Work in a staging copy**, then push to the live location and verify the two are
   byte-identical (path set + size). Never edit the user's live library in place.
3. **Headless only.** Use HTTP APIs (Deezer, iTunes Search, MusicBrainz, Cover Art Archive,
   AcoustID). Never launch a visible browser window.
4. **Prefer detection over bulk overwrite.** External databases are a good *detector* of broken
   data and a poor *source* of replacement data.
5. **Verify with a self-test.** Any detector you write must be shown to flag the known-bad
   cases and stay silent on known-good controls. A detector reporting "0 issues" is worthless
   until you have proved it is not vacuous.
6. **Investigate every flag.** Do not dismiss one as a false positive without reading the
   actual value — but expect real false positives, because song titles contain digits and
   sequel numbers.

## Workflow

### Phase 1 — Inventory and backup

- Recursively list audio files (`.mp3`, `.m4a`, `.flac`, `.wav`, `.aac`, `.ogg`).
- `shutil.copytree` the whole tree to `backup/` **before any write**.
- Record path + size for every file so you can diff later.
- Use **mutagen** for all tag I/O.

### Phase 2 — Filename and folder hygiene → [metadata.md](metadata.md)

Strip site spam, leading track numbers, ALL-CAPS folders and bitrate suffixes; flatten nested
folders into one folder per album; delete `.DS_Store`.

Put single-track albums in one shared **`Singles/`** folder rather than creating hundreds of
one-file directories.

### Phase 3 — Metadata completion → [metadata.md](metadata.md)

Fill **title, album, artist, album artist, genre, year** on every file. Backfill from album
siblings first — it is the cheapest and most reliable source. Reject placeholders.

### Phase 4 — Album art → [metadata.md](metadata.md)

Detect and replace embedded piracy-banner images. Leave art blank rather than embedding a
wrong cover.

### Phase 5 — Acoustic fingerprinting → [fingerprinting.md](fingerprinting.md)

The force multiplier. Identifies files with no usable tags, catches filenames that are really
performer credits, and generates duplicate candidates.

### Phase 6 — De-duplication → [deduplication.md](deduplication.md)

Three passes: exact name, fuzzy name, then acoustic. Verify every acoustic candidate with a raw
bit-error-rate comparison before acting on it.

### Phase 7 — Verify

Re-scan the final tree and assert **all** of:

- staging and destination have identical path sets and sizes
- 0 missing tag fields, 0 placeholder values
- 0 spam strings in names or tags
- 0 leading track numbers (minus verified false positives)
- 0 ALL-CAPS folders, 0 nested directories, 0 stray non-audio files
- 0 known-bad art hashes
- report the exact cover-art coverage percentage

Print a single PASS/FAIL line.

## Cloud storage notes (OneDrive / iCloud / Dropbox)

- **Never use Finder AppleScript to delete a large cloud folder.** It can hang indefinitely —
  observed at 29+ minutes with zero items removed and an empty Trash. POSIX `rm -rf` on the
  same folder is instant.
- Prefer direct POSIX I/O on the sync provider path; it is orders of magnitude faster than
  driving Finder, and it does not hang.
- On macOS, confirm the remote actually received the changes:

  ```
  fileproviderctl evaluate <path>
  ```

  and check `isUploaded = 1`, `isUploading = 0`, `hasUnresolvedConflicts = 0`.
  There is **no** `fileproviderctl status` subcommand, and a bare `fileproviderctl dump` on a
  large library is far too slow to be useful. Parallelise `evaluate` across a thread pool to
  audit a whole library.
- After a large restructure, tell the user to **force their music app to rescan**. Phone and
  desktop players cache a stale library and will keep displaying the old, broken names long
  after the files are fixed — this looks exactly like the repair having failed.

## Reporting to the user

Close with a table of before/after counts and, importantly, the decisions you made *not* to
act — files intentionally left without art, alternate versions deliberately preserved, and
where the quarantined originals can be recovered from.
