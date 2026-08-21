---
name: content-research
description: >
  Researches any topic against reliable sources — encyclopaedias, wire services
  and major news outlets, court judgments, official inquiry reports, academic
  work and published books — and turns the findings into a narration script cut
  to an exact target duration. Every spoken sentence is bound to a numbered
  claim in a fact ledger, every claim carries at least two independent sources,
  and a linter fails the script if a figure, date or name is spoken without one,
  if a contested number is stated without a hedge, or if the word count does not
  fit the runtime. Includes a policy for covering real events, disasters and
  living people without dramatising them. Use when asked to research a topic and
  write a video script, to write a documentary / explainer / historical
  narration, to fact-check a script, or to fit a script to a given runtime.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "1.1.0"
---

# Content Research

Turn a topic into a **narration script that is accurate to the second and
accurate to the fact**. Any subject — history, science, business, current
affairs, product stories.

Within video-craft this is **aspect 0: truth and structure**.
[`paper-explainer`](../paper-explainer/) turns the words into a video;
[`voiceover`](../voiceover/) reads them aloud.

---

## Non-negotiables

1. **Ledger before script.** A script written first and sourced afterwards bends
   facts to fit sentences already written.
2. **Two independent sources per claim.** Independent means *not derived from
   each other*. Six outlets rewriting one wire is one source.
3. **Every line is bound to a claim**, or marked `{~}` as rhetoric — and a `{~}`
   line may carry no fact: no number, no date, no name.
4. **Where sources disagree, say so.** Mark the claim `contested` and speak the
   hedge. *"At least 40,000"* survives scrutiny; *"40,000"* does not.
5. **Two sources or no number.** Hedging is for contested facts, not a way to
   launder an unverified one. Cut the figure instead.
6. **Write to the clock.** The word budget is fixed by the runtime before the
   first sentence. Cut *content*, never pace.
7. **Attribute in the narration, not just the ledger.** "The inquiry found…" is
   more honest and more watchable than a flat assertion.
8. **Recency is a fact.** Legal and political threads move; check current state.
9. **The linter is the gate.** Unlinted is a draft, not a deliverable.

---

## Workflow

| | Step | Detail in |
|---|---|---|
| 1 | **Frame the question.** One sentence on what the video answers; a bare topic produces a script that wanders. | — |
| 2 | **Research outward from a spine.** Start encyclopaedic to learn the shape and harvest its citation list, then leave it. | [sourcing.md](reference/sourcing.md) |
| 3 | **Build the ledger.** Each fact becomes a numbered claim with sources. Contradictions get recorded, not resolved. | [fact-ledger.md](reference/fact-ledger.md) |
| 4 | **Budget the runtime.** Duration → words → chapter table, *before* writing. | [duration-model.md](reference/duration-model.md) |
| 5 | **Write the script.** One idea per line, 6–18 words, each bound to its claims. | [script-format.md](reference/script-format.md) |
| 6 | **Lint, fix, repeat.** | below |
| 7 | **Hand off.** Line ids map onto storyboard beats; `--plain` feeds TTS. | [script-format.md](reference/script-format.md) |

Real violence, disaster, crime or living people involved? Read
[sensitive-subjects.md](reference/sensitive-subjects.md) **before** step 5.

---

## Commands

```bash
python3 scripts/scriptcheck.py script.md            # errors fail
python3 scripts/scriptcheck.py script.md --strict   # warnings fail too
python3 scripts/scriptcheck.py script.md --json     # machine-readable
python3 scripts/scriptcheck.py script.md --plain    # narration only, for TTS
```

Exit `0` pass, `1` fail. Python 3.9+, standard library only. Enforces rules 2–6
plus the `sensitive: true` vocabulary rules. Full check list:
[script-format.md](reference/script-format.md#what-the-linter-checks).

Publishers that answer `curl` with a bot-challenge page are read through a
headless browser, which also writes most of the ledger source record:

```bash
npm i --no-save playwright-core && npx playwright install chromium --only-shell
node scripts/fetch-source.mjs targets.json sources/
```

---

## Reference

| Module | Read it when |
|---|---|
| [sourcing.md](reference/sourcing.md) | Source tiers; independence; contradictions; fetching blocked publishers |
| [fact-ledger.md](reference/fact-ledger.md) | Building `ledger.json`; claim wording; contested facts |
| [duration-model.md](reference/duration-model.md) | Minutes → words; pace bands; act structure |
| [script-format.md](reference/script-format.md) | The `script.md` dialect; the full linter check list |
| [sensitive-subjects.md](reference/sensitive-subjects.md) | Real violence, disaster, crime, living people, defamation |

---

## Will not do

Invent a quote · round a figure for rhythm · resolve a live dispute · pad a
runtime. If the research supports six minutes, the honest answer is six minutes,
and you should say so.
