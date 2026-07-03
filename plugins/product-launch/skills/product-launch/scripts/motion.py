"""Easing + per-frame animation helpers (motion-design: personality-driven).

Everything is evaluated at a single output time `t` (seconds) so the orchestrator
can render any frame independently.
"""
from __future__ import annotations
import math


# ---- Cubic bezier easing (P0=(0,0), P3=(1,1)) ----
def _bezier(p1x, p1y, p2x, p2y):
    def eval_x(u):
        return 3 * (1 - u) ** 2 * u * p1x + 3 * (1 - u) * u ** 2 * p2x + u ** 3

    def eval_y(u):
        return 3 * (1 - u) ** 2 * u * p1y + 3 * (1 - u) * u ** 2 * p2y + u ** 3

    def f(x):
        x = max(0.0, min(1.0, x))
        lo, hi = 0.0, 1.0
        for _ in range(24):  # bisection on parameter u
            u = (lo + hi) / 2
            if eval_x(u) < x:
                lo = u
            else:
                hi = u
        return eval_y((lo + hi) / 2)

    return f


def ease_linear(x):
    return x


def ease_out_cubic(x):
    return 1 - (1 - x) ** 3


def ease_in_cubic(x):
    return x ** 3


def ease_in_out_sine(x):
    return -(math.cos(math.pi * x) - 1) / 2


def ease_out_expo(x):
    return 1.0 if x >= 1 else 1 - 2 ** (-10 * x)


def ease_out_back(x, s=1.70158):
    x -= 1
    return x * x * ((s + 1) * x + s) + 1


# ---- Personality presets ----
# overshoot is the peak scale beyond 1.0 during the pop (0 == none)
PERSONALITY = {
    "playful":   {"enter": 0.30, "exit": 0.18, "rise": 22, "overshoot": 0.12, "start_scale": 0.90, "ease": "out_back"},
    "premium":   {"enter": 0.50, "exit": 0.28, "rise": 16, "overshoot": 0.00, "start_scale": 0.96, "ease": "out_cubic"},
    "corporate": {"enter": 0.34, "exit": 0.20, "rise": 14, "overshoot": 0.03, "start_scale": 0.94, "ease": "out_cubic"},
    "energetic": {"enter": 0.22, "exit": 0.14, "rise": 26, "overshoot": 0.22, "start_scale": 0.88, "ease": "out_expo"},
}

_EASE = {
    "out_back": ease_out_back,
    "out_cubic": ease_out_cubic,
    "out_expo": ease_out_expo,
    "out": _bezier(0.2, 0, 0, 1),
}


def persona(name):
    return PERSONALITY.get((name or "playful").lower(), PERSONALITY["playful"])


class Appear:
    """Computes (opacity, scale, dy) for an element at time `t`.

    te/tx are enter/exit times (seconds, OUTPUT time). tx=None => holds to end.
    `pop` adds the scale overshoot + slide-up; otherwise a plain fade.
    """

    def __init__(self, te, tx, personality="playful", enter=None, exit=None,
                 rise=None, overshoot=None, start_scale=None, pop=True):
        p = persona(personality)
        self.te = te
        self.tx = tx
        self.enter = p["enter"] if enter is None else enter
        self.exit = p["exit"] if exit is None else exit
        self.rise = p["rise"] if rise is None else rise
        self.overshoot = p["overshoot"] if overshoot is None else overshoot
        self.start_scale = p["start_scale"] if start_scale is None else start_scale
        self.ease_in = _EASE.get(p["ease"], ease_out_cubic)
        self.ease_exit = ease_in_cubic
        self.pop = pop

    def at(self, t):
        te, tx = self.te, self.tx
        if t < te:
            return (0.0, self.start_scale if self.pop else 1.0, -self.rise if self.pop else 0.0)
        # entering
        if t < te + self.enter:
            p = (t - te) / self.enter
            op = min(1.0, _EASE["out"](p) if not self.pop else ease_out_cubic(p))
            if self.pop:
                e = self.ease_in(p)              # may overshoot (>1) for back/expo
                scale = self.start_scale + (1.0 - self.start_scale) * e
                if self.overshoot:
                    scale += self.overshoot * math.sin(math.pi * min(1.0, p)) * 0.6
                dy = -self.rise * (1 - ease_out_cubic(p))
            else:
                scale, dy = 1.0, 0.0
            return (op, scale, dy)
        # holding
        if tx is None or t < tx:
            return (1.0, 1.0, 0.0)
        # exiting
        if t < tx + self.exit:
            p = (t - tx) / self.exit
            op = 1.0 - self.ease_exit(p)
            scale = 1.0 - 0.04 * p if self.pop else 1.0
            dy = -self.rise * 0.7 * p if self.pop else 0.0
            return (max(0.0, op), scale, dy)
        return (0.0, 1.0, 0.0)


def slide_x(t, j, half=0.20, width=1920):
    """Full-screen push-wipe X offset + opacity for a panel centered on join `j`.

    Returns (dx, opacity). The panel fully covers the frame at t == j.
    """
    if t < j - half - 0.03 or t > j + half + 0.03:
        return (-width * 2, 0.0)
    if t < j:
        p = (t - (j - half)) / half
        p = max(0.0, min(1.0, p))
        return (-width * (1 - ease_in_out_sine(p)), 1.0)
    p = (t - j) / half
    p = max(0.0, min(1.0, p))
    return (width * ease_in_out_sine(p), 1.0)
