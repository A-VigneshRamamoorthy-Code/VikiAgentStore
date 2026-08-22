---
name: rights-manager
description: >
  The clearance gate before publication: every asset's licence and attribution
  on record, and every claim in the title and description checked back against
  the researcher's ledger. Use before uploading, when checking image or music
  licensing, or when a title may be overclaiming. Part of film-crew, normally
  dispatched by the director skill.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "1.0.0"
---

# Rights manager

Publishing is the only irreversible act in this pipeline. A wrong frame can be
re-rendered. A wrong claim that has been live for an hour has been
screenshotted.

This role asks, once and deliberately, two questions that nobody upstream is
positioned to ask: *are we allowed to publish this*, and *does it say what we
can defend?*

---

## What gets checked

1. **Every asset has a licence on record.** An image with no provenance is a
   takedown waiting to happen, and the moment to notice is before the upload,
   not after the strike.
2. **Attribution a licence requires is actually present.** CC-BY is not free;
   it is free *if you credit*. An uncredited CC-BY asset is unlicensed.
3. **The metadata's claims are the ledger's claims.** The title is where
   overreach happens, because it is written last by whoever wants the click.
   Every figure and every superlative is checked back against the research.

---

## Non-negotiables

1. **Refuse by default.** An unanswered question is a failure, not a warning.
2. **An exception must be reasoned and recorded.** `--allow "<why>"` writes the
   reason into `clearance.json`. A silent override is how a policy stops
   existing.
3. **Clearance covers a cut, not a film.** Re-render and it lapses — the
   approval snapshot binds the exact bytes.
4. **Absolutes are claims.** *first*, *only*, *never*, *deadliest* each need a
   source in the ledger, the same as a number does.

---

## Use

```bash
S=skills/rights-manager/scripts/clearance.py

python3 $S --assets meta/assets.json \
          --meta meta/youtube_metadata.json \
          --ledger ledger.json \
          -o meta/clearance.json
```

Exit code is the gate: `0` cleared, `1` refused.

The asset register is a list of `{file, license, credit}`. Recognised licences,
what each obliges, and how to handle archival footage, news stills, music and
AI-generated imagery: [`reference/licensing.md`](reference/licensing.md).

---

## Where it sits

`package` → **`clearance`** → `publish`. The publisher will not run without a
cleared record, and the director's approval gate hashes it along with the film,
the thumbnail and the captions — so a clearance obtained for one cut cannot be
carried over to another.
