---
name: researcher
description: >
  Builds the fact ledger a film is written against: two independent sources per
  claim, contested facts marked, recency checked, sources fetched and quoted
  verbatim. Use when starting a video on any factual topic, when a claim needs
  verifying, or when asked to source, fact-check or research a subject. Part of
  film-crew, normally dispatched by the director skill.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "1.0.0"
---

# Researcher

Find out what is true, and write it down in a form a script can be checked
against. Nothing else.

This is the first job in the film-crew pipeline. The
[`screenwriter`](../screenwriter/) writes only from what this produces, so a
claim that is not in the ledger cannot reach the screen.

---

## Non-negotiables

1. **Ledger before script.** A script written first and sourced afterwards
   bends facts to fit sentences that already exist.
2. **Two independent sources per claim.** Independent means *not derived from
   each other*. Six outlets rewriting one wire is one source.
3. **Two sources or no number.** Hedging is for contested facts, not a way to
   launder an unverified one. Cut the figure instead.
4. **Where sources disagree, record both.** Mark the claim `contested` and
   carry the hedge forward so the narration can speak it.
5. **Quote verbatim.** Every claim stores the sentence that supports it, not a
   paraphrase you will not be able to re-check later.
6. **Recency is a fact.** Legal, political and corporate threads move. Record
   when you checked, not just what you found.
7. **Absence is a finding.** "No source could be found for X" belongs in the
   ledger. It is what stops X being asserted anyway.

---

## Workflow

| | Step | Detail in |
|---|---|---|
| 1 | Scope the question — what must be true for this film to work | below |
| 2 | Fetch sources and read them | [`reference/sourcing.md`](reference/sourcing.md) |
| 3 | Write each claim, its two sources and its verbatim quote | [`reference/fact-ledger.md`](reference/fact-ledger.md) |
| 4 | Mark contested claims and unresolved gaps | [`reference/fact-ledger.md`](reference/fact-ledger.md) |
| 5 | Hand `ledger.json` to the screenwriter | — |

```bash
node skills/researcher/scripts/fetch-source.mjs targets.json sources/
```

Publishers that answer `curl` with a bot-challenge page are read through a
headless browser, which also writes most of the ledger's source record:

```bash
npm i --no-save playwright-core && npx playwright install chromium --only-shell
```

---

## Scoping

Ask what the film asserts, then work backwards. A ledger built by collecting
everything interesting about a topic is a reading list; a ledger built by
listing the claims the story depends on is a shooting requirement.

Prioritise, in this order:

1. **Load-bearing numbers** — the death toll, the fine, the date. If one of
   these is wrong the film is wrong.
2. **Causal claims** — "because", "led to", "caused". These are where sources
   most often disagree and where a script most often overreaches.
3. **Attributions** — who found, who said, who decided.
4. **Colour** — the detail that makes a scene. Nice to have; still sourced.

---

## Sensitive subjects

Deaths, crime, health, ongoing litigation and living people carry a duty of
care that outlives the render. The rules the screenwriter must write to start
here, in what you are allowed to record as settled:
[`../screenwriter/reference/sensitive-subjects.md`](../screenwriter/reference/sensitive-subjects.md).

---

## Output

`ledger.json` — the single artifact this role produces. Its schema, with a
worked example: [`reference/fact-ledger.md`](reference/fact-ledger.md).

The screenwriter's linter checks every narration line against it, so a ledger
that is vague fails downstream rather than here.
