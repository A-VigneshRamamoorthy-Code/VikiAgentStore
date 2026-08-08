# De-duplication

Reference module for the `songs` skill. Covers Phase 6.

Run three passes, in order. Each finds duplicates the previous one cannot see.

1. **Exact name** — normalised filename equality.
2. **Fuzzy name** — normalised similarity ≥ ~0.85.
3. **Acoustic** — the same recording filed under two unrelated names.

A real 1843-file library yielded 185 exact + 33 fuzzy + **52 acoustic**. The acoustic pass
found, for example, a file named "Bharadhiraja Speech" that was byte-identical to
"Adi Manjak Kizhangae" — invisible to every name-based method.

## Proving two files are the same recording

AcoustID **grouping alone produces false positives** — it grouped `Karuthavanlaam Galeejaam`
with `Enna Solla`, and *Frozen*'s "In Summer" with "The Trolls". Always verify locally.

Use raw Chromaprint **bit-error rate (BER)**:

1. `fpcalc -raw -json` on both files → two lists of 32-bit ints.
2. Slide one over the other (**±140 frames**), XOR, popcount, divide by bits compared.
3. Take the minimum over all offsets.

Sampling **every other frame** is plenty and halves the cost.

### Measured separation

The distribution is cleanly bimodal, with one dangerous band in the middle:

| BER | Meaning |
|-----|---------|
| **0.000 – 0.103** | Same recording |
| **0.13 – 0.20** | ⚠️ **Shares a backing track** — Male/Female, Karaoke, Reprise, Remix |
| **0.227 – 0.477** | Different songs |

### ⚠️ The 0.13–0.20 band is the trap

A naive `BER < 0.22` threshold **deletes real alternate versions**. Observed in this band:

- `Venpani Malare (Female)` vs `(Male)` — 0.138
- `Darling Dambakku Reprise` — 0.168
- `Oodhaa Kalaru (Karaoke)` — 0.198

Correct rule:

```
same = ber <= 0.12
    or (ber <= 0.20 and title_similarity >= 0.72 and no_version_word)
```

where a version word is any of `male`, `female`, `karaoke`, `reprise`, `remix`,
`instrumental`, `unplugged`, `live`, `cover`.

### Cross-codec comparison

m4a vs mp3 usually works (`Kandaangi.m4a` vs `Kandangi Kandangi.mp3` = 0.080) but can be
elevated (`Ei Sandakara.m4a` vs `Hey Sandakkara.mp3` = 0.227). Treat borderline cross-codec
pairs as **keep both**.

## ⚠️ Files with no fingerprint match are invisible to fingerprint-grouped dedup

If you build duplicate groups *from* AcoustID identity, every file that returned no match is
never compared to anything. One folder shipped both `Nenjukullae.mp3` and `Nenjukulle.mp3`
because only one of the two had a lookup hit.

**Always add a final pass that ignores AcoustID entirely** and raw-compares every plausible
pair:

- all same-folder pairs whose durations are within ~12 s, **plus**
- cross-folder pairs with title similarity ≥ 0.72 and durations within ~12 s

On a 1572-file library this is roughly 4800 comparisons — cheap, and it closes the hole.

## Keeper selection: three independent decisions

Do **not** pick one file and keep it whole. The best audio, the best folder and the best name
are frequently on *different* copies — a 271 kbps rip sat loose in `Singles/` while the 64 kbps
copy was correctly filed under its album.

| Decision | Rule |
|----------|------|
| **Audio** | Highest bitrate. Rank in **buckets** (`bitrate // 16000`) so a trivial 23 kbps edge cannot outvote stronger evidence. |
| **Folder** | The real album folder beats `Singles/`. Promote the keeper into it. |
| **Name** | **Leave it alone** unless provably wrong (an explicit, hand-verified retitle entry). |

### ⚠️ Both obvious naming heuristics are wrong

| Heuristic | What it produced |
|-----------|------------------|
| Longest name wins | `Lajjavathiyea` → `Lajjavathiyea Ii` — a junk suffix won because it was longer |
| Closest to the external database wins | `Poovukkul Olinthirukkum` → `Poovukkul`, `Irukkana Idupu Irukkana` → `Irukaana` — databases abbreviate |

Renaming between two already-valid names is churn with pure downside risk. Don't.

### Implementation notes

- Group with **union-find** so transitive duplicates collapse correctly.
- Execute **removals before moves**, so a keeper can take a removed file's path.
- When a keeper moves to a different album folder, copy a sibling's cover art onto it.
- **Never delete — quarantine** to `_Duplicates/`, and zero-byte/unreadable files to
  `_Unplayable/`. Every decision here must stay reversible.
