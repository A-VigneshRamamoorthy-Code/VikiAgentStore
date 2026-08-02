---
name: minimal-ux
description: >
  Visual and interaction design language for a polished editorial product site,
  with light and dark themes, softly layered physical shadows, Switzer and Antonio
  typography, a constant trailing cursor companion, and GSAP-driven 3D coverflow.
  Use when building an app-studio, portfolio, or product-showcase experience.
license: MIT
metadata:
  author: Copilot Research
  version: "1.1.0"
---

# Sidfz Design System — Agent Instructions

Apply the current Solo Leap implementation of the visual language derived from `portfolio.sidfz.tech`. Build an editorial canvas with theme-aware tokens, softly lifted product surfaces, restrained typography, and deliberate GSAP motion.

## Before Writing Any Code

1. Read both module files to understand the visual language and interaction choreography.
2. Load Switzer weights 300–700 and Antonio weights 500–700 before rendering the interface.
3. Install the theme boot script before first paint; do not rely on a post-mount theme effect.
4. Keep the native OS cursor. The custom dot is only a fixed-size trailing companion.
5. Implement reduced-motion branches alongside every programmatic animation.

## Module Index

- [visual.md](visual.md) — Light and dark token palettes, first-paint theme resolution, typography, shadows, surfaces, and product imagery.
- [interaction.md](interaction.md) — Constant trailing cursor, card and detail behavior, 3D coverflow, app-flight geometry, reduced motion, and React correctness rules.
