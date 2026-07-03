# Narrative Structure

A launch video should feel like a tiny product story, not a raw screen recording.

```text
0s                                                        ~20–35s target
| intro |------ tightened demo + captions ------| outro CTA | end-card |
        ^ feature 1   ^ feature 2   ^ feature 3
```

---

## Structure

| Phase | Purpose | Typical length |
|-------|---------|----------------|
| Intro card | Establish brand, promise, tone | 2.5–3s |
| Tightened demo | Prove the product works; show best moments | 15–25s |
| Outro CTA | Tell viewers what to do next | 3–6s |
| Logo + name end-card | Leave a clean brand memory | 1–2s or part of outro |

Aim for a punchy **~20–35s** total unless the user asks for a longer walkthrough.

---

## Intro card

Use `intro.enabled`, `intro.duration`, `intro.title`, and `intro.subtitle`.

Good intro copy:
- product name,
- short tagline,
- no long paragraphs,
- tokens are OK: `{brand.name}`, `{brand.tagline}`.

---

## Demo section

The demo is assembled from `segments`:

```json
"segments": [
  { "start": 2.0, "end": 8.5 },
  { "start": 13.0, "end": 21.0 }
]
```

Choose segments that:
- show visible product value quickly,
- include the moment before and after each result,
- remove dead air, loading, setup, repeated clicks, and long typing,
- avoid abrupt context jumps where possible,
- have clean cut points for `transitions` to hide.

If `segments` is empty, the whole input is used.

---

## Captions

Captions are feature callouts in `captions`. They should sit in the lower third, away from important UI, with one active at a time.

Guidelines:
- Use **3–6 captions**.
- Keep each caption short: 4–9 words is usually enough.
- Time to **OUTPUT seconds** after the assembled video timeline.
- Hold most captions for about 2s.
- Caption what is on screen now, not what happened earlier.
- Avoid blocking buttons, charts, code, or the cursor path.

Good:

```json
{ "text": "Summarize work in one click", "start": 5.4, "end": 7.6 }
```

Too vague:

```json
{ "text": "A better way to do everything", "start": 5.4, "end": 7.6 }
```

---

## Outro + end-card

Use `outro.enabled`, `outro.headline`, `outro.cta_text`, `outro.link`, `outro.footnote`, `outro.duration`, and `outro.end_card`.

Outro content should be concrete:
- closing headline,
- optional CTA button,
- optional URL chip,
- optional footnote,
- final logo + product name when `outro.end_card` is true.

Never invent a link or claim. If no CTA is provided, use a clean closing headline and end-card only.

---

## Pacing checklist

- Does the product value appear in the first 5–8s after intro?
- Is every pause earning its time?
- Are captions readable before they leave?
- Are there no overlapping captions?
- Do transitions hide cuts without calling attention to themselves?
- Does the video end on a stable, branded frame?
