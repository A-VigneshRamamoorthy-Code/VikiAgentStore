# Cards

> Dependencies: colors.md, radius.md, shadows.md, typography.md

## Core Specs

- Background: neutral-primary-soft
- Border: 1px, border-default color
- Radius: 12px (base)
- Shadow: shadow-xs

## Card Heading

- Desktop: 20px, medium weight, heading color
- Mobile: 16px, medium weight, heading color
- Never skip heading levels — the page hierarchy must logically arrive at the card heading level.

## Variants

### Static Card (`.card`, no interactivity)
- Background: neutral-primary-soft
- Border: 1px, border-default
- Radius: 12px
- Shadow: shadow-xs
- No hover styles. Non-interactive cards must NOT have hover background changes.

### Interactive Card (`.card`, clickable)
- Same base styles as static card
- Hover: border-default-strong border color
- Transition: colors
- Cursor: pointer

### Testimonial Card (`.card-testimonial`)
- Background: neutral-primary-soft
- Border: 1px, border-default
- Radius: 12px (base)
- Padding: 32px
- Layout: flex column, 24px gap
- Content: quote text (15px, body color, relaxed leading) + author row
- Author row: separated by top border (border-default), includes avatar (40px circle, brand-softer bg, initials), name (14px, medium, heading), and role/company (12px, body-subtle)
- No shadow by default — relies on border for definition

### Feature Card (`.card` with icon)
- Standard .card with 32px padding
- Icon container: 48×48px, rounded-default, colored background per intent (brand-softer, success-soft, warning-soft), ring-1 with matching subtle border, 24px bottom margin
- Heading: 16–20px, medium weight, heading color, 12px bottom margin
- Body: base size, body color

## Rules

- Background: neutral-primary-soft
- Border: 1px, border-default
- Radius: 12px
- Shadow: shadow-xs (static and feature cards only; testimonial cards omit shadow)
- Interactive hover: border-default-strong border color
- Non-interactive: no hover styles
