# Titles

The title does two jobs at once, for two different readers: a human deciding
whether to click, and an index deciding when to show the video. Write for the
human first, because a title that ranks and is not clicked stops ranking.

## Anatomy

```
<hook>  |  <keyword tail>  |  <second keyword tail>
```

- **Hook** — the reason to click. Comes first and is never truncated.
- **Keyword tails** — the searchable phrasing, appended only while it fits.

`metadata.py` implements exactly this: it starts with the hook and adds each
tail only if the result stays inside 100 characters. Tails are what gets
dropped, never the hook.

Roughly the first 60–70 characters survive in search and on mobile. Anything
past that is working for the index, not the reader.

## The documentary register

The anatomy above is for content whose value is a **claim**. Investigative
documentary sells an **investigation**, and its titles are correspondingly
plain. The reference, at 24 million views:

> **The Search For D. B. Cooper**

Five words. No number, no colon, no superlative, no capitals, no year, no
question mark, no keyword tail. It promises a search — not an answer — which is
exactly what the film delivers, and is why the comments argue about suspects
instead of complaining about clickbait.

| rule | why |
|---|---|
| **Name the subject plainly** | the entity *is* the search term; no tail needed |
| **Promise the process, not the payoff** | "The Search For…", "The Hunt For…", "What Happened To…" |
| **No superlatives, no ALL-CAPS, no emoji** | each one trades credibility for a click, and this genre is bought with credibility |
| **Never promise a resolution you do not have** | the film ends unresolved; a title saying *SOLVED* would earn one angry view and no session |
| **Under ~35 characters** | it never truncates anywhere, on any surface |

The keyword tail is unnecessary here because the *tags* carry it, and the tags
in the reference are pure entities — `db cooper`, `flight 305`, `fbi`,
`tina mucklow`, `florence schaffner`, `tina bar` — the names of people, places
and objects in the film, not genre words like "documentary 2024".

## Hook formulas that work for proceedings

| Formula | Example shape |
|---|---|
| Named confrontation | "X vs Y over Z" |
| The concrete number | "7 audits, zero findings" |
| The unanswered question | "Who signed off on it?" |
| The reversal | "The minister's own figures said otherwise" |
| The moment | "The exchange that stopped the session" |

Prefer whichever is **true and specific**. "Shocking scenes in the assembly" is
a hook with no information; "Opposition walks out mid-answer" is a hook that is
also a fact.

## Two languages in one title

A video spoken in one language is watched by an audience that searches in two.
The pattern that works:

```
<hook in the spoken language> | <topic in English> | <place/session in English>
```

The hook stays in the language of the video, because that is who clicks. The
tail is English, because that is how a much larger group searches. This is why
`title_tails` exists in the spec.

Do **not** translate the hook into the tail — a duplicated sentence wastes the
budget. The tail should add *searchable nouns* the hook does not contain.

## Rules

1. **Never promise what the video does not deliver.** For assembly content this
   is not just ethics: a title claiming a fight over footage of applause gets
   the click and loses the retention, and the second failure is the one the
   algorithm punishes.
2. **Front-load the distinguishing word.** Not "Highlights from the session on
   the budget" but "Budget session: …".
3. **No ALL CAPS blocks.** They read as spam and are not weighted more heavily.
4. **One idea.** A title carrying two claims sells neither.
5. **Numbers and names beat adjectives.** "Zero" and a surname outperform
   "shocking" and "massive".

## Checking

`seocheck.py` warns when the title is under 30 characters (wasted index space)
and when the title's keywords never reappear in the opening lines of the
description, which is where they most need to be repeated.
