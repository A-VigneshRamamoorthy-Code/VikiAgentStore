# Interaction & Motion

## 1. Custom cursor: constant companion

- Keep the native OS cursor. Never set `cursor: none`.
- Render one decorative `16px × 16px` dot with `var(--bg-black)` (`#050505`, equivalent to `rgb(5, 5, 5)`).
- Keep its `1.5px` light border, subtle `4px` glow, circular shape, and fill constant for the full session.
- Show it only for `(pointer: fine)`. Keep `pointer-events: none` and `aria-hidden="true"`.
- Offset it `28px` right and `32px` down so it never sits under the real pointer.
- Centre it with `xPercent: -50`, `yPercent: -50` and initialise it at `opacity: 0`. On the first move, place it immediately, reveal it over `0.3s`, then track with:

```ts
const xTo = gsap.quickTo(cursor, 'x', { duration: 0.6, ease: 'power3.out' });
const yTo = gsap.quickTo(cursor, 'y', { duration: 0.6, ease: 'power3.out' });
```

- Attach exactly one passive `mousemove` listener. Do not attach `mouseover`, `mouseout`, `mouseenter`, or `mouseleave` listeners.
- **Invariant:** the dot never changes size, shape, or colour. Do not scale it over links, recolour it, add labels, or morph it into a CTA pill.
- Rationale: a resizing decorative cursor competes with the native pointer, obscures its target, and weakens affordance and accessibility.

## 2. Product cards and explicit details

- A card hover is only a preview: lift its media `-8px`, switch to `var(--shadow-card-hover)`, darken the circular arrow, and rotate the arrow `-45deg`.
- Selection persists the lifted state, changes the media border to the product accent, and rotates the arrow `90deg`.
- Reveal details only after an explicit card click. Never reveal them on hover and never render them always-open.
- Keep at most one panel open per category. Clicking the selected card closes it; clicking a sibling switches the panel content.
- Open the mounted panel from `{ height: 0, opacity: 0 }` to `{ height: 'auto', opacity: 1 }` over `0.8s` with `power3.out`, then clear the inline height.
- Close before unmounting: animate to `{ height: 0, opacity: 0 }` over `0.5s` with `power2.inOut`, then remove the panel. Do not let close paths vanish instantly.
- Route every close action through the same collapse function: selected card click, explicit `✕` button, and `Escape`.
- Use the panel's app tabs only to switch sibling products. Keep the close control independently reachable and labelled.

## 3. Netflix-style 3D coverflow

- Put `perspective: 1200px` and `transform-style: preserve-3d` on the stage. Absolutely centre each card at `left: 50%`, `top: 50%` with `xPercent: -50`, `yPercent: -50`.
- **Do not set card `z-index`.** `preserve-3d` lets the browser depth-sort the cards. Reintroducing explicit stacking causes swap flicker.
- Compute the shortest signed cyclic offset from the active card. Keep two cards visible on either side.
- For each depth level, move sideways, rise, recede on negative `z`, rotate around the Y axis toward centre, scale down, and fade:

```ts
x = stageWidth * spread * offset;
y = -stageWidth * rise * abs(offset);
z = -abs(offset) * 150;
rotationY = -offset * flip;
scale = 1 - abs(offset) * 0.11;
opacity = 1 - abs(offset) * 0.42;
```

- Wide portrait fan: `spread: 0.14`, `rise: 0.075`, `flip: 26`.
- Wide landscape fan: `spread: 0.165`, `rise: 0.09`, `flip: 24`.
- Below `900px`, tighten portrait to `spread: 0.115`, `flip: 22`; tighten landscape to `spread: 0.13`, `flip: 18`.
- Animate swaps over `0.78s` with `power3.inOut`. A receding card first dips another `260px` on `z`, using `45%` of the duration with `power2.out`, then returns during the remaining `55%` with `power2.inOut`.
- Hide cards beyond visible depth with `opacity: 0`, `pointer-events: none`, `tabIndex: -1`, and `aria-hidden="true"`.
- Probe every screenshot with `new Image()` and read `naturalWidth / naturalHeight`. Do not rely on React `onLoad`; a cached image can complete before that handler is attached.
- Clamp aspect ratios to `0.4–3.1`. Derive card width from aspect within `42%–76%` of the stage so portrait and landscape images settle at similar heights.
- Size the stage from the tallest derived card plus fan rise and margin. Do not hardcode a portrait- or landscape-only height.
- Format the counter as `1 / 4`, never `01 / 04`.

## 4. Hero-to-grid app flight

- The desktop flight layer owns the moving covers while their static hero and grid copies step aside.
- Cache settled document-space geometry. Walk `offsetLeft` and `offsetTop` through each `offsetParent`; use `offsetWidth` and `offsetHeight` for size.
- Do not use `getBoundingClientRect()` for this cache. It includes active reveal and hover transforms, so measuring mid-flight poisons the destination.
- Re-measure only after resize, load, or a document `ResizeObserver` invalidation. Do not read layout inside every ticker update.
- Disable the flight below `860px` and for `(prefers-reduced-motion: reduce)`.

## 5. Reduced motion

- Include the global guard:

```css
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

- Do not rely on CSS alone for GSAP. Check `matchMedia('(prefers-reduced-motion: reduce)')` and use an instant state path.
- Set gallery slots immediately, show detail panels without an opening tween, close them before the next paint, and skip the app-flight sequence.

## 6. React style correctness

- Never mix a CSS shorthand in a base style object with one of its longhands in a merged override. React reports a conflicting style update.
- For selectable borders, define `borderWidth`, `borderStyle`, and `borderColor` in the base object; override only `borderColor`.
- Apply the same rule to tabs and cards. Do not use base `border` plus selected `borderColor`.

## 7. Supporting choreography

- Use GSAP `ScrollTrigger` reveals from `y: 42`, `opacity: 0` to rest over `0.9s` with `power3.out`, starting at `top 88%`.
- Keep the floating navbar fixed and let ordinary links fade to `0.6` opacity on hover. The theme toggle and contact action remain stable circular or pill targets.
