# Motion Design

This skill applies the `motion-design` skill to launch videos. Pick one `personality` and keep it consistent across intro, captions, transitions, outro, and end-card.

---

## Personality table

| `personality` | Feeling | Easing | Durations | Overshoot | Use when |
|---------------|---------|--------|-----------|-----------|----------|
| `playful` | fun, friendly, bouncy | `ease-out-back` | 150–300ms | 10–20% | consumer, creative, delightful products |
| `premium` | elegant, calm, refined | `cubic-bezier(0.4,0,0.2,1)` | 350–600ms | 0% | luxury, polished, minimal launches |
| `corporate` | clean, clear, trustworthy | `cubic-bezier(0.2,0,0,1)` | 200–400ms | 0–3% | SaaS, dashboards, professional tools |
| `energetic` | fast, bold, exciting | `ease-out-expo` | 100–250ms | 15–30% | launches, social cuts, high-energy demos |

Config field: `personality`.

---

## Entrance vs exit

Directional rules:
- Entrances decelerate: fast start, gentle landing.
- Exits accelerate: gentle start, fast departure.
- Entrances are **30–50% longer** than exits.
- Important text should never be opacity-only; combine position + scale + fade.

Example feel:

```text
caption enter: slide up + scale 0.96 → 1.03 → 1.00 + fade in
caption exit: slight lift or drop + fade out, ~40% shorter
```

---

## Caption pop-in system

Config fields: `captions`, `brand.primary`, `personality`.

Each feature caption should:
1. slide up from the lower third,
2. scale in with a small overshoot based on `personality`,
3. fade from 0 → 1,
4. show a small accent bullet/mark using `brand.primary`,
5. hold for ~2s,
6. accelerate out before the next caption.

Keep only one caption active. If two moments are close together, shorten text or shift timing rather than overlapping.

---

## Transitions

Config field: `transitions`.

| Value | Feel | Best for |
|-------|------|----------|
| `wipe` | designed, energetic, masks jumps | most launch demos |
| `dissolve` | soft, calm, premium | slower or elegant demos |
| `cut` | direct, fast, editorial | very tight footage with clean cut points |

Transitions should hide edits, not become the story. If the cut feels confusing, choose better `segments` first.

---

## Three motion layers

Every scene should have depth:

| Layer | In this skill | Config tie-in |
|-------|---------------|---------------|
| Primary | intro title, active caption, CTA, end-card logo | `intro`, `captions`, `outro` |
| Secondary | accent bullet, button/chip motion, logo bug | `brand.primary`, `logo_bug`, `outro.cta_text` |
| Ambient | gradient movement, subtle background pulse, music/SFX | `brand.bg_gradient`, `music`, `sfx` |

If the video feels flat, add secondary/ambient motion. If it feels noisy, reduce amplitude and simultaneous movement.

---

## The 1/3 rule

Use the 1/3 rule to keep motion polished:

- No element should travel more than **1/3 of the frame** without changing direction, easing, or settling.
- With 3+ elements, no more than **1/3 should be actively moving** at the same time.
- Caption motion should be small and readable; the screen recording is the hero.

---

## Practical timing

| Element | Typical duration |
|---------|------------------|
| Caption enter | 180–420ms, by personality |
| Caption exit | 100–260ms, faster than enter |
| Wipe accent | 250–500ms |
| Intro title reveal | 400–900ms |
| CTA button settle | 200–450ms |
| Ambient pulse | 2–6s loop |

Quality test: the viewer should notice the feature, not the animation mechanics.
