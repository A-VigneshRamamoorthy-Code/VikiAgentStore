# 3. Animation core — 0% idle CPU + physics + "always alive" gestures

Three layers: a **render loop** that costs nothing when idle, a **physics engine**
(spring + Verlet rope), and a **gesture system** that keeps the creature moving on
a clock. All physics/geometry live in the pure core; only the loop is AppKit.

## 3a. The 0%-idle render loop (CADisplayLink, paused at rest)
```swift
final class CreatureView: NSView {
    private var link: CADisplayLink?
    private var lastTime: CFTimeInterval = 0
    private var lastDirty: CGRect = .null

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        guard window != nil, link == nil else { return }
        let l = displayLink(target: self, selector: #selector(tick(_:)))
        l.preferredFrameRateRange = CAFrameRateRange(minimum: 24, maximum: 30, preferred: 30) // cap → ~half CPU
        l.add(to: .main, forMode: .common)
        l.isPaused = true                      // start asleep
        link = l
    }
    func resume() { if link?.isPaused == true { lastTime = 0; link?.isPaused = false } }

    @objc private func tick(_ link: CADisplayLink) {
        let now = link.timestamp
        let dt = lastTime > 0 ? now - lastTime : 1.0/60.0
        lastTime = now
        let state = engine.update(cursor: target, engaged: engaged, dt: dt)
        let dirty = Renderer.bounds(of: state)          // only the creature's box
        setNeedsDisplay(dirty.union(lastDirty)); lastDirty = dirty
        if !engaged && engine.isAtRest { link.isPaused = true }   // ★ sleep → 0% CPU
    }
    override func draw(_ dirty: NSRect) {
        guard let ctx = NSGraphicsContext.current?.cgContext else { return }
        ctx.clear(dirty)
        Renderer.draw(in: ctx, state: engine.state)
    }
}
```
The four levers that keep active CPU at ~4–6% and idle at **0%**:
1. **Pause the link** when `isAtRest && !engaged`; resume on the mouse monitor.
2. **Cap the frame rate** (30fps is plenty for a notch toy).
3. **Dirty-rect** invalidation — never redraw the whole transparent window.
4. **Cache rigid art** as a `CGImage` and blit it (see rendering doc); only
   per-frame transforms change.

## 3b. Spring solver — sub-step for stability
A damped spring chases a target. Naive Euler explodes on large/irregular `dt`
(breakpoints, stutter). Sub-step based on `dt`:
```swift
struct Spring { var stiffness, damping, mass: Double
  func step(position p: Double, velocity v: Double, target: Double, dt: Double) -> (Double, Double) {
    guard dt > 0 else { return (p, v) }
    let n = min(64, max(2, Int((dt / (1.0/180.0)).rounded(.up))))   // ★ adaptive sub-steps
    let h = dt / Double(n); var p = p, v = v
    for _ in 0..<n { let a = (stiffness*(target - p) - damping*v)/max(1e-4,mass); v += a*h; p += v*h }
    return (p, v)
  }
}
```
Also **clamp dt** in the engine (`min(dt, 1.0/30)`) as a second safety net.

## 3c. Verlet rope — fluid limbs and tails (and pull-chains)
A pinned rope gives natural follow-through for both short limbs (4 nodes) and long
tails/chains (8+ nodes). Base node is pinned at the notch; the tip is attracted to
a target; intermediate nodes trail.
```
for i in 1..<n:                    # integrate free nodes
    temp = node[i]
    vel  = node[i] - prev[i]       # Verlet velocity = positional delta
    if i == last: node[i] += vel*tipDamp + springToTarget*h*h - gravity
    else:         node[i] += vel*chainDamp - gravity*h*h
    prev[i] = temp
# distance constraints — iterate a few times:
for _ in 0..<iters:
    node[0] = shoulder             # re-pin base every pass
    for i in 1..<n:
        d = node[i] - node[i-1]; if |d|<eps { d = (0,-1) }   # seed direction if collapsed
        diff = (|d| - segLen)/|d|
        if i-1 == 0: node[i] -= d*diff                       # base pinned → move child only
        else:        node[i-1] += d*0.5*diff; node[i] -= d*0.5*diff   # ★ move BOTH ends
```
**★ Gotcha:** the constraint must move *both* nodes (except the pinned base). If you
only move the child, a collapsed chain can never straighten/extend — limbs and
tails stay bunched at the notch. (This was a real bug.)

Tuning: lower `chainDamping` (~0.80) = stiffer, straighter limb; higher (~0.92) =
loose, whippy tail. `segLen` scales with an `emergence` factor (0→1) so the chain
**tucks fully into the notch** when retracting, and (for paws) scales with the
cursor distance so a near cursor gives a **short** limb instead of a coil.

## 3d. Gesture system — stay alive when the cursor is still
Drive the tip's target from a **clock**, not just the cursor, so the creature keeps
acting. One cycle = anticipation → strike (overshoot) → follow-through → pause,
plus an always-on idle sway. (Apply the `motion-design` skill: Playful archetype,
ease-out-back, squash & stretch, overlapping action.)
```swift
func sample(style, cursor, shoulder, time) -> (target, stretch, windup) {
    let phase = (time / cycle).truncatingRemainder(dividingBy: 1)
    let strike = singleStrike(phase)              // -antic → ~1+overshoot → 0
    let along  = reach * (reachBias + (1-reachBias)*strike)   // reach toward cursor
    let sway   = perpAmp*sin(2π*phase*perpCycles) + idleSway*sin(time*2.2)  // never frozen
    // target = shoulder + unit(cursor-shoulder)*along + perp*sway (+ hop for bunnies)
}
```
Because every output is a function of `time`, two calls a fraction of a second
apart return different targets → continuous, lifelike motion with a stationary
cursor. Per-variant personality lives in a `Style` struct (stiffness, cycle,
reachBias, swat impulse, sway amplitude, hop, palette…).

## 3e. Emergence (pop in/out of the notch)
Keep a `0…1` `emergence` value driven by a critically-damped spring toward
`engaged ? 1 : 0`. Multiply limb length / alpha by it so the creature smoothly
slides out when the cursor nears and tucks away when it leaves. `isAtRest` =
`emergence < 0.02 && tip≈shoulder && low velocity` → lets the loop sleep.

See [rendering-and-icon.md](rendering-and-icon.md) for drawing the state, and
[examples/pull-chain-lock-screen.md](../examples/pull-chain-lock-screen.md) for a
draggable Verlet chain.
