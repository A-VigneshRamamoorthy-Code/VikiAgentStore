/**
 * Overlap — follow-through, drag and settle for jointed chains.
 *
 * ── The idea, in one line ──────────────────────────────────────────────────
 *
 *     "Not all objects move at the same time even within one physical body."
 *
 * A rig that moves every part on the same frame reads as a machine, because
 * machines are exactly the thing that does that. Bodies do not: the shoulder
 * starts, the elbow follows, the hand arrives last and keeps going after the
 * shoulder has stopped. Three named effects fall out of that one lag, and it
 * is worth keeping them straight because they are usually confused:
 *
 *     overlapping action   the offset in TIME     — child starts later
 *     drag                 the offset in SPACE    — child trails behind
 *     follow-through       the child still moving after the parent stopped
 *
 * All three are the same delay observed three ways, which is why one function
 * produces all three.
 *
 * ── How it is implemented here, and why not with springs ───────────────────
 *
 * The obvious implementation is a spring per joint integrated over time. This
 * rig cannot do that: it is PARAMETRIC — every frame is solved from scratch
 * out of a phase value, with no state carried between frames, which is
 * precisely what makes it scrubbable and deterministic and lets the physics
 * checker sample frame 300 without simulating the 299 before it.
 *
 * So lag is done the way a hand animator does it: by sampling the leader's own
 * trajectory from earlier. `lag()` shifts phase rather than integrating state,
 * which gets overlap and drag exactly right, costs nothing, and keeps every
 * frame independent. Follow-through past a stop needs one extra term, which
 * `settle()` supplies.
 */

const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
const TAU = Math.PI * 2;

/**
 * The canonical delay: two frames — one drawing on twos — per link, and it
 * accumulates down the chain, so link 2 is 2 frames back, link 3 is 4, link 4
 * is 6. Everything below is expressed as a multiple of this.
 */
export const LINK_DELAY = 2;

/**
 * Sample a cyclic driver as it was `frames` ago.
 *
 * `phase` is in cycles, `cycleFrames` is how many frames one cycle takes, so
 * the shift is a pure phase subtraction. Wrapping keeps it in [0,1) — a cycle
 * has no beginning, so reaching back before "the start" is meaningless and the
 * value simply comes off the far end.
 */
export const lag = (phase, frames, cycleFrames) => {
  if (!cycleFrames) return phase;
  const p = phase - frames / cycleFrames;
  return ((p % 1) + 1) % 1;
};

/**
 * Delay for link `i` of a chain, in frames.
 *
 * `stiffness` scales the whole chain: a starched collar barely lags (0.3), a
 * loose coat tail lags more than the default (1.5-3). Tuning one number per
 * garment is the entire interface.
 */
export const linkDelay = (i, stiffness = 1) => i * LINK_DELAY * stiffness;

/**
 * Phases for every link of an `n`-link chain hanging off a driver.
 *
 * Link 0 is the anchor and never lags — it is bolted to the body. Everything
 * downstream trails it cumulatively.
 */
export const chainPhases = (phase, n, cycleFrames, stiffness = 1) => {
  const out = [];
  for (let i = 0; i < n; i++) out.push(lag(phase, linkDelay(i, stiffness), cycleFrames));
  return out;
};

/**
 * How far a point at `u` along a hanging thing swings, 0 at the anchor and 1
 * at the free end.
 *
 * A whip has a TENSION POINT: "one point is not moving, the next point's
 * moving a little bit, the point after that's moving a lot, and the point at
 * the end is moving the most." That is not linear — the growth accelerates
 * toward the tip, which a square captures well and a straight line does not.
 */
export const whipAmplitude = (u, power = 2) => Math.pow(clamp(u, 0, 1), power);

/**
 * Follow-through: what a trailing part does once its driver has stopped.
 *
 * `t` is frames since the stop. The part carries its momentum past the rest
 * position, comes back, and rings down — a decaying oscillation, which is the
 * one place this module does need real spring behaviour. It is safe here
 * because the input is "time since an event" rather than accumulated state,
 * so any frame can still be evaluated on its own.
 *
 * Returns a multiplier on the drag offset: 1 at the moment of the stop,
 * crossing zero and overshooting before settling to 0.
 */
export const settle = (t, {period = 9, decay = 0.14} = {}) => {
  if (t < 0) return 1;
  return Math.exp(-decay * t) * Math.cos((TAU * t) / period);
};

/**
 * Cloth against acceleration.
 *
 * Fabric lags the direction the body is accelerating, not the direction it is
 * travelling: a coat streams backward as you speed up, hangs when you cruise,
 * and swings forward when you stop. Reading velocity instead of acceleration
 * is why a coat can look pasted on even when it is technically moving.
 */
export const clothLag = (accel, drag = 1) => -accel * drag;

/**
 * The four poses a hanging edge cycles through as it reverses.
 *
 * "A whip or a flap is a wave with a tension point." Across one reversal the
 * edge passes through: C (fully flexed one way) → straight (root has turned,
 * tip has not) → S (inflection travelling down it) → C the other way. The
 * straight is the one most often missed, and its absence is why procedural
 * cloth so often looks like it is merely rotating.
 *
 * Returns a bend factor in [-1, 1] for the tip, and the inflection position
 * along the length where the curvature changes sign.
 */
export const whipPose = (phase) => {
  const p = ((phase % 1) + 1) % 1;
  const bend = Math.sin(p * TAU);
  const inflect = 0.5 - 0.5 * Math.cos(p * TAU * 2);
  return {bend, inflect, straight: Math.abs(bend) < 0.15};
};

/**
 * Arm swing that leads the legs slightly.
 *
 * Arms are not purely dragged by the torso — walking, they help drive it, and
 * the swing leads the corresponding foot rather than trailing it. The lead is
 * small; it is the difference between an arm that belongs to the character and
 * one that has been bolted on and left to flap.
 */
export const armPhase = (legPhase, lead = 0.04) => {
  const p = legPhase + 0.5 + lead;
  return ((p % 1) + 1) % 1;
};

export const overlap = {lag, linkDelay, chainPhases, whipAmplitude, settle, whipPose, armPhase};
