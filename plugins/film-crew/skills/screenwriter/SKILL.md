---
name: screenwriter
description: >
  Turns a researched fact ledger into a narration script cut to a target
  runtime: every line bound to a claim, contested numbers hedged, line-level
  linting and sensitive-subject rules. Use when asked to write a
  documentary/explainer/history narration or fit a script to time. Part of
  film-crew, normally dispatched by the director skill.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "1.1.0"
---

# Film Screenwriter

Turn a **fact ledger** into a narration script that is accurate to the second
and accurate to the fact. Any subject — history, science, business, current
affairs, product stories.

This is the screenwriter's job in the film-crew pipeline: structure and
sentences. [`researcher`](../researcher/) establishes what is true and hands
over `ledger.json`; nothing may enter the script that is not in it.
[`paper` style](../style-paper/) turns the words into a video;
[`voice-booth`](../voice-booth/) reads them aloud.

---

## Non-negotiables

1. **The ledger is the ceiling.** If it is not in the ledger it does not get
   said. A missing fact is a request to the researcher, not a judgement call.
2. **Never soften a hedge the ledger set.** A claim marked `contested` stays
   contested in the narration.
3. **Every line is bound to a claim**, or marked `{~}` as rhetoric — and a `{~}`
   line may carry no fact: no number, no date, no name.
4. **Where sources disagree, say so.** Mark the claim `contested` and speak the
   hedge. *"At least 40,000"* survives scrutiny; *"40,000"* does not.
5. **Two sources or no number** — the researcher's rule, enforced again here
   because a number can be introduced by a rewrite.
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
| 2 | **Read the ledger.** It is the whole permitted vocabulary of fact. | [`../researcher/`](../researcher/) |
| 3 | **Find the gaps.** A beat you need and cannot source goes back to the researcher, not into the script. | [`../researcher/reference/fact-ledger.md`](../researcher/reference/fact-ledger.md) |
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

Fetching sources is the [`researcher`](../researcher/)'s job, not this one's.
If a claim turns out to be unsourced, send it back rather than looking it up
mid-sentence — that is how a script starts bending facts to fit prose.

---

## Reference

| Module | Read it when |
|---|---|
| [`../researcher/`](../researcher/) | Where the ledger comes from, and how claims are sourced |
| [duration-model.md](reference/duration-model.md) | Minutes → words; pace bands; act structure |
| [script-format.md](reference/script-format.md) | The `script.md` dialect; the full linter check list |
| [sensitive-subjects.md](reference/sensitive-subjects.md) | Real violence, disaster, crime, living people, defamation |

---

## Will not do

Invent a quote · round a figure for rhythm · resolve a live dispute · pad a
runtime. If the research supports six minutes, the honest answer is six minutes,
and you should say so.
