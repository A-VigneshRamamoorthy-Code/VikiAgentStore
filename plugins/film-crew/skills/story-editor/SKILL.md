---
name: story-editor
description: >
  Edits accurate scripts for retention: 0–3s hooks, open-loop ledgers,
  re-hooks, try-fail escalation, cut rhythm, captions and TTS-safe prose.
  Separates what platforms actually document from creator method and folklore,
  and lints promises against payoffs. Use when a script is boring, drop-off is
  high, or asked to write hooks, cold opens, viral narration or Shorts. Part of
  film-crew, normally dispatched by the director skill.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "1.1.0"
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
2. **A promise must name its payload.** "Watch until the end" is a request, not
   a promise. Curiosity is the discomfort of a *specific* gap — so name the
   missing thing, or do not tease it.
3. **Context is earned, not given.** Open in the moment of highest stakes; supply
   background only after the viewer is committed. *(Long-form investigative
   documentary inverts this deliberately — see the register note below.)*
4. **Every beat joined by *but* or *therefore*.** A chain held together by *and
   then* is a list, not a story — rewrite it.
5. **A cut is not a re-hook.** Changing the picture changes nothing if the story
   did not move. A beat is progress only if it changes **goal, odds, knowledge,
   cost, options, relationship or time remaining**. If you cannot name which one
   moved, it is decoration.
6. **Escalation needs a named axis.** Cost, scale, danger, rarity, intimacy,
   irreversibility, options remaining. Pick one and move it; "more exciting" is
   not a direction.
7. **Never stage what did not happen.** No invented failure, no manufactured
   fear, no superlative the ledger cannot source. A staged setback creates a
   payoff the footage cannot pay.
8. **Sentence length is a register decision.** In `feed`, one idea per sentence
   at 8–16 words. In `documentary`, the measured mean is **16.4** with 16% of
   sentences past 24 words — clipped prose throughout reads as a list of facts,
   not an account. `hookcheck --register documentary` enforces the band.
9. **End-focus is the only emphasis.** edge-tts has no `<emphasis>`; put the
   payload word last, in a short sentence, with air around it.
10. **Punctuation is the timing instrument.** edge-tts XML-escapes its input, so
    any SSML tag is *spoken aloud*. See [tts-scripting.md](reference/tts-scripting.md).
11. **Pace is a contour.** Accelerate into a list, brake into a reveal. Urgency is
    a change, not a setting.
12. **End on an image, not a lesson.** The button is a concrete action. Never
    close on housekeeping.
13. **Label the evidence class of every rule you repeat.** This field runs on
    numbers nobody can source. Say whether a claim is `[PLATFORM]`,
    `[EXPERIMENT]`, `[CREATOR METHOD]`, `[HOUSE HEURISTIC]` or `[FOLKLORE]` —
    and never quote a retention threshold as if it were a specification.
14. **The linter is the gate.** Unlinted is a draft, not a deliverable.

---

## Workflow

