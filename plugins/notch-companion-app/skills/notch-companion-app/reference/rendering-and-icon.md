# 5. Rendering — code-drawn CoreGraphics art, caching, app icon

All art is drawn in **CoreGraphics inside the pure core** (no AppKit), so the exact
same code renders on screen *and* into offscreen bitmaps for previews/tests.

## Draw from a state object
`Renderer.draw(in: CGContext, state:)` consumes the engine's output (chain nodes,
rotation, scale, emergence) and paints it. Keep a `Renderer.bounds(of: state)` that
returns the padded bounding box for dirty-rect invalidation.

### Smooth tapered limbs/tails (no facets)
Build the outline as a filled ribbon with per-point half-widths (thick base → thin
tip), and **connect the boundary points with quadratic Béziers** (midpoint
technique) instead of straight `addLine` segments — smooth edges at the same vertex
count, ~no extra cost:
```swift
// midpoint quad-smoothing of a polyline boundary:
ctx.move(to: pts[0])
for i in 1..<pts.count-1 {
    let mid = midpoint(pts[i], pts[i+1])
    ctx.addQuadCurve(to: mid, control: pts[i])
}
ctx.addLine(to: pts.last!)
```
Resample the raw chain through a **Catmull-Rom** spline first for a flowing curve.

## ★ Cache rigid art as an image (big CPU win)
A paw head / bead / face that only rotates & scales should be **rasterized once**
into a `CGImage` and blitted each frame, not re-pathed. This cut NotchPaw's active
CPU from ~13% back to ~5%.
```swift
private static var cache: [String: CGImage] = [:]
static func headImage(for style: Style) -> CGImage? {
    if let img = cache[style.id] { return img }
    let px = Int(sizePt * scale)
    let ctx = CGContext(data: nil, width: px, height: px, bitsPerComponent: 8,
                        bytesPerRow: 0, space: CGColorSpace(name: .sRGB)!,
                        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
    ctx.scaleBy(x: scale, y: scale); ctx.translateBy(x: sizePt/2, y: sizePt/2)
    drawHead(ctx, style: style)                 // expensive path work, once
    let img = ctx.makeImage(); cache[style.id] = img; return img
}
// per frame: translate→rotate→scale→ctx.draw(img, in: rect)  (cheap)
```
Keep AppKit-free by passing colors as a plain `RGBA` struct with a `.cg(alpha)`
helper that returns a `CGColor`.

## Offscreen preview modes (see your art without a GUI)
Add hidden CLI flags that render PNGs via an `CGContext` bitmap + `ImageIO`:
- `--render <dir>`  — one representative pose per style.
- `--contact <dir>` — an **animation contact sheet**: a grid of frames sampled over
  ~2s, so you can eyeball the *motion*, not just a pose.
- `--icons <dir>`   — the menu thumbnails on light+dark backgrounds.
- `--appicon <png>` — the 1024px app icon.
Then `view` the PNGs to verify. This replaces screenshots (Screen Recording is
usually not granted). Write PNGs with:
```swift
let dest = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil)!
CGImageDestinationAddImage(dest, image, nil); CGImageDestinationFinalize(dest)
```

## App icon, drawn in code
Draw a 1024px icon (`appIcon(pt:scale:) -> CGImage`): a rounded-square gradient
"plate" (with ~8.5% padding so the system squircle mask never clips) + your motif +
a soft drop shadow. Render it, then build `.icns` in `build_app.sh`:
```bash
"$BIN" --appicon build/icon-1024.png
mkdir AppIcon.iconset
for s in 16 32 128 256 512; do
  sips -z $s $s         build/icon-1024.png --out AppIcon.iconset/icon_${s}x${s}.png
  sips -z $((s*2)) $((s*2)) build/icon-1024.png --out AppIcon.iconset/icon_${s}x${s}@2x.png
done
iconutil -c icns AppIcon.iconset -o "$APP/Contents/Resources/AppIcon.icns"
```
Add `CFBundleIconFile = AppIcon` to Info.plist. Verify it reads as your motif even
at 32px (`view` the 32px iconset entry). NB: an `LSUIElement` agent has no Dock
icon, so the app icon shows in **Finder / Get Info**, not the Dock.

See [testing-and-verification.md](testing-and-verification.md) to wire previews
into your verification loop.
