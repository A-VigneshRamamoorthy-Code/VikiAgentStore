# Interaction & Animation Guidelines

## 1. Custom Cursor
- Use a custom GSAP-driven cursor (a 16px black dot).
- **Default State**: Tracks mouse using `gsap.quickTo()` for spring-like fluid motion.
- **Hover State (Interactive)**: When hovering over `<a>` or `<button>`, scale the cursor up (`scale: 3`) and change color to `var(--accent-peach)` (`#f6b78b`).
- **Hover State (CTA/Contact)**: When hovering over primary contact buttons, morph the cursor into a wide pill (`width: 250px, height: 48px, border-radius: 999px`) with inline text ("Speak to me") and icons.

## 2. Header / Navbar
- **Sticky Glass**: Fixed at top, `height: 60px`, `background-color: rgba(255,255,255,0.5)`, `backdrop-filter: blur(5px)`. Bottom border is hairline `#d9d9d9`.
- **Logo**: Simple Switzer text, typically paired with a dot (`width: 6px`, `height: 6px`, `border-radius: 50%`).
- **Links**: Fade opacity to `0.6` on hover.

## 3. Product Name to Product Details Transition
Instead of standard modals, product details should feel like a fluid page transition:
1. **Click**: The user clicks a product card in the grid.
2. **Title Morph**: The product name scales and moves seamlessly from the card's `h3` (`20px`) size to a massive `t-hero` (`clamp(44px, 5.2vw, 72px)`) heading on the details page.
3. **Details Entrance**: The project metadata, tags, and long description stagger in from the bottom (`y: 40`, `opacity: 0` to `y: 0`, `opacity: 1` over `0.8s` using `power3.out`).
4. **Implementation**: If building a single page app, this is typically done using Framer Motion's `<motion.div layoutId="...">` or GSAP FLIP to morph the title and image across views.

## 4. Scroll Animations
- Smooth scrolling powered by **Lenis** (`duration: 1.2`).
- **Reveal on Scroll**: Use `ScrollTrigger`. Sections fade and slide up (`y: 40`, `opacity: 0` -> `y: 0`, `opacity: 1`) when they cross `80%` of the viewport. Elements inside grids should use `stagger: 0.1`.
