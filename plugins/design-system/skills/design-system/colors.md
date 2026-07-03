# Color Tokens

> All values are CSS custom properties defined in globals.css. Reference them by token name. They handle light/dark mode automatically.

## Background Tokens

### Neutral
| Token | Light | Dark |
|---|---|---|
| neutral-primary-soft | #FFFFFF | #111116 |
| neutral-primary | #FFFFFF | #0D0D12 |
| neutral-primary-medium | #FFFFFF | #1A1A21 |
| neutral-primary-strong | #FFFFFF | #2C2C35 |
| neutral-secondary-soft | #FAFBFC | #111116 |
| neutral-secondary | #FAFBFC | #0D0D12 |
| neutral-secondary-medium | #F2F2F5 | #1A1A21 |
| neutral-secondary-strong | #F2F2F5 | #2C2C35 |
| neutral-tertiary-soft | #EDEDF0 | #111116 |
| neutral-tertiary | #EDEDF0 | #1A1A21 |
| neutral-tertiary-medium | #EDEDF0 | #2C2C35 |
| neutral-quaternary | #DFDFE3 | #2C2C35 |
| quaternary-medium | #DFDFE3 | #3F3F48 |
| gray | #C8C8D0 | #3F3F48 |

### Brand
| Token | Light | Dark |
|---|---|---|
| brand-softer | #F4F0FF | #1A0F36 |
| brand-soft | #E8DEFF | #2D1B69 |
| brand | #6C47FF | #7C5CFF |
| brand-medium | #D4C4FF | #2D1B69 |
| brand-strong | #5535DC | #6C47FF |

### Status
| Token | Light | Dark |
|---|---|---|
| success-soft | #ECFDF5 | #052E1C |
| success | #059669 | #10B981 |
| success-medium | #D1FAE5 | #064E3B |
| success-strong | #047857 | #059669 |
| danger-soft | #FEF2F2 | #450A0A |
| danger | #DC2626 | #EF4444 |
| danger-medium | #FEE2E2 | #7F1D1D |
| danger-strong | #B91C1C | #DC2626 |
| warning-soft | #FFFBEB | #451A03 |
| warning | #D97706 | #F59E0B |
| warning-medium | #FEF3C7 | #78350F |
| warning-strong | #B45309 | #D97706 |

### Button Glint (CSS custom properties, used for the glint box-shadow effect)
| Variable | Light | Dark |
|---|---|---|
| --color-1-400 | rgba(255,255,255,0.15) | rgba(255,255,255,0.08) |
| --color-1-700 | rgba(0,0,0,0.08) | rgba(0,0,0,0.15) |

### Utility
| Token | Light | Dark |
|---|---|---|
| dark | #131316 | #131316 |
| dark-strong | #0D0D12 | #2C2C35 |
| disabled | #F2F2F5 | #1A1A21 |

### Accent
| Token | Value (same both modes) |
|---|---|
| purple | #A855F7 |
| sky | #0EA5E9 |
| teal | #14B8A6 |
| pink | #EC4899 |
| cyan | #06B6D4 |
| fuchsia | #D946EF |
| indigo | #6366F1 |
| orange | #FB923C |

## Text Color Tokens

### Base
| Token | Light | Dark |
|---|---|---|
| white | #FFFFFF | #FFFFFF |
| black | #131316 | #131316 |
| heading | #131316 | #F5F5F7 |
| body | #5E5F6E | #9394A1 |
| body-subtle | #747686 | #9394A1 |

### Brand
| Token | Light | Dark |
|---|---|---|
| fg-brand-subtle | #D4C4FF | #2D1B69 |
| fg-brand | #6C47FF | #A78BFF |
| fg-brand-strong | #5535DC | #D4C4FF |

### Status
| Token | Light | Dark |
|---|---|---|
| fg-success | #059669 | #065F46 |
| fg-success-strong | #047857 | #10B981 |
| fg-danger | #DC2626 | #EF4444 |
| fg-danger-strong | #991B1B | #FCA5A5 |
| fg-warning-subtle | #D97706 | #F59E0B |
| fg-warning | #92400E | #FCD34D |
| fg-disabled | #9CA3AF | #6B7280 |

### Informational / Accent
| Token | Light | Dark |
|---|---|---|
| fg-yellow | #EAB308 | #FACC15 |
| fg-info | #3730A3 | #A5B4FC |
| fg-purple | #7C3AED | #A78BFF |
| fg-purple-strong | #6D28D9 | #D4C4FF |
| fg-cyan | #0891B2 | #06B6D4 |
| fg-indigo | #6366F1 | #818CF8 |
| fg-pink | #EC4899 | #F472B6 |
| fg-lime | #65A30D | #84CC16 |

## Border Color Tokens

| Token | Light | Dark |
|---|---|---|
| border-dark | #1F1F25 | #3F3F48 |
| border-buffer | #FFFFFF | #0D0D12 |
| border-buffer-medium | #FFFFFF | #1A1A21 |
| border-buffer-strong | #FFFFFF | #2C2C35 |
| border-muted | #FAFBFC | #111116 |
| border-light-subtle | #F2F2F5 | #111116 |
| border-light | #F2F2F5 | #1A1A21 |
| border-light-medium | #F2F2F5 | #2C2C35 |
| border-default-subtle | #E8E8EC | #111116 |
| border-default | #E8E8EC | #1F1F25 |
| border-default-medium | #E8E8EC | #2C2C35 |
| border-default-strong | #E8E8EC | #3F3F48 |
| border-success-subtle | #A7F3D0 | #064E3B |
| border-success | #059669 | #047857 |
| border-danger-subtle | #FECACA | #7F1D1D |
| border-danger | #DC2626 | #DC2626 |
| border-warning-subtle | #FDE68A | #78350F |
| border-warning | #D97706 | #F59E0B |
| border-brand-subtle | #D4C4FF | #2D1B69 |
| border-brand-light | #7C5CFF | #7C5CFF |
| border-brand | #6C47FF | #A78BFF |
| border-dark-subtle | #1F1F25 | #2C2C35 |
| border-purple | #A855F7 | #A855F7 |
| border-orange | #FB923C | #FB923C |

## Semantic Usage Rules

- Page/section backgrounds: neutral-primary-soft (default), neutral-secondary-soft (alternating)
- Primary buttons: brand background
- Headings: heading text color
- Body text: body text color
- CTA links: fg-brand text color
- Default borders: border-default
- Status borders match intent: success → border-success, danger → border-danger, warning → border-warning
- Disabled: disabled background + fg-disabled text

## Prohibited

- No raw hex/rgb values in component code — always use design tokens
- No brand text color for long-form paragraphs
- No accent text tokens (fg-purple, etc.) for body copy or navigation
- No brand/accent backgrounds for large layout surfaces (pages, sections) unless it's a hero/campaign area
- No manual light/dark value swapping — let the CSS custom properties handle it
