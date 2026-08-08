# Acoustic Fingerprinting

Reference module for the `songs` skill. Covers Phase 5 — identifying audio by what it *is*
rather than by what its tags claim.

## Setup

Install `chromaprint`, which provides `fpcalc`. Use the free **AcoustID** web API.

```
fpcalc -json <file>          # compressed fingerprint + duration, for AcoustID lookup
fpcalc -raw -json <file>     # raw 32-bit frame vector (~0.124 s/frame), for local comparison
```

## API discipline

- Rate limit is **3 requests/second**. Enforce it with a **global lock**, not per-thread
  sleeps — a thread pool will otherwise burst straight past it and start getting errors.
- Pass `meta=recordings releasegroups compress` (**space** separated, not `+`).
- Filter candidates by **duration agreement** and prefer non-compilation release groups; the
  compilation entries carry far worse titles.
- Retry with backoff, and **checkpoint results to JSON every ~100 files** so a crash never
  costs a full re-run — and so later dedup passes can reuse the fingerprints for free.
- A 6–12 thread pool processes ~1600 files in roughly 15 minutes.

Expect around **85–90% identification** on a mixed real-world library.

## What fingerprinting is excellent at

### Identifying files with no usable tags at all

Real results from a library repair:

| File | Identified as | Score |
|------|---------------|-------|
| `shoot.mp3` (zero tags) | **"Shoop" — Salt-N-Pepa**, *Very Necessary* | 0.975, exact 248s duration match |
| `PRIYA3.MP3` (zero tags) | **"Priya Priya"** — *Run*, Vidyasagar | 0.956 |
| `01 ORU MALLI.mp3` | **"Oru Maalai"** — Karthik, *Ghajini* | 0.978 |

### Catching filenames that are not song titles

An entire album folder was named after its **singers** — `Karthik.mp3`,
`Shankar Mahadevan & Sujatha.mp3`, `Anubhama.mp3`. Detect by fuzzy-matching the filename
against the returned **artist** names.

⚠️ Use **fuzzy** matching — exact matching caught only half of them, because spelling drifts
between the tag and the database (`Sreram Partha Sarathy` vs `Sriram Parthasarathy`).

### Catching a mislabelled track

`Fallin' in Love.mp3` fingerprinted at 0.985 as **"Against the Grain" by Akon feat. Ray
Lavender**. The track's hook *samples* "Fallin' in Love", which is exactly why a human had
mislabelled it. No name-based logic could ever have found this.

### Generating duplicate candidates

See `deduplication.md`. This is the single highest-value use — it surfaces the same recording
filed under two completely unrelated names.

## ⚠️ What fingerprinting is BAD at: non-English titles

AcoustID/MusicBrainz is **not authoritative for regional-language titles**. For byte-identical
audio it routinely returns the **dubbed title in another language**:

| Tagged title | Database returns | Reality |
|--------------|------------------|---------|
| `Aaruyire` | `Tere Bina` | Hindi dub |
| `Jodi Jodi` | `Ek Lo Ek Muft` | Hindi dub |
| `Nannare` | `Barso Re` | Hindi dub |
| `Kalluri Salai` | `College Ki Saathi` | Telugu dub |
| `Poovukkul Olinthirukkum` | `Poovukkul` | abbreviated |

In one 1623-file run there were **426 title disagreements**. About half were mere
transliteration variants and most of the rest were dub titles or junk entries. Only **2–4**
were genuinely broken names.

> **Never bulk-apply fingerprint titles.** Use them as a **detector** of broken names, then fix
> only the ones you have individually confirmed are wrong. Overwriting 426 correct titles to
> fix 4 is a catastrophic net loss.

## The general principle

External databases are a good *detector* of broken data and a poor *source* of replacement
data. Let the fingerprint tell you **which** files to look at; decide **what** to write using
the evidence you can verify.
