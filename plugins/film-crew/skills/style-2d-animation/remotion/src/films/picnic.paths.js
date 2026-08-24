/**
 * The Picnic — every path, every beat of the clock, in one plain-JS module.
 *
 * ── Why this file exists ──────────────────────────────────────────────────
 *
 * It used to live inside `Picnic.jsx`, and `scripts/check-physics.mjs` kept a
 * hand-written COPY of it, because Node cannot import JSX and the validator
 * has to run outside Remotion.
 *
 * That copy drifted. Three segment durations were retimed in the validator and
 * silently not in the film — the search-and-replace matched one file's
 * whitespace and not the other's. The validator went on reporting "29 checks
 * clean" the whole time, because it was faithfully validating ITSELF. The film
 * meanwhile had a segment of *negative* duration in it and ended with the dog
 * nine hundred units outside the frame.
 *
 * A validator that mirrors the thing it validates is worse than no validator,
 * because it converts a visible bug into a passing test. So the mirror is gone.
 * This module is the single source of truth and both sides import it.
 *
 * ── What is still not shared, and why that is fine ────────────────────────
 *
 * Stride lengths. Those come from `Humaaans.jsx` and `Dog.jsx`, which are JSX
 * and therefore unreachable from Node. So `picnicPaths` takes them as an
 * argument instead of importing them: the film passes the rig's real numbers,
 * the validator passes the ones it derives independently from the same
 * skeleton constants, and the two are then checked against each other. That is
 * a cross-check, not a copy — if they disagree, something is genuinely wrong.
 */

export const FPS = 30;
export const DURATION_SEC = 18;

export const ADULT = 0.92;
export const CHILD = 0.58;   // read as a child by height, not by a smaller head
export const DOG_S = 0.66;

/* ── the clock ────────────────────────────────────────────────────────────
 *
 * Named once. Six separate things have to agree about when the family sits
 * and when the dog goes, and six copies of "about five seconds in" is how a
 * film drifts out of sync with itself.
 */
export const ARRIVE = 4.4;   // the last adult stops walking
export const SIT_IN = 4.6;   // knees start to bend
export const SIT_OUT = 6.0;  // fully down
export const NOTICE = 9.6;   // the dog's head comes up
export const LAUNCH = 10.4;  // it goes
export const SKID = 14.0;    // it gives up

export const BLANKET_X = 430;

export const S = (sec) => Math.round(sec * FPS);

/**
 * Append a constant-speed leg to a path.
 *
 * `dur` is in seconds and MUST be positive. A negative duration puts a key
 * before the one it follows, which the solver interpolates straight through
 * without complaining — the film simply teleports. This has happened once
 * already (`SKID - 15.0` with SKID at 14.0), so it now throws.
 */
const seg = (keys, dur, speed, ease) => {
  if (!(dur > 0)) {
    throw new Error(`seg: duration must be positive, got ${dur}`);
  }
  const last = keys[keys.length - 1];
  keys.push({t: last.t + S(dur), x: last.x + speed * dur, ease});
  return keys;
};

/**
 * Shift a whole path so that at key `idx` the character is at `targetX`.
 *
 * Paths here are built forwards from a start position, which means the place a
 * character ENDS UP is the sum of every segment before it. Authoring the start
 * instead and hoping is how the first cut of this film put the entire family
 * six hundred units to the left of the blanket, sitting down to eat on bare
 * grass — every path individually correct, the staging nonsense.
 *
 * So the arrival is what gets specified, and the entrance is derived. Retime
 * any segment and everyone still lands on the rug.
 */
const place = (keys, idx, targetX) => {
  const dx = targetX - keys[idx].x;
  return keys.map((k) => ({...k, x: k.x + dx}));
};

/**
 * Build all four paths from a set of measured stride lengths.
 *
 * @param strides `{WALK, KID_WALK, KID_RUN, DOG_TROT, DOG_BOUND}` — scene
 *        units per gait cycle, already scaled to each character's size.
 */
