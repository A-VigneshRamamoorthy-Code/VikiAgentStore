# Layout & Spacing

## Spacing Rhythm

Base unit: 8px. All spacing values should be multiples of 8px.

| Context | Value |
|---|---|
| Section vertical padding | 96px |
| Section header → content | 48px or 64px |
| Heading → paragraph | 16px |
| Container horizontal padding | 24px |
| Flex/grid row gap | 16px |
| Card grid gap | 24px |
| Wide component grid gap | 32px |
| Column layout gap | 48px |

## Container

Standard section container: max-width 1200px, centered, 24px horizontal padding.

Every major section wraps content in this container.

## Content Composition Order

Inside each section, follow this order:
1. Section label (optional — small category text above headline)
2. Heading (`h1`–`h3`)
3. Leading paragraph
4. Normal paragraph(s)
5. Lists, CTA links, or component grids

## Section Header Pattern

Each section header follows the label → headline → description pattern:

1. Section label (`.section-label`): 14px, font-weight 600, fg-brand color, 0.02em letter-spacing, 12px bottom margin. Includes an optional 16×16 icon to the left with 8px gap. Centered with justify-center for centered sections.
2. Headline (`h2`): standard heading scale (28px mobile → 36px tablet → 44px desktop), bold, heading color, 16px bottom margin.
3. Description (`.text-lead`): 20px, body color, max-width 70ch, centered with mx-auto for centered sections.
4. Bottom margin: 64px from header group to section content.

## Section Pattern

Each section has:
- 96px vertical padding
- A background color (alternate between neutral-primary-soft and neutral-secondary-soft)
- A centered container (max-width 1200px, 24px horizontal padding)
- A section header area (label + headline + description) with 64px bottom margin
- Section content below

## Hero Pattern

The hero section follows a centered layout:
1. Announcement badge: pill badge (rounded-full), border-default, neutral-secondary-soft background, xs text, with a pulsing brand dot indicator.
2. Headline: largest heading (36px → 48px → 64px), bold, with a gradient-highlighted keyword using bg-clip-text text-transparent bg-linear-to-r from-brand to-purple.
3. Lead paragraph: centered, max-width 2xl.
4. CTA buttons: two buttons centered (brand primary + secondary).
5. Trust bar: below CTAs, separated by a top border. Includes a label ("Trusted by...") and a row of company names/logos at 50% opacity, increasing to 70% on hover.

## Trust Bar / Logo Bar

- Class: .logo-bar
- Layout: flex, wrap, centered, 32px gap
- Default opacity: 50% — hover: 70%
- Separated from hero content by a top border (border-default) with 80px top margin and 48px top padding
- Label above: 14px, body-subtle color, font-medium, centered, 32px bottom margin

## Motion & Animation

- Prefer CSS-native: transition, animation, @keyframes. Use Motion library only when CSS cannot achieve the behavior.
- Prioritize high-impact orchestrated moments over scattered micro-interactions. A single well-sequenced page-load animation using staggered animation-delay delivers more perceived quality than many isolated effects.
- Reserve scroll-triggered and hover transitions for moments that reinforce hierarchy or reward attention.

## Backgrounds & Visual Depth

- Default to layered, atmospheric backgrounds rather than flat solid fills.
- Apply contextual treatments — gradient meshes, noise textures, geometric patterns, layered transparencies, dramatic shadows, decorative borders, grain overlays — that align with brand aesthetic.
- Every decorative element must serve a compositional purpose (depth, separation, or emphasis). No purely ornamental effects competing with content.

## Must

- All sections: consistent 96px vertical padding
- All containers: max-width 1200px, centered, 24px horizontal padding
- Section headers: use label → headline → description pattern with 64px bottom margin
- Consistent vertical rhythm, no crowded sections
- Layouts readable and properly spaced on both desktop and mobile
