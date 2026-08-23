# Camera and overlays

Ways to buy motion without drawing anything. Every technique here moves the
*presentation* of a still image, so its cost is fixed no matter how long the
shot runs.

## Yori — the slow push-in

The single most valuable move in limited animation, because it triples how
long a drawing may be held.

| parameter | value |
|-----------|-------|
| scale | 1.00 → 1.10–1.15 |
| duration | 2–4s |
| easing | cubic in **and** out |
| pre-hold | ~0.5s still before it starts |
| post-hold | ~0.5s still after it ends |
| share of shots | **≤ 35%** |

### The five ways a push goes wrong

1. **No easing.** A linear zoom reads as a machine, not a camera.
2. **No pre- or post-hold.** The move must start from stillness and settle
   back into it, or the shot has no beginning and no end.
3. **A move on every shot.** This is the default failure and the reason this
   skill exists. See `tier_separation` in the verification reference.
4. **Range too large, or too slow.** Past ~15% the audience notices the zoom
   itself.
5. **Nothing else moving.** A push over a completely inert frame reads as a
   slideshow effect.

### Push-ins have a cropping budget

A zoom throws away the edge of the frame, and in a caption-led style the
captions live there. Measured on the validation board: a 1.32 zoom turned
`KESTREL` into `ESTREL` and `NOT TO LOOK BACK` into `NOT TO LOOK BAC` across a
dozen shots, while the undirected board — which never exceeded 1.10 — stayed
clean.

The fix is **not** a global cap. A flat safe-for-everything cap of 1.18 cost
that film a fifth of its total motion, because it starved the beats that had
plenty of room. Ask each beat what it can afford: compute the bounding box of
everything that beat owns and cap that shot's zoom so the box stays inside the
frame. Loose compositions then get a hard push and tight ones get none, which
is the correct answer for both.

## Multiplane parallax

Displace layers against the camera in proportion to depth. A ratio of about
**4 : 2 : 1** (foreground : midground : background) is the usual starting
point. This is what turns a flat pan into a moving world, and it costs one
extra copy of a background.

For a walking shot the background must be **at least 3× screen width** or the
loop becomes visible.

## Particles and overlays

Falling snow, embers, dust, petals, rain, cherry blossom. A small looping
sprite layer over a completely static drawing. This is the cheapest life
available and it is why so many anime scenes are set in weather.

Drift them *across* the frame rather than straight down, and give at least two
layers different speeds, or the loop reads.

## Impact frames

Exactly **one** frame — rarely two — of white, black, or inverted artwork,
slammed in at the moment of contact. Not a transition; a punctuation mark. The
drawing it cuts into is held.

## Camera shake

Decay by halving: **16 → 8 → 4 → 2 → 0** pixels over 4–8 frames. A shake that
does not decay reads as a broken camera rather than an impact.

## Speed lines

Radial or linear lines over a static figure, redrawn every 2–3 frames so they
crawl. Carries the *sensation* of speed with no character animation at all —
the technique the manga page gave to the screen unchanged.
