# Visual System

## 1. Token-first rule

- Treat the global token layer as the source of truth. Themeable components consume variables; do not hardcode a second palette inside component styles.
- Keep product and brand accent colours as product data. They are deliberately not theme tokens and must remain identical in light and dark themes.
- Change only tint strength across themes. Use product accents through `color-mix()`, never by replacing the accent itself.

## 2. Light palette

Use this block verbatim:

```css
:root {
  color-scheme: light dark;
  --bg-canvas: #fafafa;
  --bg-surface: #ffffff;
  --bg-inverse: #0a0a0a;
  --bg-black: #050505;
  --bg-glass: rgba(255, 255, 255, 0.72);
  --text-primary: #1a1a1a;
  --text-secondary: #545454;
  --text-muted: #6b6b6b;
  --text-on-dark: #ffffff;
  --text-on-dark-muted: #888888;
  --border-hairline: rgba(0, 0, 0, 0.08);
  --border-subtle: #dedede;
  --border-on-dark: #1e1e1e;
  --accent-peach: #f6b78b;
  --font-sans: 'Switzer', sans-serif;
  --font-display: 'Antonio', "Arial Narrow", sans-serif;
  --shadow-physical:
    0 1px 2px rgba(0, 0, 0, 0.03),
    0 2px 4px rgba(0, 0, 0, 0.03),
    0 4px 8px rgba(0, 0, 0, 0.03),
    0 8px 16px rgba(0, 0, 0, 0.03),
    0 16px 32px rgba(0, 0, 0, 0.03);
  --shadow-soft: 0 10px 22px rgba(0, 0, 0, 0.06);
  --shadow-card-hover:
    0 20px 40px rgba(0, 0, 0, 0.08),
    0 6px 14px rgba(0, 0, 0, 0.04);
  --shadow-navbar: 0 12px 28px rgba(0, 0, 0, 0.07);
  --shadow-product: 0 16px 34px rgba(0, 0, 0, 0.1);
  --tint-strong: 24%;
  --tint-mid: 10%;
  --tint-soft: 5%;
}

html[data-theme='light'] {
  color-scheme: light;
}
```

Use `--bg-canvas` for the page and `--bg-surface` for cards, controls, and detail panels. The slight separation between `#fafafa` and `#ffffff` is intentional.

## 3. Dark palette

Use the full override. Do not derive dark colours at runtime.

```css
html[data-theme='dark'] {
  color-scheme: dark;
  --bg-canvas: #11100f;
  --bg-surface: #191817;
  --bg-inverse: #070605;
  --bg-black: #050505;
  --bg-glass: rgba(25, 24, 23, 0.74);
  --text-primary: #f4efe7;
  --text-secondary: #c7bfb4;
  --text-muted: #91887d;
  --text-on-dark: #ffffff;
  --text-on-dark-muted: #8a8177;
  --border-hairline: rgba(255, 244, 232, 0.11);
  --border-subtle: #332f2a;
  --border-on-dark: rgba(255, 244, 232, 0.12);
  --shadow-physical:
    inset 0 1px 0 rgba(255, 244, 232, 0.04),
    0 1px 2px rgba(0, 0, 0, 0.14),
    0 8px 18px rgba(0, 0, 0, 0.16),
    0 18px 42px rgba(0, 0, 0, 0.18);
  --shadow-soft:
    inset 0 1px 0 rgba(255, 244, 232, 0.04),
    0 14px 30px rgba(0, 0, 0, 0.22);
  --shadow-card-hover:
    inset 0 1px 0 rgba(255, 244, 232, 0.05),
    0 24px 52px rgba(0, 0, 0, 0.28),
    0 9px 20px rgba(0, 0, 0, 0.2);
  --shadow-navbar: 0 16px 38px rgba(0, 0, 0, 0.3);
  --shadow-product: 0 20px 44px rgba(0, 0, 0, 0.3);
  --tint-strong: 17%;
  --tint-mid: 8%;
  --tint-soft: 4%;
}
```

The warm inset top edge fakes a softly lit rim on dark surfaces. Use `rgba(255, 244, 232, 0.04)` for physical and soft elevation, and `rgba(255, 244, 232, 0.05)` for the stronger hover state.

## 4. Theme resolution before first paint

Place this script in `<head>` before styles that depend on the theme and before the application bundle:

