---
name: story-editor
description: >
  Edits accurate scripts for retention: 0–3s hooks, open-loop ledgers,
  re-hooks, try-fail escalation, cut rhythm, captions and TTS-safe prose. Use
  when a script is boring, drop-off is high, or asked to write hooks, cold
  opens, viral narration or Shorts. Part of film-crew, normally dispatched by the
  director skill.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "1.0.0"
---

# Film Story Editor

Accuracy earns the right to be watched. It does not cause it.

This is the story editor's job in the film-crew pipeline: attention.
[`researcher`](../researcher/) decides what is *true*,
[`screenwriter`](../screenwriter/) decides how long it runs; this skill decides
what keeps someone *watching* it;
[`paper` style](../style-paper/) renders it;
[`voice-booth`](../voice-booth/) reads it aloud.

---

## Non-negotiables

1. **Never open a loop you do not pay.** Every question raised must be answered
   on screen. Unpaid promises are the only reliable way to lose a returning
   audience. *Paying a loop is not the same as resolving it:* where the record
   genuinely does not settle the question, the payment is saying so plainly and
   showing why. What loses an audience is a question the film forgot, not one it
   answered with "we do not know".
2. **Context is earned, not given.** Open in the moment of highest stakes; supply
   background only after the viewer is committed. *(Long-form investigative
   documentary inverts this deliberately — see the register note below.)*
3. **Every beat joined by *but* or *therefore*.** A chain held together by *and
   then* is a list, not a story — rewrite it.
4. **A cut is not a re-hook.** Changing the picture changes nothing if the story
   did not move. Re-hook with changed odds, new evidence, a choice, or a cost.
5. **Sentence length is a register decision.** In `feed`, one idea per sentence
   at 8–16 words. In `documentary`, the measured mean is **16.4** with 16% of
   sentences past 24 words — clipped prose throughout reads as a list of facts,
   not an account. `hookcheck --register documentary` enforces the band.
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
| 1b | **Read the register.** `brief.register` is already set — feed opening, or documentary cold open. Do not re-decide it; overriding it makes a 25-minute film sound like a trailer for itself. | [hooks.md](reference/hooks.md#the-documentary-cold-open) |
| 2 | **Engineer the opening.** Choose a hook type, then budget seconds 0–3, 3–8, 8–15. | [hooks.md](reference/hooks.md) |
| 3 | **Draw the loop ledger.** Every loop gets an open, a progress and a close. Max three live at once. | [loops.md](reference/loops.md) |
| 4 | **Escalate.** Two or three try-fail cycles — *No-and*, then *Yes-but* — before the decisive action. | [loops.md](reference/loops.md) |
| 5 | **Place the re-hooks.** ~25%, ~50%, ~70–80% of runtime. Past ~8 minutes, switch to three visible acts and re-hook every ~90 s. | [loops.md](reference/loops.md#long-form--8-to-20-minutes) |
| 6 | **Write for the ear and for the engine.** Short sentences, spelled numbers, digital clock times, no homographs, no SSML. | [tts-scripting.md](reference/tts-scripting.md) |
| 7 | **Plan the picture.** Draw the thing rather than captioning it; cut rhythm, pattern interrupts, caption density, safe areas. | [visual-retention.md](reference/visual-retention.md) |
| 8 | **Land the ending.** Consequence, then meaning, then a button that rhymes with the opening. | [loops.md](reference/loops.md#land-the-ending) |
| 9 | **Lint, fix, repeat.** | below |

Writing a factual subject? Build the ledger in
[`screenwriter`](../screenwriter/) **first**. Retention technique never
licenses bending a fact — a hook that overstates what the sources support is
just clickbait with better rhythm.

---

## Commands

```bash
python3 scripts/hookcheck.py script.md                       # errors fail
python3 scripts/hookcheck.py script.md --strict              # warnings fail too
python3 scripts/hookcheck.py script.md --json                # machine-readable
python3 scripts/hookcheck.py script.md --register documentary  # override the script
python3 scripts/hookcheck.py script.md --wpm 150             # override the pace
```

### Cutting a Short

```bash
python3 scripts/cut.py --hook h1 \
    --beat-plan ep1/beat-plan.json \
    --timeline ep1/cooper.timeline.json \
    --title "He Stepped Off The Back Of An Airliner" \
    -o short1/short.json
```

**Never work the window out by hand.** A hook marks its span by narration id,
because that is what the story means, but turning ids into seconds by adding up
the narration clips gives the wrong answer: the renderer trims the recorded
silence off every clip before laying the voice down, so the files on disk run
about a second longer than what plays and the error compounds line by line. On
a 12-minute film that put a cut 12 seconds late — it opened halfway through a
sentence and closed two lines past the image it was chosen for. `cut.py` reads
the timeline the renderer published instead, and warns when the result is past
the 60-second Shorts ceiling or too brief to land a turn.

**It takes a whole `script.md`, not just narration.** The frontmatter,
`## [00:00]` headings, `lNN` line ids and `{c14}` claim references are removed,
and wrapped continuation lines are re-joined, so the result is exactly what
`scriptcheck --plain` prints. Plain narration is still accepted unchanged.
Re-joining matters more than it looks: a sentence the author wrapped across two
rows counts as two short sentences, which drags every cadence statistic down by
the amount of the wrapping.

**The register comes from the script.** `register:` in the frontmatter is
written by the screenwriter from `brief.register` — the one place the decision
is made. `--register` overrides it; a script that declares none is linted as
`feed`, whose tighter caps fail loudly rather than quietly licensing lines
nobody meant to allow. An unrecognised value is an error, not a fallback.
The register changes both the sentence lengths accepted and the words-per-minute
the runtime is computed from. Linting a documentary at feed cadence is not a
stricter check, it is the wrong one — measured against a real 29-minute
investigation, `feed` raises forty-seven errors and predicts a 41-minute
runtime, while `documentary` raises two and predicts the length within one
percent. Shorts are always cut at feed cadence, whatever the episode uses.

`wpm` is read from the frontmatter too, and is *not* reset by `--register`: the
pace is a fact about the recording, while the register is a judgement about the
writing.

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
them, because some are useful heuristics even without evidence. The two most
often repeated as fact — "something must change every five seconds" and the
Zeigarnik effect as the justification for open loops — are examined in
[visual-retention.md](reference/visual-retention.md) and
[loops.md](reference/loops.md). Neither survives contact with the evidence in
the form it is usually quoted; both point at a real technique underneath.

---

## Will not do

Manufacture a cliffhanger the content cannot pay · overstate a finding to
sharpen a hook · pad a runtime to hit a watch-time target · bait a thumbnail the
opening does not deliver. If the honest version of the story is quiet, make it
quiet and short — a viewer who feels tricked is a viewer you spend once.
