# The fact ledger

`ledger.json` is the script's evidence file. It exists so that a year from now,
anyone — including you — can point at any sentence in the video and see exactly
what it rests on.

---

## Shape

```json
{
  "topic": "The 1709 European cold wave",
  "compiled": "2026-08-20",
  "sources": [
    {
      "id": "enc-1709",
      "title": "Great Frost of 1709",
      "publisher": "Encyclopaedia (English)",
      "url": "https://example.org/wiki/Great_Frost_of_1709",
      "tier": "C",
      "accessed": "2026-08-20"
    },
    {
      "id": "jrnl-climate",
      "title": "The hardest winter in 500 years",
      "author": "Luterbacher et al.",
      "publisher": "Journal of Climate",
      "date": "2004",
      "url": "https://example.org/10.1175/jcli",
      "tier": "B",
      "accessed": "2026-08-20"
    }
  ],
  "claims": [
    {
      "id": "c-france-toll",
      "claim": "At least 100,000 excess deaths were recorded in France in the first months of 1709.",
      "sources": ["enc-1709", "jrnl-climate"],
      "confidence": "high",
      "contested": true,
      "note": "Estimates run from 100,000 to 600,000 depending on whether the following year's famine deaths are folded in. Speak the floor with a hedge."
    }
  ]
}
```

---

## Writing a claim

**A claim is one checkable assertion.** If you cannot imagine a single document
that would settle it, it is two claims.

| Bad | Why | Better |
|---|---|---|
| "The winter was devastating and changed Europe forever." | Not checkable | Split: the excess deaths (checkable) and the grain-price record (checkable) |
| "Rivers froze and 100,000 died in France." | Two facts, two source sets | `c-rivers`, `c-france-toll` |
| "The harvest failed." | Under-specified, no place or date | "The 1709 French wheat harvest fell to roughly a third of the 1708 yield." |

**Write the claim to be stricter than the narration**, never looser. The
narration may generalise a claim; it may not exceed it. If the ledger says "at
least 31" the script may say "dozens" — it may not say "36".

**Keep the number in the claim text.** A claim that says "many died" cannot
support a line that says "58 died", and a reviewer checking the script against
the ledger has no way to see the gap.

---

## Fields

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Kebab-case, stable, prefixed `c-`. Referenced from the script |
| `claim` | yes | One checkable assertion, written as a full sentence |
| `sources` | yes | ≥ 2 source ids, distinct. See [sourcing.md](sourcing.md) on independence |
| `confidence` | yes | `high` · `medium` · `low` |
| `contested` | no | `true` if sources disagree. Forces a hedge word in every line using it |
| `note` | no | The disagreement, the caveat, the provisional status |
| `quote` | no | Verbatim text, only if it is a genuine quotation with a traceable origin |

### `confidence`

- **high** — adjudicated, official, or corroborated by two independent Tier B
  sources. Speak it plainly.
- **medium** — reported consistently but not adjudicated. Attribute it:
  "police said", "the commission found".
- **low** — single credible source, or contemporaneous and never confirmed.
  Either cut it or speak the uncertainty out loud. Do not smuggle it in.

### `contested`

Set it whenever you found two defensible numbers. The linter then rejects any
line that uses the claim without one of:

> at least · about · around · roughly · more than · nearly · some · an
> estimated · up to · over · approximately · in excess of · close to

This single rule catches most of the factual errors that survive into a
finished script, because the errors are rarely inventions — they are hardened
approximations.

---

## Ordering

Order claims in narrative order and prefix by section (`c-sea-*`, `c-cst-*`,
`c-trial-*`). You will renumber the script many times; you should never have to
renumber the ledger.

---

## Unused claims

The linter reports claims no line uses. That is not a failure — a ledger is
allowed to be bigger than the script, and usually should be, because it is what
you cut *from*. But scan the list before shipping: an unused claim is sometimes
a fact you meant to include and lost in a rewrite.

---

## Reviewing a ledger

Before writing a single line, read the ledger straight through and ask:

1. Does any claim rest on one source, or on two sources that are really one?
2. Does any claim state a number that another claim contradicts?
3. Is any claim actually two claims wearing a coat?
4. Is anything here from a live thread that has moved on since the source?
5. Does any claim assert *motive*, *intent* or *blame* that is not adjudicated?

Item 5 is the one that ends up in a correction. "They intended to kill 5,000
people" is a claim about what an official said, not a claim about the world;
write it that way or leave it out.
