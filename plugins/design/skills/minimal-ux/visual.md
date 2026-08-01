[Turn 0]
## Summary

`https://portfolio.sidfz.tech` is a Vite + React 19.2.5 SPA (`portfolio_v2`) that ships a single ~120 KB compiled stylesheet at `/assets/index-CmQ7yN4u.css` and one JS bundle at `/assets/index-BDHMsrRa.js`. The HTML shell is empty (`<div id="root">`), so **all design information lives in the compiled CSS**, which I read end-to-end (5 paginated fetches, char 0 → ~119k). The design language is a **light, near-white editorial/agency aesthetic**: `#fafafa` page canvas, `#fff` card surfaces, `#1a1a1a`/`#111` text, hairline `rgba(0,0,0,0.08)` dividers, heavy use of **pill (999px) radii**, **layered multi-stop "physical" shadows** on dark buttons, and a custom **Switzer** typeface throughout, with **Antonio** (condensed, uppercase, weight 900) used exclusively for the About section and the giant footer wordmark. There is a declared design-token layer (`:root` with `--color-*`, `--text-*`, `--space-*`) that is **largely unused by the actual components**, which hardcode px values — I document both.

No public source repo exists (searched GitHub for `"portfolio_v2" "Switzer"` — only unrelated results: `OpenOLAT/OpenOLAT`, `kleva-j/portfolio_v3`, `Forestierr/portfolio`).

---

## Files investigated

| Asset | Purpose |
|---|---|
| `https://portfolio.sidfz.tech/` | Empty SPA shell; `<title>portfolio_v2</title>`, favicon `/avatar.webp` |
| `https://portfolio.sidfz.tech/assets/index-CmQ7yN4u.css` | **Complete stylesheet** — all tokens, components, breakpoints |
| `https://portfolio.sidfz.tech/assets/index-BDHMsrRa.js` | React 19.2.5 bundle (minified, ~1.5–3 MB; contains ASCII-art animation frame data) |
| `/assets/Switzer-Medium-RFqtjt7E.otf` | Switzer @ weight 400 |
| `/assets/Switzer-Semibold-BL4pOLMt.otf` | Switzer @ weight 600 |
| `/assets/Switzer-Light-BADCwite.otf` | Registered as a **separate family** `"Switzer Light"` @ weight 300 |

---

# 1. Color Palette

### 1a. Declared tokens — primary `:root` (css char ~700–1100)

```css
:root{
  --color-bg:            #fff;
  --color-bg-secondary:  #f5f5f5;
  --color-text:          #1a1a1a;
  --color-text-muted:    #6b6b6b;
  --color-accent:        #e8191a;   /* red */
  --color-border:        #1a1a1a;
  --color-border-light:  #e0e0e0;
  --border:       1px solid var(--color-border);
  --border-light: 1px solid var(--color-border-light);
  --radius: 2px;
}
```

### 1b. Declared tokens — second `:root` override (css char ~2600–2900)

```css
:root{
  --nav-height:     60px;
  --black:          #050505;
  --white:          #fafafa;
  --content-width:  120ch;
  --accent:         #f2330d;   /* orange-red — differs from --color-accent */
}
body{ background: var(--white); min-height:100vh; overflow-x:hidden; }
```

> ⚠️ **Two conflicting token sets.** The second `:root` wins for `body { background }` → the real page canvas is **`#fafafa`**, not `#fff`. `--radius: 2px` and `--color-accent: #e8191a` are effectively dead (only `#e8191a` survives on `.services__button-avatar`).

### 1c. **Actual palette in use** (extracted from component rules)

