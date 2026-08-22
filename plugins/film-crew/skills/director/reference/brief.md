# The brief

Most requests arrive as *"make a video about X"*. That is a topic, not a brief,
and shooting it directly produces a Wikipedia summary read aloud.

Before you start the pipeline, get four things straight. Ask the human — you are
the only one in the crew who is allowed to.

---

## 1. The angle

"The Bhopal disaster" is a subject. *"The three warnings that were ignored"* is
a film. An angle is a claim or a question that the runtime is spent answering.

Without one, every scene is equally important, which means none of them is, and
the viewer leaves at ninety seconds.

**Ask:** what is the one thing someone should still know a week later?

## 2. Who it is for

Determines vocabulary, what you may assume, and how long the setup runs. A film
for people who already know the subject is a different film, not the same one at
a different speed.

## 3. Length, honestly

`--runtime 13m` is a budget, and the script is written to fit it. A thin topic
stretched to thirteen minutes is worse than a tight six.

If the topic will not fill the runtime, say so and shorten it. If it genuinely
needs more, that is what `--parts` is for.

## 4. Whether it is one story or several

`--parts 2` splits **one narrative** into two ordered episodes. Episode 2
assumes episode 1: it does not re-introduce the subject, and it does not stand
alone.

Two unrelated videos on a theme are two productions, not one with `--parts 2`.

---

## Shorts

`--shorts 3` cuts three vertical pieces from the moments the storyboard artist
marked `short_worthy`.

A Short is not a trailer and not a crop. It stands alone — its own hook in the
first second, its own payoff, its own call to action. The long video it came
from is the destination, not the context.

If the beat plan does not mark enough hooks, the answer is to mark more hooks in
the beat plan, not to invent windows at cut time.

---

## When the request is vague

Do not stall on it, and do not silently guess. Make the smallest reasonable
assumption, **state it**, and carry on:

> No angle was given, so I am taking it as *the three warnings that were
> ignored*, in the paper style, thirteen minutes, no Shorts. Say if you want a
> different line through it.

The one thing you may not assume is anything that touches truth or is
irreversible: an unsourceable claim, or whether to publish. Those are the
human's.

---

## Adapting existing material

`--source` takes an article, transcript or URL. The pipeline is the same, with
one difference that matters: **the source is not a ledger**. Claims in it still
need verifying, and the fact that something appeared in an article is not a
citation.

If you are adapting rather than researching, and the human does not want the
claims re-checked, that is `--skip research` — which marks the production
`unverified` and forbids describing it as sourced. That is the honest trade, and
it is recorded rather than assumed.
