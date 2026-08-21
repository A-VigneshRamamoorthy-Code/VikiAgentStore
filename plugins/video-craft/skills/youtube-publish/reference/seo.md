# SEO: description, chapters and tags

## The one thing to understand

**YouTube indexes text, not speech.** Auto-captions exist but are unreliable
for many languages and are not what ranking is built on. If a concept is spoken
but never written, the video is invisible for that concept.

This has a sharp consequence for non-English videos: a Tamil video with a
Tamil-only description cannot be found by anyone typing
"tamil nadu assembly highlights", which is a far larger group than those typing
the same words in Tamil. The fix is not translation of the whole description —
it is a **dedicated block in the second language**.

## Description structure

Ordered by what actually reads it:

```
1. Lead (1–2 lines)      ← shown in search, collapsed panel, and share cards
2. Chapters              ← starts at 0:00
3. Second-language block ← summary + topics
4. Topics / keywords
5. Source and credit
6. Call to action
7. Hashtags (max 3 useful ones)
```

**The first two lines carry the most weight.** They must repeat the title's
main keywords — `seocheck.py` warns when they do not.

## Chapters

- The list must start at exactly `0:00`, or YouTube renders no chapters at all
  and silently ignores every other timestamp.
- Minimum three chapters, each at least 10 seconds.
- Offsets must be measured from the **rendered files**, never from the edit
  plan. Clip lengths change whenever cuts are re-snapped, and a description
  full of timestamps that are three seconds off is worse than none.
  `metadata.py` probes the files for this reason.

Bilingual chapter lines cost almost nothing and index both languages:

```
0:00 தொடக்கம் | Intro
0:12 சூடான வாக்குவாதம் | Heated exchange
```

## Tags

Tags are the weakest of the three signals — they mainly help with spelling
variants, transliterations and names the title cannot fit. Do not agonise, but
do budget.

- **All tags together must fit 500 characters.** This is a total, not per tag.
- Order matters here only because `budget_tags()` fills highest-priority first
  and drops the tail, so put the terms you most want indexed in `primary`.
- Include: the topic in both languages, transliterations, the institution's
  name, the place, and any names in the video.
- Exclude: generic words like "video", "viral", "trending". They compete with
  the entire platform and describe nothing.

## Making a non-English video discoverable in English

Do all four:

1. **Keyword tail on the title** in the second language.
2. **A labelled summary block** — a real paragraph, not keyword soup. Eight or
   more Latin-script words is the bar `seocheck.py` checks for.
3. **Bilingual chapter labels.**
4. **Latin-script tags** alongside the native ones.

`seocheck.py` flags a description that contains a non-Latin script but no
substantial Latin text, and a tag list with no Latin entries.

## What does not help

- Keyword stuffing the description. It reads as spam to humans, and duplicate
  terms add nothing after the first occurrence.
- More than about three hashtags — YouTube ignores the excess.
- Copying a competitor's tags. You cannot see them accurately, and matching
  them would only place you against a stronger video for the same query.