**Surfaces / backgrounds**
| Token (proposed) | Value | Used by |
|---|---|---|
| `bg/canvas` | `#fafafa` | `.hero`, `.work`, `.work-testimonial`, `.services`, `.pricing`, `.faq`, `.workpage`, `.projectpage`, `.legalpage`, `.storypage` |
| `bg/canvas-alt` | `#fbfbfb` | `.about` |
| `bg/surface` | `#ffffff` | `.hero__badge`, `.pricing__card--info`, `.pricing__card--price`, `.faq__item` (≥990px), `.contact-cta`, `.projectpage__tag`, `.contact-panel__sheet`, `.services__stack-icon` |
| `bg/surface-sunken` | `#f0f0f0` | `.pricing__plans-wrapper` |
| `bg/media-placeholder` | `#f0f0ee` / `#ececeb` / `#e7e7e1` | `.workpage__card-media`, `.projectpage__media`, `.about__capabilities-preview.is-visible` |
| `bg/portrait` | `#d9dbd3` | `.about__portrait` |
| `bg/inverse` | `#0a0a0a` | `.footer`, `.pricing__single`, `.laptop-screen-terminal` |
| `bg/inverse-elevated` | `#1a1a1a` | `.footer__social-pill`, `.footer__social-btn`, `.projectpage__author-avatar--initial` |
| `bg/black` | `#000` / `#050505` | all primary buttons, `.services__list-icon`, `.pricing__card-floating`, `.custom-cursor` |
| `bg/glass` | `rgba(255,255,255,0.5)` + `blur(5px)` | `.navbar`, `.bottombar` |
| `bg/glass-mobile-menu` | `rgba(255,255,255,0.42)` + `blur(18px)` | `.navbar--mobile-open` |

**Text**
| Token | Value | Usage |
|---|---|---|
| `text/primary` | `#1a1a1a` | default body, headings, card titles, nav links |
| `text/primary-alt` | `#111` | `.projectpage__*`, `.contact-cta__heading`, `.faq__card-desc` |
| `text/heading-about` | `#2c2c2e` / `#2e2e30` | `.about__title`, `.about__capabilities-title`, `.about__eyebrow` |
| `text/secondary` | `#545454` | `.hero__subtext`, `.projectpage__meta-label`, `.bottombar__sub`, `.work-testimonial__role` |
| `text/secondary-alt` | `#444` / `#4a4a4a` / `#4a4a4c` / `#3f3f42` | `.projectpage__description`, `.faq__item-content p`, `.about__copy`, `.about__bio-copy` |
| `text/muted` | `#6b6b6b` | `.work__card-category`, `.pricing__step p`, `.workpage__subtitle`, `.legalpage__updated` |
| `text/muted-cool` | `#6b7280` | `.hero__heading-light`, `.contact-cta__heading-muted` |
| `text/muted-light` | `#828282` / `#8a8a8a` | `.services__heading-light`, `.faq__heading-light`, `.projectpage__caption` |
| `text/placeholder` | `#b0b0b0` | `.contact-panel__input::placeholder` |
| `text/on-dark` | `#fff` | footer, dark buttons |
| `text/on-dark-muted` | `#7c7c7c`, `#888`, `#7a7a7a`, `#8a8a8a`, `#555`, `#444` | `.footer__sub--muted`, `.footer__label`, `.footer__copy` |

**Borders**
| Token | Value | Usage |
|---|---|---|
| `border/hairline` | `rgba(0,0,0,0.08)` (`#00000014`) | **the signature divider** — every section boundary: `.hero`, `.work`, `.services`, `.about`, `.pricing` `border-bottom`; `.grid-container` left/right; `.projectpage__*:after`; `.projectpage__stats` |
| `border/subtle` | `#dedede` | `.hero__button` inner, `.pricing__card`, `.projectpage__tag`, `.bottombar`, `.contact-cta` |
| `border/subtle-2` | `#d9d9d9` (navbar), `#d8d8d6` (hero badge), `#e2e2e2` (form inputs), `#e5e5e3` (faq item), `#eaeaea` (faq card) | |
| `border/link-underline` | `rgba(0,0,0,0.28)` (`#00000047`) | `.projectpage__link`, `.legalpage__link` |
| `border/on-dark` | `#2a2a2a`, `#1e1e1e`, `rgba(255,255,255,0.45)` | footer pills / divider |

