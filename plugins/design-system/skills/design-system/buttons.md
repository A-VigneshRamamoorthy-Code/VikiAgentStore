# Buttons

> Dependencies: colors.md, radius.md, shadows.md

## Core Specs (every button except ghost and disabled)

- Radius: 8px (default) or 9999px for pills
- Border: 1px solid
- Shadow: shadow-xs
- Glint effect: Every button except ghost and disabled gets a combined box-shadow that layers the base shadow with an inset top-edge highlight and a subtle outer color glow:
  - var(--shadow-xs), inset var(--color-1-400) 0 6px 0px -5px, var(--color-1-700) 0 4px 10px -5px
- Font weight: 600 (semibold)
- Font: Lato
- Box sizing: border-box
- Transition: all 0.15s ease

## Sizes

| Size | Font size | Horizontal padding | Vertical padding |
|---|---|---|---|
| Extra small | 12px | 10px | 6px |
| Small | 13px | 14px | 8px |
| Base (default) | 14px | 16px | 10px |
| Large | 15px | 24px | 12px |
| Extra large | 16px | 24px | 14px |

## Variants

### Brand
- Background: linear gradient from brand to brand-strong (180deg)
- Border: transparent
- Text: white
- Hover: linear gradient from brand-strong to brand-strong; enhanced glow: var(--shadow-sm), inset var(--color-1-400) 0 6px 0px -5px, 0 4px 16px -4px rgba(108, 71, 255, 0.3)
- Focus ring: 4px, brand-medium color
- Glint: yes

### Secondary
- Background: neutral-primary-soft
- Border: border-default-medium
- Text: heading color
- Hover: neutral-secondary-medium background, border-default-strong border, heading text color
- Focus ring: 4px, neutral-tertiary color
- Glint: yes

### Tertiary
- Background: neutral-primary-soft
- Border: border-default
- Text: body color
- Hover: neutral-secondary-medium background, heading text color
- Focus ring: 4px, neutral-tertiary-soft color

### Success
- Background: success token
- Border: transparent
- Text: white
- Hover: success-strong background
- Focus ring: 4px, success-medium color

### Danger
- Background: danger token
- Border: transparent
- Text: white
- Hover: danger-strong background
- Focus ring: 4px, danger-medium color

### Warning
- Background: warning token
- Border: transparent
- Text: white
- Hover: warning-strong background
- Focus ring: 4px, warning-medium color

### Dark
- Background: dark token
- Border: transparent
- Text: white
- Hover: dark-strong background
- Focus ring: 4px, neutral-tertiary color

### Ghost (NO shadow, NO glint)
- Background: transparent
- Border: transparent
- Text: heading color
- Hover: neutral-secondary-medium background
- Focus ring: 4px, neutral-tertiary color
- No shadow, no glint effect

### Disabled (NO shadow, NO glint)
- Background: disabled token
- Border: border-default-medium
- Text: fg-disabled color
- Cursor: not-allowed
- No hover, no focus, no shadow, no glint

## Icons in Buttons

- Icon size: 16x16px
- Spacing: 8px gap between icon and label
- Layout: inline-flex, vertically centered