export const picnicPaths = ({WALK, KID_WALK, KID_RUN, DOG_TROT, DOG_BOUND}) => {
  const D = DURATION_SEC;

  /**
   * Mum and Dad arrive together but not identically.
   *
   * Dad is fractionally slower and stops fractionally later. Two adults on one
   * path at one speed is one adult drawn twice, and the eye finds that faster
   * than it finds a wrong foot.
   */
  const mum = (() => {
    const k = [{t: 0, x: 0, ease: 'creep'}];
    seg(k, 3.4, WALK * 0.92, 'easeInOut');
    seg(k, 1.0, WALK * 0.34, 'easeOut');   // slows as she reaches the spot
    seg(k, 0.4, 0, 'easeOut');
    seg(k, D - 4.8, 0, 'creep');
    return place(k, 3, BLANKET_X - 110);
  })();

  const dad = (() => {
    const k = [{t: 0, x: 0, ease: 'creep'}];
    seg(k, 3.7, WALK * 0.9, 'easeInOut');
    seg(k, 1.0, WALK * 0.3, 'easeOut');
    seg(k, 0.3, 0, 'easeOut');
    seg(k, D - 5.0, 0, 'creep');
    return place(k, 3, BLANKET_X - 330);
  })();

  /**
   * The child gets there first, then has to wait.
   *
   * She runs ahead, overshoots the blanket, and comes back a step — which is
   * both what a child does and a free demonstration that facing is derived:
   * she reverses on screen without a single authored flip.
   */
  const kid = (() => {
    const k = [{t: 0, x: 0, ease: 'creep'}];
    seg(k, 2.6, KID_RUN * 0.86, 'easeIn');      // runs ahead of her parents
    seg(k, 0.7, KID_WALK * 0.5, 'easeOut');     // overshoots and slows
    seg(k, 0.5, 0, 'easeOut');
    seg(k, 0.9, -KID_WALK * 0.55, 'easeInOut'); // and comes back a step
    seg(k, 0.4, 0, 'easeOut');
    seg(k, D - 5.1, 0, 'creep');
    return place(k, 5, BLANKET_X + 105);
  })();

  /**
   * The dog. The only character with a second act.
   *
   * It arrives first, mills about, and then — after the film has been still
   * for three and a half seconds — leaves at four times anyone else's pace.
   * The anticipation is real travel, not a pose: it backs up a few units
   * before it launches, so the launch has something to be released from.
   *
   * It overshoots the butterflies, because a chase that lands on its target
   * is a delivery.
   *
   * The chase is deliberately SHORT. The first cut ran it for three and a
   * fifth seconds and then ambled the dog home, which put nearly seven of the
   * eighteen seconds on an empty meadow with a dog in it and cropped the
   * family out of the last shot entirely. There is no camera move that fixes
   * two subjects further apart than the lens is wide; the distance itself has
   * to be smaller. So the dog turns round sooner and comes back nearly as
   * fast as it left, which is also the funnier read.
   */
  const dog = (() => {
    const k = [{t: 0, x: 0, ease: 'creep'}];
    // Fast trot, not an amble: a stroll cannot cover enough ground in the time
    // the family takes to walk on, and the dog was starting the film already
    // parked in the middle of the shot instead of arriving in it.
    seg(k, 2.9, DOG_TROT * 2.6, 'easeIn');       // out in front of everyone
    seg(k, 0.9, DOG_TROT * 0.5, 'easeOut');
    seg(k, 0.7, -DOG_TROT * 0.35, 'easeInOut');  // circles back to the blanket
    seg(k, NOTICE - 4.5, 0, 'easeOut');          // waits, dead still
    seg(k, LAUNCH - NOTICE - 0.25, -DOG_TROT * 0.22, 'easeInOut'); // anticipation
    seg(k, 0.25, 0, 'easeOut');
    seg(k, 1.8, DOG_BOUND * 1.15, 'easeIn');     // the chase
    seg(k, 1.0, DOG_BOUND * 0.55, 'easeOut');    // losing it
    seg(k, SKID - 13.2, 0, 'easeOut');           // skids to a halt
    // Stops a little short of the hamper rather than on top of it. Two
    // characters occupying one patch of ground reads as a z-order mistake even
    // when the intent was affection.
    seg(k, D - SKID, -DOG_BOUND * 0.611, 'easeInOut'); // and hurries back
    return place(k, 3, BLANKET_X + 300);
  })();

  return {mum, dad, kid, dog};
};
