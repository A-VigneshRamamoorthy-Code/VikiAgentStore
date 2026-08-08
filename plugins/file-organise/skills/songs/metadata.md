# Metadata, Filenames & Album Art

Reference module for the `songs` skill. Covers Phases 2–4.

## Tag I/O with mutagen

MP4/M4A tag keys differ from ID3 — a mapping built for only one will silently report the
other's fields as missing:

| Field | ID3 (mp3) | MP4 (m4a) |
|-------|-----------|-----------|
| title | `TIT2` | `©nam` |
| album | `TALB` | `©alb` |
| artist | `TPE1` | `©ART` |
| album artist | `TPE2` | `aART` |
| genre | `TCON` | `©gen` |
| year | `TDRC` | `©day` |
| track | `TRCK` | `trkn` (a **tuple**, not text) |
| cover art | `APIC:*` | `covr` |

- Save ID3 as `v2_version=3` for the widest player compatibility.
- Normalise for comparison with `re.sub(r'[^a-z0-9]', '', s.lower())`.

## Filename and folder hygiene

Apply in this order:

1. **Strip piracy/site spam** from filenames, folder names *and* tag values:
   `masstamilan|isaimini|starmusiq|tamilwire|kuttyweb|sensongs|naasongs|www\.|\.com|\.net|320\s*kbps|128\s*kbps`
2. **Strip leading track numbers**: `^\s*\d{1,3}\s*[-._)\]]\s*\S` and `^\d{1,3}\s+\S`.
   Keep the number in the `track` tag.
3. **De-ALL-CAPS folder names** to title case, preserving genuine acronyms.
4. **Strip bitrate / `_V2` / trailing-number suffixes** from folder names.
5. **Flatten nested folders**; one folder per album.
6. **Remove `.DS_Store`** and other OS junk — it syncs to cloud storage and pollutes the tree.

### ⚠️ False positives that will bite you

- **Titles legitimately starting with a digit**: `108 Thenga`, `24K Magic`, `1989`, `96`,
  `7aum Arivu`, `3`. Require a separator, or verify against the title tag, before renaming.
- **Sequels are not junk suffixes**: `Aranmanai 2`, `Kanchana 2`, `Singam 3`,
  `Chennai 600028`.
- **Roman-numeral-looking fragments**: `Theme of 3`, `Who Am I` are real titles.

### Character rules

Strip `?`, `:`, `*`, `"`, `<`, `>`, `|`, `\`, `/` from **filenames** — they break Windows and
most cloud sync clients. They may safely remain in the **title tag**.

Beware over-eager initial-stripping: `O'Donis` must not lose its apostrophe.

## Metadata completion

Target a complete set on every file: **title, album, artist, album artist, genre, year**.

Source order, cheapest and most reliable first:

1. Existing tags on the file.
2. **Album siblings** — if one track in a folder knows the year/genre/album artist, the rest
   almost certainly share it. This resolves the majority of gaps for free.
3. Folder and file name.
4. An online lookup.

Reject placeholder values: `Unknown`, `Various`, `Track 01`, `Untitled`, `N/A`, `-`.

### ⚠️ The artist/composer trap

A file is often tagged with the **singer** while the release is credited to the **composer**.
This silently defeats any "artist must agree" match, and the failure is invisible — the lookup
just returns nothing. If an album lookup fails, retry with the composer, or match on album name
alone and accept a lower confidence with an explicit override list.

### ⚠️ The title-leaked-into-artist bug

Files where the artist field actually holds the song title. Detect **fuzzily**, not exactly —
the leak usually carries a mangled spelling:

| Title | Artist field (wrong) | Similarity |
|-------|----------------------|-----------|
| `Suttum Vizhi` | `Suttum Vizhi` | 1.00 |
| `Rahathulla` | `Ragatulla` | 0.84 |
| `Rangola Ola` | `Rangola` | 0.82 |

Use `difflib.SequenceMatcher` on normalised strings, threshold **≥ 0.62**, and additionally
require the suspect artist string to be near-unique in the library (a real artist recurs across
many files). Controls that must **not** flag: `Oru Maalai`/`Karthik` (0.25),
`Shoop`/`Salt-N-Pepa` (0.29), `Priya Priya`/`Vidyasagar` (0.40).

**Always self-test the detector** against these known-bad and known-good pairs before trusting a
"0 issues" result.

## Album art

- **Detect spam art, not just spam text.** Piracy sites embed a site-banner screenshot as the
  cover. Earlier text-only scans skip binary frames entirely, so this survives every filename
  cleanup. Hash known-bad images (MD5) and keep a growing blocklist.
- Fetch replacements in this order:
  1. **Deezer** — `search/album` is far stronger than `search/track` for non-Western
     catalogues. Note: search results carry **no `release_date`**.
  2. **iTunes Search API**
  3. **MusicBrainz / Cover Art Archive**
- **Cache every download** so re-runs are free.
- When a track moves to a different album folder, copy a sibling's cover onto it.
- **Leave art blank rather than embedding a wrong cover.** Ads, ringtones and regional one-offs
  genuinely exist in no public database. ~0.3% coverage loss is an acceptable end state; a wrong
  cover is not.