```html
<script>
  (() => {
    try {
      const theme = localStorage.getItem('solo-theme');
      if (theme === 'dark' || theme === 'light') document.documentElement.dataset.theme = theme;
      else document.documentElement.removeAttribute('data-theme');
    } catch {
      document.documentElement.removeAttribute('data-theme');
    }
  })();
</script>
```

- Use `solo-theme` as the storage key.
- Explicit `light` or `dark` writes `data-theme` before first paint.
- `system` removes `data-theme`; CSS resolves the OS preference.
- Repeat every declaration from the explicit dark block verbatim inside:

```css
@media (prefers-color-scheme: dark) {
  html:not([data-theme='light']) {
    /* Full dark token block, duplicated verbatim. */
  }
}
```

- The duplication is intentional. Plain CSS cannot reuse a whole declaration block, and both explicit dark mode and system dark mode must resolve independently in the cascade before React runs. Moving system resolution into JavaScript reintroduces a flash.
- The `:not([data-theme='light'])` guard makes an explicit light choice override a dark OS preference.
- Subscribe to both `matchMedia('(prefers-color-scheme: dark)')` changes and `storage` events after mount so system and cross-tab changes stay synchronized.

## 5. Shadows: soft lift, never a halo

- Build physical elevation from many low-opacity layers. The five `rgba(0, 0, 0, 0.03)` layers should read as contact, lift, and falloff—not as a single dark outline.
- Use `--shadow-soft` for small covers and icons, `--shadow-physical` for cards and dark pills, `--shadow-card-hover` only for active lift, `--shadow-navbar` for the floating glass bar, and `--shadow-product` for screenshots.
- Do not strengthen these values. The current language is deliberately lighter than the original reference.

## 6. Typography

Load the current hosted families:

```html
<link
  rel="stylesheet"
  href="https://fonts.googleapis.com/css2?family=Antonio:wght@500;600;700&display=swap"
/>
<link
  rel="stylesheet"
  href="https://api.fontshare.com/v2/css?f[]=switzer@300,400,500,600,700&display=swap"
/>
```

- Use Switzer for body copy, navigation, metadata, and primary editorial headings.
- Use Antonio for condensed uppercase category headings, detail titles, and the footer wordmark.
- Do not carry forward the old claim that Switzer `400` is a Medium font file. The current Fontshare request loads real weights `300–700`.
- Keep body copy at `16px`, line-height `1.6`, with antialiasing.
- Use these display utilities:

```css
.t-display {
  font-family: var(--font-display);
  font-weight: 700;
  text-transform: uppercase;
  line-height: 0.9;
}

.t-hero {
  font-family: var(--font-display);
  font-size: clamp(64px, 10vw, 142px);
  font-weight: 900;
  text-transform: uppercase;
  line-height: 0.88;
  letter-spacing: 0;
  white-space: nowrap;
}
```

- Keep the main hero conversational rather than condensed: Switzer `clamp(44px, 6vw, 82px)`, weight `400`, line-height `1.06`, letter-spacing `-0.03em`.

## 7. Surfaces and composition

- Constrain primary content to `120ch` with fluid `5%` page gutters.
- Float the navbar `16px` from the top. Use `56px` height, `min(760px, calc(100% - 24px))` width, `var(--bg-glass)`, `blur(5px)`, a `999px` radius, a hairline border, and `--shadow-navbar`.
- Use `999px` pills only for compact controls and actions. Product cards use larger physical radii instead of pills.
- Use `28px` radius and a `4 / 3` frame for product-card media; use `32px` for the detail panel; use `22px` for coverflow cards.
- Keep the footer on `--bg-inverse`, with `--text-on-dark` and `--text-on-dark-muted`. Set the oversized wordmark in Antonio, uppercase, weight `900`.

## 8. Product imagery and colour

- Place every app cover on `--bg-surface` plus a product-tinted gradient:

```ts
backgroundImage: `linear-gradient(
  155deg,
  color-mix(in srgb, ${accent} var(--tint-strong), transparent) 0%,
  color-mix(in srgb, ${accent} var(--tint-mid), transparent) 52%,
  color-mix(in srgb, ${accent} var(--tint-soft), transparent) 100%
)`;
```

- Use `55%` for the middle stop inside coverflow cards; use `52%` for hero, grid, and flight boards.
- Portrait covers start at `top: 11%`, use `height: 124%`, and bleed below the frame. Landscape covers centre at `50% / 50%` and use `width: 86%`.
- Apply `--shadow-product` to the screenshot itself. Preserve the product accent across themes; only `--tint-strong`, `--tint-mid`, and `--tint-soft` change.
