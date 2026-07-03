# Modals

> Dependencies: colors.md, radius.md, shadows.md, buttons.md, inputs.md

## Core Specs

### Overlay (Backdrop)
- Fixed, covers full screen
- Z-index: 40
- Background: black at 40% opacity
- Backdrop blur: small amount

### Content Container
- Background: neutral-primary
- Radius: 12px (base)
- Shadow: shadow-xl
- Padding: 24px

## Anatomy

### Header
- Bottom border: border-default
- Top corners rounded (12px)
- Title: 20px, bold weight, heading color
- Close button: Ghost variant from buttons.md, 6px padding

### Body
- Vertical padding: 24px
- Vertical spacing between elements: 24px
- Text: 16px, 1.6 line-height, body color

### Footer
- Top border: border-default
- Bottom corners rounded (12px)

## Variants

### Default (Information)
Standard header + body + footer with primary/secondary action buttons.

### Pop-up (Confirmation)
Centered text, prominent icon, reduced padding:
- Body: 24px padding, text centered
- Icon: centered, 16px bottom margin, 48x48px, gray color

### Form Modal
Body contains inputs following inputs.md. Vertical spacing between form elements: 16px.

## Rules

- Backdrop covers full screen with fixed positioning
- Content: neutral-primary background, 12px radius, shadow-xl
- Header/Footer separated by border-default borders
- Close button must be present and functional
- Accessibility: role="dialog", implement focus trap in code
- Dark mode automatic via token system