**Accents & status**
| Token | Value | Usage |
|---|---|---|
| `accent/peach` ⭐ | **`#f6b78b`** | The About section's whole accent system: `.about__wave-badge` bg, `.about__bio-stat dt`, `.about__capabilities-trigger:hover`, `.about__capabilities-check`, `.about__bio-button`, `.storypage__link:hover` |
| `accent/red` | `#e8191a` | `.services__button-avatar` only |
| `status/online` | `#22c55e` + `0 0 0 3px rgba(34,197,94,0.2)` glow | `.hero__badge-dot` |
| `status/pulse` | `#10b981` | `.pricing__pill .dot` (2s `pulse` keyframe) |
| `status/success` | `#1a7f3c` | `.contact-panel__submit--ok` |
| `status/error` | `#c0392b` | `.contact-panel__submit--err` |
| `nav/wave-dot` | `#9ca3af` → `#1a1a1a` | `waveColorBounce` keyframe |

---

# 2. Typography

### 2a. Font loading

```css
@import "…css2?family=EB+Garamond:ital,wght@0,400..800;1,400..800&display=swap";
@import "…css2?family=Antonio:wght@500;600;700&display=swap";
@import "…css2?family=Antonio:wght@600&display=swap";

@font-face{font-family:Switzer;src:url(/assets/Switzer-Medium-RFqtjt7E.otf) format("opentype");
           font-weight:400;font-style:normal;font-display:swap}
@font-face{font-family:Switzer;src:url(/assets/Switzer-Semibold-BL4pOLMt.otf) format("opentype");
           font-weight:600;font-style:normal;font-display:swap}
@font-face{font-family:"Switzer Light";src:url(/assets/Switzer-Light-BADCwite.otf) format("opentype");
           font-weight:300;font-style:normal;font-display:swap}
```

**Critical insight:** Switzer weight **400 is actually the _Medium_ cut** and 600 is _Semibold_. There is **no Regular and no Bold**. This is why nearly every large heading in the codebase declares `font-weight:400` yet renders visually medium-weight. When reproducing this design, `400 == Medium (500)`.

### 2b. Font stacks

| Role | Stack | Where |
|---|---|---|
| **Primary / UI / headings** | `Switzer, sans-serif` | ~95% of the site |
| **Light body (About/Story)** | `"Switzer Light", Switzer, sans-serif` @ 300 | `.about__copy`, `.about__capabilities-copy`, `.about__bio-copy`, `.about__capabilities-details li`, `.storypage__sub`, `.storypage__credit` |
| **Display condensed** | `Antonio, "Arial Narrow", sans-serif` | `.about__title`, `.about__eyebrow`, `.about__capabilities-title/trigger`, `.about__bio-title`, `.about__bio-stat dt`, `.about__bio-button`, `.footer__wordmark` |
| **Serif (scroll scene only)** | `"EB Garamond", serif` | global `h1` in the 3D laptop scroll section, `.screen-text` |
| **Mono** | `"Space Mono", monospace` / `ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Courier New"` | `.t-mono`, `.custom-cursor:before`, `.terminal-text`, `.dance-frame` |

> ⚠️ **Space Mono is referenced but never `@import`ed** in this stylesheet — it will fall back to the system monospace unless injected at runtime by the JS bundle. (Unverified — I did not exhaustively scan the 1.5MB+ JS.)

> ⚠️ The second `body` rule **overrides** the first: `body{font-family:sans-serif,system-ui}` wins over `body{font-family:var(--font-body)}`. Switzer is applied component-by-component via explicit `font-family:Switzer,sans-serif` declarations, not inherited.

### 2c. Declared type-scale tokens (mostly unused by components)

```css
--text-xs:   .75rem;    /* 12px */
--text-sm:   .875rem;   /* 14px */
--text-base: 1rem;      /* 16px */
--text-lg:   1.125rem;  /* 18px */
--text-xl:   1.25rem;   /* 20px */
--text-2xl:  1.5rem;    /* 24px */
--text-3xl:  2rem;      /* 32px */
--text-4xl:  clamp(2.5rem, 5vw + 1rem, 4rem);    /* 40 → 64px  */
--text-5xl:  clamp(3.5rem, 7vw + 1rem, 7rem);    /* 56 → 112px */
--text-hero: clamp(4rem, 10vw + 1rem, 11rem);    /* 64 → 176px */
```

