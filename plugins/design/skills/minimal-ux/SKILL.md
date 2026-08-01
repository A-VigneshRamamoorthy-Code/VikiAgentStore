---
name: minimal-ux
description: >
  Visual and interaction design language inspired by portfolio.sidfz.tech.
  Features a light, editorial/agency aesthetic with heavy pill radii, physical shadows,
  Switzer & Antonio typography, and advanced GSAP/Lenis animations, including
  custom cursors, page morphs, and 3D scroll experiences. Use when building a
  highly interactive, modern portfolio or agency site.
license: MIT
metadata:
  author: Copilot Research
  version: "1.0.0"
---

# Sidfz Design System — Agent Instructions

This skill provides the visual design language and interaction specifications derived from `portfolio.sidfz.tech`. When applied, the UI should follow the light canvas style, deep shadows, and complex GSAP-driven interactions detailed below.

## Before Writing Any Code

1. Read both module files to understand the visual language and interaction choreography.
2. Ensure you have the necessary fonts (Switzer Medium/Semibold/Light, Antonio, and a serif like EB Garamond for special sections). Note that Switzer weight 400 is actually Medium (500).
3. The design is heavily dependent on interactions (custom cursors, route morphs). Implement these with GSAP and React when generating the UI.

## Module Index

- [visual.md](visual.md) — Color palette, typography scale, borders, and general visual design.
- [interaction.md](interaction.md) — Hover states, focus rings, scroll animations, 3D laptop sequences, custom cursors, and responsive behavior.
