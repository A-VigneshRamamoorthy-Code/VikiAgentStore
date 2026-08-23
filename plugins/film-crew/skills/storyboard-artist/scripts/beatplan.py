"""The beat plan: what happens on screen, and when — before anyone decides how.

A beat plan is deliberately style-neutral. It says *"at this word, reveal the
factory; the keyword UNION CARBIDE lands here; circle it"*. It does not say
which font, which paper, which colour — that is the production designer's job,
and each style compiles this same plan into its own private storyboard.

That separation is the only reason a second style can ever be added. The
temptation is to write the plan in the vocabulary of the renderer you happen to
have; do that and the "style registry" is one style wearing a hat.

    python3 beatplan.py plan.json                 # validate; errors fail
    python3 beatplan.py plan.json --strict        # warnings fail too
    python3 beatplan.py plan.json --json
    python3 beatplan.py plan.json --shorts 3      # candidate Short windows
    python3 beatplan.py plan.json --measure vo/   # fill durations from the audio

Exit 0 pass, 1 fail. Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys

SCHEMA = 1

#: Above this share of the beats, one subject stops being a motif and starts
#: being the reason the film looks like a slideshow.
SUBJECT_SHARE_MAX = 0.12
#: Two beats this close together with the same subject put two copies of the
#: same picture on the board at once.
SUBJECT_GAP = 4

#: How many lines back a beat may reach for its subject. Narration is full of
#: pronouns, so the thing a line is *about* is often named a line or two
#: earlier.
ANTECEDENT = 2

#: Words too common to prove a subject came from its line. "the note" and "the
#: parachute" share nothing but grammar with "he took the money".
#:
#: The three-letter words matter more than they look. The length floor below is
#: 3, not 4, because `sea`, `map`, `car`, `sky` and `gun` are all real
#: illustration names — with a floor of 4 they stemmed to nothing and a whole
#: rotation built from them was invisible to this check.
_STOPWORDS = frozenset("""
a an and are as at be been but by for from had has have he her him his how i
in into is it its of on or our out she that the their them then there they
this to was were what when where which who will with would you your not no
all any can did few for got had has her him his its let may new now off old
one own per put say see set she too two use via was way yes yet nor due
""".split())


#: Plurals no rule reaches. Small on purpose — these are the ones that turned
#: up in real plans, not a dictionary.
_IRREGULAR = {
    "men": "man", "women": "woman", "children": "child", "people": "person",
    "feet": "foot", "teeth": "tooth", "lives": "life", "wives": "wife",
    "knives": "knife", "leaves": "leaf", "thieves": "thief",
}


def _stems(text):
    """Content words of ``text``, crudely stemmed so plurals still match.

    Not linguistics — just enough that "parachutes" in a line supports a beat
    whose subject is "parachute", while "the" supports nothing. Three cases
    are handled specially because each of them silently broke the check:
    ``-ss`` words (``glass`` must not become ``glas`` when ``glasses``
    becomes ``glass``), ``-ies`` (``stories`` must reach ``story``), and a
    trailing ``e`` (``parachutes`` strips to ``parachute``, so ``parachute``
    has to lose the ``e`` too).
    """
    out = []
    for w in re.findall(r"[a-z]+", str(text or "").lower()):
        if len(w) < 3 or w in _STOPWORDS:
            continue
        w = _IRREGULAR.get(w, w)
        if w.endswith("ies") and len(w) > 4:
            w = w[:-3] + "y"
        elif w.endswith("ss"):
            pass
        elif w.endswith("es") and len(w) - 2 >= 4:
            w = w[:-2]
        elif w.endswith("s") and len(w) - 1 >= 3:
            # 3, not 4, because the floor above admits three-letter words and
            # `car`, `map`, `sea` and `gun` are all catalogue names. Left at 4,
            # `cars` never stripped to `car` and a beat that honestly named
            # what its line said was counted as unsupported. The `-es` guard
            # stays at 4 so `notes` still routes through here to `note` rather
            # than being cut to `not`.
            w = w[:-1]
        # A second pass, because the two endings stack: "hijackings" is a
        # plural *and* a gerund, and stopping after the -s leaves "hijacking",
        # which "hijack" can never match.
        if w.endswith("ing") and len(w) - 3 >= 4:
            w = w[:-3]
        elif w.endswith("ed") and len(w) - 2 >= 4:
            w = w[:-2]
        if len(w) > 4 and w.endswith("e"):
            w = w[:-1]
        out.append(w)
    return out

#: What a beat is *for*. Closed on purpose: a style has to be able to render
#: every intent, and an open vocabulary means a plan that silently degrades on
#: a style that has never heard of "kenburns".
INTENTS = {
    "establish":  "introduce a place, object or person for the first time",
    "reveal":     "show the thing the narration has been withholding",
    "evidence":   "put a document, quote or figure on screen",
    "portrait":   "a person, held long enough to matter",
    "locate":     "where this is happening — map, route, position",
    "compare":    "two things side by side",
    "list":       "enumerate; items arrive one at a time",
    "annotate":   "mark up something already on screen",
    "emphasise":  "make one already-present thing dominant",
    "transition": "close one movement and open the next",
}

#: How much of the frame a beat is allowed to claim.
SAFE = {"full", "vertical", "square"}

#: Pacing bounds. Slower than MAX and the picture is a slideshow; faster than
#: MIN and nobody can read what arrived before it is replaced.
BEAT_MIN_S = 1.5
BEAT_MAX_S = 6.0
BEAT_TARGET_S = (2.0, 4.0)

TIME_RE = re.compile(r"^(?P<line>[A-Za-z][\w-]*)(?P<end>\.end)?"
                     r"(?:(?P<sign>[+-])(?P<off>\d+(?:\.\d+)?))?$")


class Problem(object):
    def __init__(self, level, where, message):
        self.level, self.where, self.message = level, where, message

    def __str__(self):
        return "%-7s %-14s %s" % (self.level, self.where, self.message)

    def as_dict(self):
        return {"level": self.level, "where": self.where, "message": self.message}


# ------------------------------------------------------------------ timing --


def parse_time(spec):
    """``"l4+0.35"`` → ``("l4", False, 0.35)``. Absolute seconds → ``(None, ...)``."""
    if isinstance(spec, (int, float)):
        return None, False, float(spec)
    m = TIME_RE.match(str(spec).strip())
    if not m:
        raise ValueError("cannot read %r as a time" % spec)
    off = float(m.group("off") or 0.0)
    if m.group("sign") == "-":
        off = -off
    return m.group("line"), bool(m.group("end")), off


def probe_duration(path):
    """Seconds of audio, via ffprobe. ``None`` if it cannot be read."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=60)
        return float(out.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def timeline(plan, root="."):
    """Absolute start/end of every narration line, in seconds.

    Durations come from ``duration`` when present, else from measuring
    ``audio``. A line with neither is given 0 and reported by the validator —
    silently assuming a length is how a board drifts out of sync with its own
    voiceover.
    """
    t, out, missing = 0.0, {}, []
    for line in plan.get("narration") or []:
        lid = line.get("id")
        dur = line.get("duration")
        if dur is None and line.get("audio"):
            p = line["audio"]
            p = p if os.path.isabs(p) else os.path.join(root, p)
            dur = probe_duration(p) if os.path.exists(p) else None
        if dur is None:
            missing.append(lid)
            dur = 0.0
        d = as_number(dur) or 0.0
        if as_number(dur) is None:
            missing.append(lid)
        out[lid] = (t, t + d)
        t += d + (as_number(line.get("gap_after")) or 0.0)
    return out, t, missing


def as_number(v):
    """``v`` as a float, or ``None`` if it is not a number at all.

    A plan is hand-written JSON, so `"emphasis": "high"` is a normal thing for
    a person to type. Coercing it with a bare ``float()`` turns a validator —
    whose entire job is to explain what is wrong — into a traceback.

    ``NaN`` and the infinities are rejected as well. ``float("nan")`` succeeds,
    and every comparison against the result is false, so a NaN duration passes
    each range check and then poisons the timeline arithmetic downstream.
    """
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def resolve(spec, times):
    line, at_end, off = parse_time(spec)
    if line is None:
        return off
    if line not in times:
        raise KeyError(line)
    return (times[line][1] if at_end else times[line][0]) + off


# --------------------------------------------------------------- validation --


def validate(plan, root=".", measure=True):
    P = []
    add = lambda lvl, where, msg: P.append(Problem(lvl, where, msg))

    if plan.get("schema") != SCHEMA:
        add("error", "schema", "expected schema %s, got %r — this validator "
                               "cannot read that plan" % (SCHEMA, plan.get("schema")))
        return P, {}, 0.0

    # --- narration --------------------------------------------------------
    lines = plan.get("narration") or []
    if not lines:
        add("error", "narration", "a plan with no narration has nothing to time "
                                  "its beats against")
    seen = set()
    order = []
    for i, line in enumerate(lines):
        where = "narration[%d]" % i
        lid = line.get("id")
        if not lid:
            add("error", where, "every line needs an id — beats refer to it")
        elif lid in seen:
            add("error", where, "duplicate line id %r" % lid)
        else:
            order.append(lid)
        seen.add(lid)
        if not line.get("audio") and line.get("duration") is None:
            add("warn", where, "neither audio nor duration: %r will occupy no "
                               "time until the voice booth has run" % lid)
        if line.get("audio"):
            p = line["audio"] if os.path.isabs(line["audio"]) \
                else os.path.join(root, line["audio"])
            if not os.path.exists(p):
                add("error", where, "audio %r does not exist" % line["audio"])
        gap = line.get("gap_after")
        if gap is not None:
            g = as_number(gap)
            if g is None:
                add("error", where, "gap_after must be a number of seconds, "
                                    "got %r" % (gap,))
            elif not 0 <= g <= 4:
                add("warn", where, "gap_after %.2fs is outside the 0-4s that "
                                   "reads as pacing rather than a fault" % g)
        if line.get("duration") is not None \
                and as_number(line["duration"]) is None:
            add("error", where, "duration must be a number of seconds, got %r"
                % (line["duration"],))

    times, total, unmeasured = (timeline(plan, root) if measure else ({}, 0.0, []))
    if unmeasured and measure:
        add("warn", "narration", "%d line(s) had no measurable length (%s) — every "
            "beat time after them is a guess"
            % (len(unmeasured), ", ".join(str(x) for x in unmeasured[:5])))

    # --- beats ------------------------------------------------------------
    beats = plan.get("beats") or []
    if not beats:
        add("error", "beats", "no beats: this is a radio programme")
    last_t, last_id = None, None
    bseen = set()
    for i, line in enumerate(plan.get("narration") or []):
        d = line.get("duration")
        if d is None:
            continue
        n = as_number(d)
        if n is None:
            add("error", "narration[%d]" % i,
                "duration must be a number, got %r" % (d,))
        elif n <= 0:
            # A zero-length line stacks every following beat onto the same
            # instant; a negative one runs the timeline backwards. Both pass
            # every later check and only fall apart during the render.
            add("error", "narration[%d]" % i,
                "duration %s is not a length of time — a line takes longer "
                "than zero seconds to say" % (d,))
        g = line.get("gap_after")
        if g is not None and (as_number(g) is None or as_number(g) < 0):
            add("error", "narration[%d]" % i,
                "gap_after %r is not a length of time" % (g,))

    for i, b in enumerate(beats):
        where = "beats[%d]" % i
        bid = b.get("id")
        if not bid:
            add("error", where, "every beat needs an id")
        elif bid in bseen:
            add("error", where, "duplicate beat id %r" % bid)
        bseen.add(bid)

        intent = b.get("intent")
        if intent not in INTENTS:
            add("error", where, "intent %r is not one of: %s"
                % (intent, ", ".join(sorted(INTENTS))))
        if b.get("safe") and b["safe"] not in SAFE:
            add("error", where, "safe %r is not one of: %s"
                % (b["safe"], ", ".join(sorted(SAFE))))
        em = b.get("emphasis")
        if em is not None:
            e = as_number(em)
            if e is None or not 0 <= e <= 1:
                add("error", where, "emphasis must be a number 0..1, got %r" % (em,))

        # A beat with no subject and no hint-bearing asset validates perfectly
        # and then compiles to a placeholder rectangle, so the first sign that
        # the plan was wrong is a finished render full of grey boxes. Say it
        # here instead.
        assets = [a for a in (b.get("assets") or []) if isinstance(a, dict)]
        if not b.get("subject") and not any(a.get("hint") for a in assets) \
                and not any(a.get("src") for a in assets):
            add("warn", where, "no `subject` and no asset with a `hint` or "
                               "`src` — a style has nothing to illustrate, and "
                               "will fall back to a placeholder")

        if "at" not in b:
            add("error", where, "no `at`: a beat that is not tied to a word "
                                "will land on the wrong one")
            continue
        try:
            line, _, _ = parse_time(b["at"])
        except ValueError as e:
            add("error", where, str(e))
            continue
        if line is not None and line not in seen:
            add("error", where, "`at` refers to line %r, which does not exist" % line)
            continue
        if line is None:
            add("warn", where, "absolute time %r: a rewrite of the script will "
                               "desynchronise it. Prefer \"l4+0.35\"." % b["at"])

        if not measure or not times:
            continue
        try:
            t = resolve(b["at"], times)
        except KeyError:
            continue
        if last_t is not None:
            gap = t - last_t
            if gap < 0:
                add("error", where, "lands at %.2fs, before %r at %.2fs — beats "
                    "must be in order" % (t, last_id, last_t))
            elif gap < BEAT_MIN_S:
                add("warn", where, "only %.2fs after %r; under %.1fs the viewer "
                    "cannot read what arrived" % (gap, last_id, BEAT_MIN_S))
            elif gap > BEAT_MAX_S:
                add("warn", where, "%.2fs after %r; over %.1fs the picture stops "
                    "moving" % (gap, last_id, BEAT_MAX_S))
        last_t, last_id = t, bid

    if beats and total > 0 and measure:
        density = total / max(1, len(beats))
        if not BEAT_TARGET_S[0] <= density <= BEAT_TARGET_S[1]:
            add("warn", "beats", "one beat every %.1fs across %.0fs; the band that "
                "holds attention is %.0f-%.0fs"
                % (density, total, BEAT_TARGET_S[0], BEAT_TARGET_S[1]))

    # --- keywords land on their own word ----------------------------------
    text_of = {l.get("id"): (l.get("text") or "").lower() for l in lines}
    for i, b in enumerate(beats):
        try:
            line, _, _ = parse_time(b.get("at", 0))
        except ValueError:
            continue
        for kw in b.get("keywords") or []:
            head = re.split(r"[^\w']+", str(kw).strip().lower())[0] if kw else ""
            if line and head and head not in text_of.get(line, ""):
                add("warn", "beats[%d]" % i,
                    "keyword %r is not spoken in %s — a chip that names a word "
                    "the narrator never says reads as a caption" % (kw, line))

    # --- loops are promises -----------------------------------------------
    for i, loop in enumerate(plan.get("loops") or []):
        where = "loops[%d]" % i
        for field in ("opens", "pays"):
            ref = loop.get(field)
            if not ref:
                add("error", where, "a loop needs both `opens` and `pays` — an "
                                    "unpaid loop is the cheapest way to lose an audience")
            elif ref not in seen:
                add("error", where, "%s refers to line %r, which does not exist"
                    % (field, ref))
        if loop.get("opens") in seen and loop.get("pays") in seen:
            if order.index(loop["opens"]) >= order.index(loop["pays"]):
                add("error", where, "%r pays at or before it opens — a loop has "
                    "to be closed after it is opened to be worth opening"
                    % loop.get("id", where))

    # --- does the film have anything to look at? --------------------------
    # A plan validates line by line and still describes a slideshow: every
    # beat legal, every beat asking for the same picture. That only becomes
    # visible when the beats are counted together, and by then it is a render.
    subs, first = [], {}
    for i, b in enumerate(plan.get("beats") or []):
        assets = [a for a in (b.get("assets") or []) if isinstance(a, dict)]
        if isinstance(b.get("assets"), list) and not b["assets"]:
            # Deliberately no picture; it cannot repeat one.
            subs.append("")
            continue
        s = next((a.get("hint") for a in assets
                  if a.get("hint") and a.get("kind")
                  in (None, "illustration", "art")), None) or b.get("subject")
        s = re.sub(r"\s+", " ", str(s or "")).strip().lower()
        subs.append(s)
        if s and s not in first:
            first[s] = i
    drawn = [s for s in subs if s]
    if drawn:
        tally = {}
        for s in drawn:
            tally[s] = tally.get(s, 0) + 1
        for s, n in sorted(tally.items(), key=lambda kv: -kv[1]):
            if n > max(3, len(drawn) * SUBJECT_SHARE_MAX):
                add("warn", "beats", "%r is the subject of %d of %d beats "
                    "(%d%%). One picture cannot carry that much of a film — "
                    "give those beats the subject of their own line"
                    % (s, n, len(drawn), round(100.0 * n / len(drawn))))
        near = [(i, subs[i]) for i in range(1, len(subs))
                if subs[i] and subs[i] in subs[max(0, i - SUBJECT_GAP):i]]
        if near:
            add("warn", "beats", "%d beats repeat the subject of a beat less "
                "than %d before them, so the same picture is on screen twice "
                "at once (beat %d: %r%s). Vary them."
                % (len(near), SUBJECT_GAP + 1, near[0][0], near[0][1],
                   ", and %d more" % (len(near) - 1) if len(near) > 1 else ""))
        if len(tally) < len(drawn) / 8.0 and len(drawn) >= 24:
            add("warn", "beats", "%d beats are carried by only %d different "
                "subjects. Read each line and name what it puts on screen."
                % (len(drawn), len(tally)))

    # --- a picture the line never asked for --------------------------------
    # Variety is easy to fake. Rotating a handful of decorative pictures
    # through the beats scores perfectly on every test above while putting a
    # moon over a line about a flight attendant, which is worse than the
    # repetition it replaced: the viewer stops trusting that the picture means
    # anything. So a beat has to be *supported by what is being said* — some
    # word of its subject, or of any hint it carries, must appear in the line
    # it sits on.
    #
    # Two allowances, both learned from real plans this check failed:
    #   * every hint counts, whatever its `kind`. A footage hint of "village
    #     dawn" over "before dawn, Jyoti walks" is exactly on the line, and
    #     ignoring it because the kind is not `illustration` flagged a
    #     correct beat.
    #   * the previous two lines count too. Narration uses pronouns — "She is
    #     one of four hundred women" is about Jyoti because the line before
    #     said so, and a subject naming her is right, not decorative.
    order = [l.get("id") for l in (plan.get("narration") or [])]
    pos_of = {lid: i for i, lid in enumerate(order) if lid}
    unsupported = []
    checked = 0
    for i, b in enumerate(plan.get("beats") or []):
        cands = [a.get("hint") for a in (b.get("assets") or [])
                 if isinstance(a, dict) and a.get("hint")]
        if isinstance(b.get("assets"), list) and not b["assets"]:
            continue
        cands.append(b.get("subject"))
        cands = [c for c in cands if c]
        if not cands:
            continue
        try:
            lid = parse_time(b.get("at", 0))[0]
        except ValueError:
            continue
        if lid not in pos_of:
            continue
        window = [text_of.get(order[j])
                  for j in range(max(0, pos_of[lid] - ANTECEDENT), pos_of[lid] + 1)]
        said = set()
        for t in window:
            if t:
                said |= set(_stems(t))
        if not said:
            continue
        # A candidate that stems to nothing cannot be judged either way. It
        # must not count as *passing* — "the sea", "a map" and "a car" are all
        # real catalogue names that stem to nothing, so treating them as
        # supported made the check blind to precisely the decorative rotation
        # it exists to catch. A beat none of whose candidates can be judged is
        # left out of the denominator too, rather than diluting the share.
        judgeable = [set(s) for s in (_stems(c) for c in cands) if s]
        if not judgeable:
            continue
        checked += 1
        if any(said & s for s in judgeable):
            continue
        unsupported.append((b.get("id") or "beat %d" % i, cands[0], lid))
    if unsupported and checked:
        share = 100.0 * len(unsupported) / checked
        # On a six-beat plan one stemmer miss is seventeen points, so the
        # share alone cannot decide. Only a plan long enough for the number
        # to mean something may fail the build on it.
        sev = "error" if (share >= 35 and checked >= 20) else "warn"
        add(sev, "beats", "%d of %d beats (%d%%) ask for a picture their line "
            "never mentions — %s wants %r from line %s. Name the thing the "
            "line just said; a picture chosen for variety alone reads as "
            "decoration."
            % (len(unsupported), checked, round(share), unsupported[0][0],
               unsupported[0][1], unsupported[0][2]))

    # --- hooks feed the Shorts --------------------------------------------
    hooks = plan.get("hooks") or []
    for i, h in enumerate(hooks):
        where = "hooks[%d]" % i
        for field in ("from", "to"):
            if h.get(field) not in seen:
                add("error", where, "%s refers to line %r, which does not exist"
                    % (field, h.get(field)))
    if not any(h.get("short_worthy") for h in hooks):
        add("warn", "hooks", "no hook is marked short_worthy — nothing tells the "
                             "editor where a Short could be cut from")
    return P, times, total


# ------------------------------------------------------------------ shorts --


def shorts(plan, want, seconds, root="."):
    """Candidate Short windows, best first.

    A Short is cut from a hook the storyboard artist already marked, not from an
    arbitrary loud moment: the whole point of marking hooks during boarding is
    that the decision is made once, with the script in view.
    """
    times, total, _ = timeline(plan, root)
    out = []
    for h in plan.get("hooks") or []:
        if not h.get("short_worthy"):
            continue
        a, b = h.get("from"), h.get("to")
        if a not in times or b not in times:
            continue
        start, end = times[a][0], times[b][1]
        span = end - start
        out.append({
            "hook": h.get("id"),
            "kind": h.get("kind"),
            "why": h.get("why"),
            "from_line": a, "to_line": b,
            "start": round(start, 2), "end": round(end, 2),
            "seconds": round(span, 2),
            "fits": abs(span - seconds) <= seconds * 0.5,
            "note": ("trim to ~%ds" % seconds) if span > seconds * 1.5
                    else ("extend to ~%ds" % seconds) if span < seconds * 0.5
                    else "usable as-is",
        })
    out.sort(key=lambda s: (not s["fits"], abs(s["seconds"] - seconds)))
    if want and len(out) < want:
        out.append({"shortfall": want - len(out),
                    "note": "only %d hook(s) are marked short_worthy but %d "
                            "Shorts were asked for. Mark more hooks in the beat "
                            "plan rather than inventing windows." % (len(out), want)})
    return out[:want] if want and len(out) >= want else out


# --------------------------------------------------------------------- cli --


def main(argv=None):
    p = argparse.ArgumentParser(prog="beatplan.py",
                                description="Validate a beat plan.")
    p.add_argument("plan")
    p.add_argument("--strict", action="store_true", help="warnings fail too")
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-measure", action="store_true",
                   help="skip ffprobe; structural checks only")
    p.add_argument("--shorts", type=int, metavar="N",
                   help="print N candidate Short windows instead of validating")
    p.add_argument("--short-seconds", type=int, default=40)
    p.add_argument("--measure", metavar="DIR",
                   help="resolve audio paths relative to DIR (default: the "
                        "plan's own directory)")
    a = p.parse_args(argv)

    try:
        with open(a.plan, encoding="utf-8") as fh:
            plan = json.load(fh)
    except (OSError, ValueError) as e:
        print("beatplan: cannot read %s: %s" % (a.plan, e), file=sys.stderr)
        return 1

    root = a.measure or os.path.dirname(os.path.abspath(a.plan))

    if a.shorts is not None:
        found = shorts(plan, a.shorts, a.short_seconds, root)
        if a.json:
            print(json.dumps(found, indent=2))
        else:
            for s in found:
                if "shortfall" in s:
                    print("\n! %s" % s["note"])
                    continue
                print("%-6s %6.2f-%-6.2f %5.1fs  %-12s %s"
                      % (s["hook"], s["start"], s["end"], s["seconds"],
                         s["kind"] or "", s["note"]))
        return 0 if found and "shortfall" not in found[-1] else 1

    problems, times, total = validate(plan, root, measure=not a.no_measure)
    errors = [x for x in problems if x.level == "error"]
    warns = [x for x in problems if x.level == "warn"]

    if a.json:
        print(json.dumps({
            "ok": not errors and not (a.strict and warns),
            "runtime_seconds": round(total, 2),
            "beats": len(plan.get("beats") or []),
            "problems": [x.as_dict() for x in problems]}, indent=2))
    else:
        for x in problems:
            print(x)
        print("\n%d error(s), %d warning(s) — %.1fs, %d beats"
              % (len(errors), len(warns), total, len(plan.get("beats") or [])))
    return 1 if errors or (a.strict and warns) else 0


if __name__ == "__main__":
    raise SystemExit(main())
