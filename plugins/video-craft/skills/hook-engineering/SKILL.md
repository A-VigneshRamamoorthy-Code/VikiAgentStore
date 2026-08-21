---
name: hook-engineering
description: >
  Engineers a narration script so viewers keep watching — the opening three
  seconds, the loops that hold the middle, and the ending that earns a rewatch.
  Supplies a hook taxonomy, an open-loop ledger, a re-hook vocabulary, try-fail
  escalation, cut-rhythm and caption specs, and the rules for writing narration
  a neural TTS engine can actually perform. Ships a linter that fails a script
  for a weak opening, an unpaid loop, sentences too long for the ear, or markup
  edge-tts will read aloud. Use when a script is accurate but boring, when
  viewers drop off early, when asked to make a video engaging, go viral, or hold
  attention, or when writing a hook, a cold open, or a short-form narration.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "1.0.0"
---

# Hook Engineering

Accuracy earns the right to be watched. It does not cause it.

Within video-craft this is **aspect 1: attention**.
[`content-research`](../content-research/) decides what is *true* and how long
it runs; this skill decides what keeps someone *watching* it;
[`paper-explainer`](../paper-explainer/) renders it;
[`voiceover`](../voiceover/) reads it aloud.

---

## Non-negotiables

1. **Never open a loop you do not pay.** Every question raised must be answered
   on screen. Unpaid promises are the only reliable way to lose a returning
   audience.
2. **Context is earned, not given.** Open in the moment of highest stakes; supply
   background only after the viewer is committed.
3. **Every beat joined by *but* or *therefore*.** A chain held together by *and
   then* is a list, not a story — rewrite it.
4. **A cut is not a re-hook.** Changing the picture changes nothing if the story
   did not move. Re-hook with changed odds, new evidence, a choice, or a cost.
5. **One idea per sentence, 8–16 words.** The ear cannot re-read. If it cannot be
   said in one breath, split it.
6. **End-focus is the only emphasis.** edge-tts has no `<emphasis>`; put the
   payload word last, in a short sentence, with air around it.
7. **Punctuation is the timing instrument.** edge-tts XML-escapes its input, so
   any SSML tag is *spoken aloud*. See [tts-scripting.md](reference/tts-scripting.md).
8. **Pace is a contour.** Accelerate into a list, brake into a reveal. Urgency is
   a change, not a setting.
9. **End on an image, not a lesson.** The button is a concrete action. Never
   close on housekeeping.
10. **The linter is the gate.** Unlinted is a draft, not a deliverable.

---

## Workflow

| | Step | Detail in |
|---|---|---|
| 1 | **Pick the governing question.** One sentence the whole piece answers. It stays open until the final 10–20%. | [loops.md](reference/loops.md) |
| 2 | **Engineer the opening.** Choose a hook type, then budget seconds 0–3, 3–8, 8–15. | [hooks.md](reference/hooks.md) |
| 3 | **Draw the loop ledger.** Every loop gets an open, a progress and a close. Max three live at once. | [loops.md](reference/loops.md) |
| 4 | **Escalate.** Two or three try-fail cycles — *No-and*, then *Yes-but* — before the decisive action. | [loops.md](reference/loops.md) |
| 5 | **Place the re-hooks.** ~25%, ~50%, ~70–80% of runtime. Past ~8 minutes, switch to three visible acts and re-hook every ~90 s. | [loops.md](reference/loops.md#long-form--8-to-20-minutes) |
| 6 | **Write for the ear and for the engine.** Short sentences, spelled numbers, digital clock times, no homographs, no SSML. | [tts-scripting.md](reference/tts-scripting.md) |
| 7 | **Plan the picture.** Draw the thing rather than captioning it; cut rhythm, pattern interrupts, caption density, safe areas. | [visual-retention.md](reference/visual-retention.md) |
| 8 | **Land the ending.** Consequence, then meaning, then a button that rhymes with the opening. | [loops.md](reference/loops.md#land-the-ending) |
| 9 | **Lint, fix, repeat.** | below |

Writing a factual subject? Build the ledger in
[`content-research`](../content-research/) **first**. Retention technique never
licenses bending a fact — a hook that overstates what the sources support is
just clickbait with better rhythm.

---

## Commands

```bash
python3 scripts/hookcheck.py script.txt            # errors fail
python3 scripts/hookcheck.py script.txt --strict   # warnings fail too
python3 scripts/hookcheck.py script.txt --json     # machine-readable
python3 scripts/hookcheck.py script.txt --wpm 112  # duration at a given pace
```

Exit `0` pass, `1` fail. Python 3.9+, standard library only.

It fails a script for markup edge-tts would speak aloud, bare homographs, digits
and abbreviations the engine must guess at, sentences too long for the ear, a
throat-clearing opener, and an opening that spends its first seconds on nothing.
Full check list: [tts-scripting.md](reference/tts-scripting.md#what-the-linter-checks).

---

## Reference

| Module | Read it when |
|---|---|
| [hooks.md](reference/hooks.md) | The first fifteen seconds; hook taxonomy; anti-patterns; retention numbers |
| [loops.md](reference/loops.md) | Open and nested loops; re-hooks; escalation; long-form three-act structure; endings and loop seams |
| [visual-retention.md](reference/visual-retention.md) | Cut rhythm; pattern interrupts; motion and camera pace; picture-over-text; captions; safe areas |
| [tts-scripting.md](reference/tts-scripting.md) | Writing for the ear and for edge-tts; punctuation as timing; WPM bands |

[`examples/rowan-street/`](examples/rowan-street/) is one fully worked piece —
262 words, 2:19, every beat annotated with the technique it implements, a loop
ledger, and a passing lint.

---

## What is evidence and what is folklore

The reference modules mark unverified claims **[FOLKLORE]** rather than dropping
them, because some are useful heuristics even without evidence. Two worth
knowing up front:

- **"Something must change every five seconds."** Conflates shot changes with
  narrative turns. Cut often *and* move the story; they are different jobs.
- **The Zeigarnik effect** is the usual justification for open loops. A 2025
  meta-analysis found no general memory advantage for interrupted tasks. Loops
  still work — treat them as promises you owe the viewer, which is the better
  reason to pay them. Loewenstein's information-gap theory is the
  better-supported mechanism.

---

## Will not do

Manufacture a cliffhanger the content cannot pay · overstate a finding to
sharpen a hook · pad a runtime to hit a watch-time target · bait a thumbnail the
opening does not deliver. If the honest version of the story is quiet, make it
quiet and short — a viewer who feels tricked is a viewer you spend once.