### 2d. Declared utility classes

```css
.t-hero  { font-family:var(--font-heading); font-size:var(--text-hero);
           letter-spacing:-.03em; font-weight:700; line-height:.95 }
.t-h1    { font-size:var(--text-5xl); font-weight:700 }
.t-h2    { font-size:var(--text-4xl); font-weight:600 }
.t-h3    { font-size:var(--text-2xl); font-weight:600 }
.t-body  { font-size:var(--text-base); line-height:1.7 }
.t-small { font-size:var(--text-sm);   line-height:1.5 }
.t-mono  { font-family:var(--font-mono); font-size:var(--text-sm) }
.t-label { font-size:var(--text-xs); letter-spacing:.12em;
           text-transform:uppercase; font-weight:500 }
.t-accent{ color:var(--color-accent) }
.t-muted { color:var(--color-text-muted) }

h1,h2,h3,h4,h5,h6 { font-family:var(--font-heading); letter-spacing:-.02em;
                    color:var(--color-text); font-weight:400; line-height:1.05 }
body { font-size:1rem; line-height:1.6; -webkit-font-smoothing:antialiased;
       -moz-osx-font-smoothing:grayscale }
```

### 2e. **Real, in-use type scale** (the useful table)

| Element | Size | Weight | Line-height | Letter-spacing | Color |
|---|---|---|---|---|---|
| `.hero__heading` | `clamp(44px, 5.2vw, 72px)`<br>(64px ≥990, 48px 770–989, 42px ≤770) | 400 | 1.06 | −0.02em | `#6b7280` light span / `#1a1a1a` bold span |
| `.hero__subtext` | 18px (16px ≤989) | 400 (`strong`=600) | 1.55 | — | `#545454` |
| `.hero__badge` | 13px (12px ≥990) | — | — | — | `#1a1a1a` |
| `.hero__button` | 16px / 14px ≤770 | 400 | — | — | `#fff` |
| `.work__label` | 24px | 400 | — | −0.02em | `#1a1a1a` |
| `.work__card-title` | 20px | 400 | — | −0.01em | `#1a1a1a` |
| `.work__card-category` / `-link` | 14px | 400 | — | — | `#6b6b6b` |
| `.work-testimonial__quote` | `clamp(22px, 2.2vw, 27px)` | 400 (`strong`=600) | 1.4 | **−0.04em** | `#1a1a1a` |
| `.services__heading` | `clamp(40px, 5vw, 68px)` (mobile `clamp(36px,10vw,42px)`) | 400 | 1.05 (mobile 1.02) | −0.02em (mobile −0.04em) | `#828282` / `#1a1a1a` |
| `.services__list-text` | `clamp(16px, 1.7vw, 24px)` (20px mobile) | 400 | — | −0.02em (mobile −0.03em) | `#1a1a1a` |
| `.about__eyebrow` | Antonio `clamp(28px, 2.35vw, 42px)` | 500 | 0.95 | 0 | `#2e2e30`, UPPERCASE |
| `.about__title` | Antonio `clamp(86px, 7.7vw, 142px)` (96px tablet, 56px mobile) | **900** | 0.88 | 0 | `#2c2c2e`, UPPERCASE, nowrap |
| `.about__copy` | Switzer Light `clamp(19px, 1.35vw, 25px)` | 300 | 1.32 | — | `#4a4a4c`, right-aligned |
| `.about__capabilities-title` / `.about__bio-title` | Antonio 48px (42px mobile) | 900 | 0.95 | 0 | `#2c2c2e` |
| `.about__capabilities-trigger` | Antonio `clamp(26px, 2.45vw, 42px)` (24px mobile) | 600 | 1 | 0 | `#2c2c2e` → `#f6b78b` |
| `.about__bio-stat dt` | Antonio 54px (60px tablet, 48px mobile) | 700 | 1 | — | `#f6b78b` |
| `.about__bio-stat dd` | Switzer 18px (16px sm) | 700 | 1.1 | — | `#303033` |
