# Duration model

> The register is not yours to choose. `brief.register` is set by the director
> from the runtime, and it selects the band below. Pass it through to
> `hookcheck.py --register`.

Runtime is decided before the writing, and the writing is cut to fit it. Never
the other way round.

---

## The arithmetic

```
words = target_seconds × wpm ÷ 60
```

`wpm` here is **gross** — measured across the finished read, pauses and breaths
included. It is not how fast the voice moves; it is how much script a minute
absorbs.

| Register | Gross wpm | Feel |
|---|---|---|
| Memorial / atrocity / grief | 90–100 | Long rests. Silence carries meaning |
| Reflective essay | 100–120 | Room to think between sentences |
| Explainer, science, how-it-works | 115–130 | Brisk, still unhurried |
| **Investigative documentary** | **150–170** | **The default for long-form** |
| Promo / trailer | 130–150 | Energy over comprehension |
| Social vertical | 150–180 | Captions doing half the work |

The investigative band is **measured, not assumed**. Against a 29-minute
reference documentary with 24 million views, the body chapters run:

| chapter | seconds | words | wpm |
|---|---|---|---|
| The Hijacking | 257 | 706 | 164.8 |
| The Manhunt Begins | 185 | 501 | 162.5 |
| Follow the Money | 262 | 674 | 154.4 |
| A Leap of Faith | 372 | 1084 | 174.8 |
| The Suspects | 559 | 1544 | 165.7 |

A slow, hushed read is what people *think* documentary sounds like. What
actually holds an audience for half an hour is a brisk, level delivery that
never dawdles on a sentence — the gravity comes from *what is said*, not from
saying it slowly.

**Do not compensate for a long script by raising `wpm`.** Pace is a design
decision; word count is the variable. If it does not fit, cut content.

### The pace curve

One `wpm` for a whole film is a simplification, and the reference does not do
it. Measured across the same documentary:

| section | wpm | why |
|---|---|---|
| cold open | ~58 | mostly archive and silence; the narrator is barely in it |
| body | 155–175 | level, unhurried, never slow |
| outro | ~104 | deliberate deceleration — the film is handing the question back |

Budget the **body** at the register's wpm and let the open and the close run
long. An outro written at body pace reads as a summary; the same words at 105
wpm read as a conclusion.

### Budget table

At 100 wpm:

| Target | Words | Lines (~11 words) | Chapters |
|---|---|---|---|
| 0:30 | 50 | 5–7 | 1 |
| 1:00 | 100 | 9–12 | 2 |
| 3:00 | 300 | 27–33 | 3–4 |
| 5:00 | 500 | 45–55 | 5–6 |
| 10:00 | 1000 | 90–110 | 8–12 |
| 20:00 | 2000 | 180–220 | 12–16 |

Tolerance is ±8 % by default. Tighter than that is false precision — the read
varies by voice — and looser than that misses the slot.

### Where the tolerance goes

A 10-minute target with a 1 000-word budget has roughly ±80 words of slack.
Spend it on **silence around the hardest material**, not on an extra sentence.
Casualty figures, verdicts and reversals are where the slack belongs.

---

## Act structure by length

### Under 60 seconds

One idea. Establish (0–20 %), complicate (20–55 %), move (55–85 %), resolve
(85–100 %). See the paper style
[authoring guide](../../style-paper/reference/authoring-guide.md#4-shape-the-arc).

### 3–6 minutes

Five movements: **hook · context · event · consequence · close.** Context is the
one that bloats — it is allowed about 20 % and no more. Viewers came for the
event.

### 8–20 minutes — chaptered

Long form needs visible joints, because attention resets at each one.

| Chapter | Share | Job |
|---|---|---|
| Cold open | 5–8 % | The single sentence the whole thing is about. No context yet |
| Setup | 10–15 % | Only the context needed to follow the next chapter |
| Escalation | 35–45 % | The event, in sequence, one location or phase per chapter |
| Turn | 10–15 % | The thing that changed the outcome — usually a person |
| Consequence | 15–20 % | What it cost; what was done about it |
| Close | 5–8 % | Where it stands now. One image, then stop |

Rules that hold at every length:

- **One chapter, one job.** If a chapter needs "and also", it is two chapters.
- **Chapters run 45–90 s.** Under 45 s it reads as a bump; over 90 s attention
  drifts with no seam to catch it.
- **Chronology is the default for events.** Thematic ordering is a choice that
  must earn itself, and it usually costs clarity in the escalation.
- **The close is not a summary.** Summarising is what the viewer just did.

---

## Timecoding chapters

Head each chapter with its intended start:

```markdown
## [01:45] 21:20 — the station
```

`scriptcheck` sums the word counts, converts to seconds at `wpm`, and warns when
a chapter's real start drifts more than ±12 s from its heading. Rewrite the
heading or rebalance the chapter — either is fine, but do not ship a script
whose own timecodes are fiction. They are what the storyboard and the edit are
built against.

---

## Line shape

- **6–18 words.** Over 18 and the voice cannot land it in one breath; the
  linter warns.
- **One idea per line.** Two ideas in a line means the second gets no beat.
- **Put the payload last.** "By the third day, the river had risen four metres"
  lands; "The river had risen four metres by the third day" does not.
- **A number gets its own line** whenever it matters. Numbers sharing a line
  with anything else are numbers the viewer will not retain.

---

## Reading it back

The word count is a proxy. Before shipping, read the script aloud against a
timer. If your read comes in more than 10 % under target, you have written a
script that *scans* like documentary and *reads* like news — the fix is more
silence, not more words.