| | Step | Detail in |
|---|---|---|
| 1 | **Pick the governing question.** One sentence the whole piece answers. It stays open until the final 10–20%. | [loops.md](reference/loops.md) |
| 1b | **Read the register.** `brief.register` is already set — feed opening, or documentary cold open. Do not re-decide it; overriding it makes a 25-minute film sound like a trailer for itself. | [hooks.md](reference/hooks.md#the-documentary-cold-open) |
| 2 | **Engineer the opening.** Choose a hook type, then budget seconds 0–3, 3–8, 8–15. | [hooks.md](reference/hooks.md) |
| 3 | **Draw the loop ledger.** Every loop gets an open, a progress and a close. Max three live at once. Record it in the script with `> loop <name> open\|progress\|close` so the linter can audit it. | [loops.md](reference/loops.md) |
| 4 | **Escalate along a named axis.** Two or three try-fail cycles — *No-and*, then *Yes-but* — before the decisive action. Name which axis moves each time; never stage a failure that did not happen. | [loops.md](reference/loops.md) |
| 5 | **Place the re-hooks by structure, not by stopwatch.** Put a fresh question wherever a promise has just been paid — the moment of satisfaction is the moment of exit. There is no sourced cadence; treat any fixed interval as a house default, not a rule. | [loops.md](reference/loops.md#long-form--8-to-20-minutes) |
| 6 | **Write for the ear and for the engine.** Short sentences, spelled numbers, digital clock times, no homographs, no SSML. | [tts-scripting.md](reference/tts-scripting.md) |
| 7 | **Plan the picture.** Draw the thing rather than captioning it; cut rhythm, pattern interrupts, caption density, safe areas. | [visual-retention.md](reference/visual-retention.md) |
| 8 | **Land the ending.** Consequence, then meaning, then a button that rhymes with the opening. | [loops.md](reference/loops.md#land-the-ending) |
| 8b | **Audit the promises.** Walk the script once asking only: what did I promise, and where is it paid? Every tease names a payload; every superlative carries a claim id; every sponsor read bridges into the story. | [loops.md](reference/loops.md) |
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
the timeline the renderer published instead, and warns when the result reaches
the 60-second Shorts ceiling or is too brief to land a turn.

**It records which film it was timed against.** The cut carries `source_video`,
derived from the timeline's own stem (`cooper.timeline.json` → `cooper.mp4`)
unless `--source-video` says otherwise, and `shorts.py` slices exactly that.
Without it a two-episode project resolves ep2's timestamps against ep1's film
and mis-slices in silence. `--title` is a precondition rather than a warning:
a Short with no hook text is not a Short, so `cut.py` refuses before writing
rather than emitting a file it would then declare unusable.

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

It also audits **what the script owes the viewer**: teases that promise nothing
specific, superlatives with no claim reference, an opening minute that is all
future tense, loops that close before they open or never close, loops opened in
the final tenth, and sponsor reads with no story bridge.

Those checks read `>` directive lines placed under the narration they annotate:

```markdown
l5  Why did the bell ring thirteen times?
> loop A open
l7  The thirteenth strike was a flood warning.  {c14}
> loop A close
```

`> loop <name> open|progress|close`, `> execution`, `> payoff: <what it pays>`
and `> sponsor: story-bridge`. They are invisible to `scriptcheck` and to
edge-tts — which is precisely why they are `>` lines and not inline `{...}`
markers, since `scriptcheck` reads a trailing brace group as claim ids.

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

Almost every retention number in circulation is folklore with a confident
delivery. The reference modules therefore label each claim by how it is known:

| Label | Means |
|---|---|
| `[PLATFORM]` | Stated by YouTube/TikTok in their own documentation |
| `[EXPERIMENT]` | Peer-reviewed, with the population and outcome named |
| `[CREATOR METHOD]` | A named creator describes doing it — evidence of practice, not of effect |
| `[HOUSE HEURISTIC]` | This skill's default. Defensible, unproven, override freely |
| `[FOLKLORE]` | Widely repeated, unsourced, sometimes false |

Unverified claims are kept and marked rather than deleted, because several are
useful heuristics even without evidence. But a rule you cannot source must never
be quoted as a specification.

**Claims this skill has removed or corrected**, having failed verification:

- *"You need >50% average view duration for the algorithm to promote you."*
  No such threshold is documented anywhere by YouTube.
- *"CTR above 4% is good, above 10% is excellent."* YouTube's own figure is that
  **half of all channels sit between 2% and 10%** — the band is the norm, not a
  grade.
- *"Re-hook every 5–10 seconds"* / *"reset the video every 90 seconds"*. Not in
  the MrBeast corpus; the phrase "reset the video" does not appear in it.
- *"Cut every three seconds."* MrBeast cites rigid cut rules as a *mistake*, and
  in March 2024 publicly moved toward slower storytelling.
- *"Fast cutting increases comprehension."* EEG work finds chaotic editing
  widens attentional scope while **reducing** conscious processing — attention
  and comprehension are not the same variable.
- *"Captions increase completion by 12–40%."* The sourced finding is that
  captions can *divide* attention; caption for accessibility, and stop claiming
  the retention number.
- *"Loop seams earn a Shorts ranking bonus."* Engaged views exclude loops.

The two most-repeated rules of all — "something must change every five seconds"
and the Zeigarnik effect as the justification for open loops — are examined at
length in [visual-retention.md](reference/visual-retention.md) and
[loops.md](reference/loops.md). Neither survives contact with the evidence in
the form it is usually quoted; both point at a real technique underneath.

Provenance matters for the creator material too. The widely-circulated "MrBeast
production bible" is a **staff-verified circulated internal document**, not an
authenticated publication — and it says of itself, "this is not a rulebook".

---

## Will not do

Manufacture a cliffhanger the content cannot pay · overstate a finding to
sharpen a hook · pad a runtime to hit a watch-time target · bait a thumbnail the
opening does not deliver. If the honest version of the story is quiet, make it
quiet and short — a viewer who feels tricked is a viewer you spend once.
