# Content & Grid System

> Dependencies: layout.md, typography.md

## Containers

| Type | Max width | Horizontal padding |
|---|---|---|
| Standard | 1280px | 16px |
| Internal (reading) | 768px | — (45–75 char line length) |
| Section (`.container-section`) | 1200px | 24px |

## Vertical Padding

| Breakpoint | Vertical padding |
|---|---|
| Mobile | 32px |
| Tablet (≥768px) | 48px |
| Desktop (≥1024px) | 64px or 96px for hero/feature sections |

## Grid System

Mobile-first with flexible desktop configurations.

| Context | Gap |
|---|---|
| Standard content/cards | 24px |
| Feature icon grid | 32px horizontal, 48px vertical |
| Compact widgets/metadata | 16px |
| Testimonial cards | 24px |

### Responsive Columns

| Breakpoint | Columns |
|---|---|
| Mobile (default) | 1–2 |
| Small/Tablet (≥640px) | 2–4 |
| Desktop (≥1024px) | 3–12 |

Full support for 6, 7, 8, 9+ column grids where needed.

### Common Grid Configurations

| Section type | Mobile | Tablet | Desktop |
|---|---|---|---|
| Bento features | 1 col | 3 col with spans | 3 col with spans |
| Capability list (icon + text) | 1 col | 2 col | 3 col |
| Pricing cards | 1 col | 2 col | 2 col (max-w 4xl) |
| Testimonials | 1 col | 2 col | 3 col |
| Integration logos | 2 col | 3 col | 6 col |
| Tool badges | 2 col | 4 col | 4 col |

## Breakpoints

| Name | Width |
|---|---|
| Small | 640px |
| Medium | 768px |
| Large | 1024px |
| Extra large | 1280px |
| 2x Extra large | 1536px |

## Page Section Order (Landing Page)

1. Navigation (sticky header)
2. Hero (badge, headline, lead, CTAs, trust bar)
3. Product showcase / visual demo
4. Primary features (bento grid)
5. Capabilities list (icon + title + description grid)
6. Pricing
7. Testimonials
8. Integrations / framework support
9. CTA band (final conversion section)
10. Footer

## Rules

- Always design mobile-first
- Use layout shifts (column → row) to accommodate horizontal space
- Lists: 24px indentation, 8px vertical gap between items
- Body copy: 16px, 1.6 line-height
- All interactive links follow brand underline/hover protocol
- Section headers always use the label → headline → description pattern (see `layout.md`)
