#!/usr/bin/env python3
"""Compile a style-neutral beat plan into a stock-footage storyboard.

The beat plan says *what is on screen and when*. This turns that into the
vocabulary of a stock-footage cut: a **shot list**, where every shot carries a
search query, a duration, a camera move and a grade — and, once `fetch.py` has
run, the actual clip that answers it.

    python3 compile.py beat-plan.json -o storyboard.json
    python3 compile.py beat-plan.json --motion-plan motion-plan.json -o sb.json
    python3 compile.py beat-plan.json --check

The compile step deliberately does **not** touch the network. Compiling is
cheap, repeatable and offline; searching is metered, slow and non-deterministic.
Keeping them apart is what lets you re-cut a film a dozen times against footage
you already have, and it is why the query lives in the storyboard as data rather
than being computed inside the renderer.

What this file is really doing is translating *prose* into *search*. That is the
whole craft of the style, and it is much harder than it looks: "the vault door
closes on ninety seconds of silence" is a sentence, and `vault door closing` is
a query. Get that translation wrong and the film is a beautiful, irrelevant
screensaver.
"""

import argparse
import json
import math
import os
import re
import sys

SCHEMA = 1

#: The frame shapes declared in style.json, as exact encoder dimensions rather
#: than a ratio: both sides even, and the vertical one the size a phone plays.
FRAME = {
    "16:9": {"width": 1920, "height": 1080},
    "9:16": {"width": 1080, "height": 1920},
    "1:1": {"width": 1080, "height": 1080},
}

#: Words that are never worth searching for. A stock search engine matches on
#: subject nouns; feeding it articles and prepositions dilutes every term that
#: mattered. This is not a general English stopword list -- it keeps colour and
#: number words, which are strong visual search terms ("red car", "two people").
STOP = {
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "with", "and", "or",
    "but", "as", "by", "from", "into", "onto", "over", "under", "is", "are",
    "was", "were", "be", "been", "being", "it", "its", "this", "that", "these",
    "those", "he", "she", "they", "them", "his", "her", "their", "which",
    "who", "whom", "what", "when", "where", "while", "there", "here", "then",
    "than", "so", "such", "very", "just", "only", "also", "still", "yet",
    "has", "have", "had", "do", "does", "did", "will", "would", "can", "could",
    "should", "may", "might", "must", "one", "up", "down", "out", "off",
    "again", "more", "most", "some", "any", "all", "no", "not", "own", "same",
    "too", "s", "t",
}

#: Terms that are *abstractions* -- true of the story, useless to a search
#: engine, because no camera has ever photographed one. A query that reduces to
#: nothing but these has failed and must be reported rather than sent.
ABSTRACT = {
    "moment", "time", "times", "thing", "things", "way", "ways", "idea",
    "reason", "chance", "truth", "fact", "point", "sense", "kind", "sort",
    "part", "case", "matter", "problem", "question", "answer", "story",
    "history", "future", "past", "present", "beginning", "end", "start",
    "finish", "silence", "nothing", "everything", "anything", "something",
    "someone", "anyone", "everyone", "nobody", "life", "death", "fear",
    "hope", "love", "luck", "plan", "plans", "mistake", "difference",
}

#: How a beat's intent becomes a camera move over the footage. A stock clip is
#: already moving, so this is a *second* move layered on the first -- which is
#: why almost every entry is small. `hold` means the clip's own motion is the
#: only motion, and it is the right answer far more often than it feels.
MOVE = {
    "establish":  "push-in",
    "reveal":     "push-in",
    "evidence":   "hold",
    "portrait":   "push-in",
    "locate":     "drift-left",
    "compare":    "hold",
    "list":       "drift-up",
    "annotate":   "hold",
    "emphasise":  "push-in",
    "transition": "drift-right",
}

#: Playback speed by intent. Stock footage is shot at a neutral pace; the cut
#: is where a film gets its tempo. A held beat slows fractionally, an impact
#: beat runs a touch hot. Kept close to 1.0 -- past about 1.25 the motion
#: judders once it is resampled to the timeline's fps.
SPEED = {
    "evidence": 0.92,
    "portrait": 0.94,
    "transition": 1.08,
}

#: Shortest and longest a single shot may hold. Under ~1.2 s a viewer registers
#: a flash rather than a picture.
#:
#: The 5 s ceiling is not a guess. It is the rule ColdFusion's Dagogo Altraide
#: states for his own films: "as a rule of thumb, no scene should last more
#: than five seconds" (Tubefilter, 2017). It matches what the footage can
#: support -- past about five seconds a stock clip has visibly run out of
#: things to show and the film goes slack.
#:
#: The compiler still merges nothing, because a merge is a story decision. It
#: does offer to *split*, which is an editing decision and therefore this
#: style's business: see `add_cutaways()`.
MIN_SHOT = 1.2
MAX_SHOT = 5.0

#: Grades, and the words that choose one. A grade is the single strongest
#: unifying device this style has: forty clips shot by forty strangers in forty
#: different lighting conditions become one film mainly because they were all
#: pushed through the same curve. Selection is by the story's own words --
#: see the "ask the story, not the default" rule in the style contract.
#:
#: Each is an ffmpeg filter chain. `eq` moves contrast/brightness/saturation,
#: `colorbalance` tints shadows/midtones/highlights independently, and
#: `curves` does the final filmic shaping.
GRADES = {
    "noir": {
        "about": "cool, desaturated, milky blacks — film noir, not darkness",
        "target": 0.40,
        "filter": "eq=contrast=1.10:saturation=0.62,"
                  "colorbalance=rs=-0.05:bs=0.10:rm=-0.02:bm=0.05:bh=0.04,"
                  "curves=all='0/0.06 0.5/0.5 1/0.95'",
        "words": ("night", "dark", "rain", "crime", "police", "chase", "steal",
                  "robbery", "heist", "shadow", "cold", "siren", "vault",
                  "getaway", "alarm", "pursuit", "escape", "wet", "storm"),
    },
    "ember": {
        "about": "warm highlights, amber midtones, lifted blacks",
        "target": 0.48,
        "filter": "eq=contrast=1.08:saturation=1.06,"
                  "colorbalance=rs=0.05:bs=-0.05:rm=0.07:gm=0.02:bm=-0.07:rh=0.06:bh=-0.06,"
                  "curves=all='0/0.05 0.5/0.53 1/1'",
        "words": ("fire", "sun", "sunset", "desert", "warm", "summer", "gold",
                  "harvest", "autumn", "dawn", "kitchen", "home", "family"),
    },
    "verdant": {
        "about": "deep greens, cool shadows, natural saturation",
        "target": 0.46,
        "filter": "eq=contrast=1.10:saturation=1.14,"
                  "colorbalance=gs=0.05:bs=0.03:gm=0.04:rm=-0.03:gh=0.03,"
                  "curves=all='0/0.04 0.5/0.5 1/0.99'",
        "words": ("forest", "tree", "trees", "mountain", "river", "nature",
                  "wild", "green", "leaf", "leaves", "rain", "jungle", "farm",
                  "field", "garden", "valley"),
    },
    "clinical": {
        "about": "neutral, bright, high-key — the look of a product film",
        "target": 0.52,
        "filter": "eq=contrast=1.05:saturation=0.98,"
                  "colorbalance=bs=0.02:bm=0.01,"
                  "curves=all='0/0.04 0.5/0.52 1/1'",
        "words": ("office", "work", "business", "team", "meeting", "data",
                  "laptop", "computer", "market", "company", "product",
                  "software", "science", "lab", "research", "study"),
    },
    "oceanic": {
        "about": "cyan highlights, deep blue shadows, cool and wide",
        "target": 0.46,
        "filter": "eq=contrast=1.12:saturation=1.05,"
                  "colorbalance=bs=0.10:gs=0.03:bm=0.06:rm=-0.04:bh=0.04,"
                  "curves=all='0/0.05 0.5/0.5 1/0.98'",
        "words": ("sea", "ocean", "water", "wave", "waves", "coast", "beach",
                  "ship", "boat", "harbour", "harbor", "island", "sail",
                  "swim", "dive", "ice", "arctic", "winter", "snow"),
    },
    "faded": {
        "about": "lifted blacks, low saturation, the look of memory",
        "target": 0.50,
        "filter": "eq=contrast=0.94:saturation=0.72,"
                  "colorbalance=rs=0.04:bs=0.04:rm=0.02:bm=0.02,"
                  "curves=all='0/0.10 0.5/0.52 1/0.94'",
        "words": ("memory", "remember", "old", "childhood", "grandmother",
                  "grandfather", "letter", "photograph", "album", "ago",
                  "forgotten", "return", "home", "village"),
    },
    "reportage": {
        "about": "cool, desaturated, lifted blacks — the tech-documentary look",
        "target": 0.42,
        # Cool and desaturated is what the sources agree on. The warm-midtone
        # half of a teal-and-orange split is deliberately absent: it could not
        # be confirmed from frame evidence, and a split-tone applied wrongly
        # is visible on every single shot. Blacks lift rather than crush --
        # the register is documentary, not thriller.
        "filter": "eq=contrast=1.06:saturation=0.80,"
                  "colorbalance=rs=-0.04:gs=0.02:bs=0.06:bm=0.03,"
                  "curves=all='0/0.07 0.5/0.5 1/0.96'",
        "words": ("startup", "founder", "investor", "investors", "billion",
                  "valuation", "acquisition", "bankruptcy", "collapse",
                  "empire", "giant", "rival", "shares", "ipo", "boardroom",
                  "merger", "revenue", "downfall", "decline"),
    },
}
DEFAULT_GRADE = "clinical"

#: Music moods, and the words that pick one. Mirrors the sound designer's
#: vocabulary so that a film's picture and its score are chosen by the same
#: word rather than by two unrelated defaults.
MOODS = {
    "tension": ("chase", "police", "alarm", "run", "escape", "crime", "steal",
                "robbery", "heist", "pursuit", "danger", "siren", "hunt"),
    "dread": ("dark", "death", "disaster", "collapse", "fire", "storm",
              "warning", "lost", "trapped", "fail"),
    "triumph": ("win", "won", "victory", "record", "first", "success",
                "built", "achieve", "launch", "rise"),
    "elegy": ("died", "loss", "grief", "gone", "last", "final", "farewell",
              "mourn", "remember"),
    "curious": ("discover", "found", "how", "why", "question", "experiment",
                "strange", "secret", "mystery"),
    "reflective": ("memory", "quiet", "alone", "slow", "winter", "still",
                   "years", "ago", "home"),
}
DEFAULT_MOOD = "reflective"

TIME_RE = re.compile(r"^(l\d+)(\.end)?(?:([+-])([0-9.]+))?$")
WORD_RE = re.compile(r"[a-z0-9']+")

INTENTS = set(MOVE)


def die(msg):
    print("stock/compile: %s" % msg, file=sys.stderr)
    raise SystemExit(1)


def warn(msg):
    print("stock/compile: %s" % msg, file=sys.stderr)


def load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as e:
        die("cannot read %s: %s" % (path, e))


def words(text):
    return WORD_RE.findall(str(text or "").lower())


# ------------------------------------------------------------------ timing --


def line_index(plan):
    return {l.get("id"): l for l in plan.get("narration") or []}


def line_starts(plan):
    """Absolute start and end of every narration line.

    The film's clock is the voice's clock. A line contributes its own duration
    plus the gap that follows it, and `timing.lead_in` shifts everything so a
    film can breathe before the first word.
    """
    starts, ends = {}, {}
    t = float((plan.get("timing") or {}).get("lead_in") or 0.0)
    for l in plan.get("narration") or []:
        d = float(l.get("duration") or 0.0)
        starts[l.get("id")] = round(t, 3)
        ends[l.get("id")] = round(t + d, 3)
        t += d + float(l.get("gap_after") or 0.0)
    return starts, ends, round(t, 3)


def resolve_at(ref, starts, ends):
    """A beat's time reference, in seconds."""
    if isinstance(ref, (int, float)):
        return float(ref)
    m = TIME_RE.match(str(ref or "").strip())
    if not m:
        die("bad time reference %r (want l4, l4+0.2, l4.end)" % ref)
    line, is_end, sign, delta = m.groups()
    table = ends if is_end else starts
    if line not in table:
        die("time reference %r names a line that does not exist" % ref)
    t = table[line]
    if sign:
        t += float(delta) * (1 if sign == "+" else -1)
    return round(max(0.0, t), 3)


def line_of_beat(beat):
    m = TIME_RE.match(str(beat.get("at") or "").strip())
    return m.group(1) if m else None


# ------------------------------------------------------------------ search --


def query_from(beat, lines):
    """The search query for a beat, and the alternates to fall back through.

    Priority is deliberate and worth stating, because getting it backwards is
    what makes a stock film look automated:

    1. **`assets[].hint`** — the storyboard artist wrote this *as* a search
       query. It is the one field in the beat plan whose author knew a camera
       had to have pointed at the thing. Always prefer it.
    2. **`subject`** — prose. Reduced to its nouns, which is lossy but honest.
    3. **the narration line** — a last resort, and usually a bad query, so it
       is only ever an alternate.

    Alternates exist because stock search is not a lookup. A query returns
    nothing far more often than feels reasonable, and the difference between a
    film that finishes and one that stalls is having a second and third way to
    ask.
    """
    hints = [str((a or {}).get("hint") or "").strip()
             for a in (beat.get("assets") or [])
             if (a or {}).get("hint")]

    subject = str(beat.get("subject") or "").strip()
    subj_terms = [w for w in words(subject) if w not in STOP]

    primary = ""
    alts = []

    if hints:
        primary = hints[0]
        alts.extend(hints[1:])
        if subj_terms:
            alts.append(" ".join(subj_terms[:4]))
    elif subj_terms:
        primary = " ".join(subj_terms[:4])

    # A shorter query matches more. Every alternate below is a widening, so the
    # fallback chain ends with the single strongest noun rather than with a
    # long phrase that was never going to match anything.
    if subj_terms:
        if len(subj_terms) > 2:
            alts.append(" ".join(subj_terms[:2]))
        alts.append(subj_terms[0])

    pterms = [w for w in words(primary) if w not in STOP]
    if len(pterms) > 2:
        alts.insert(0, " ".join(pterms[:2]))

    line = lines.get(line_of_beat(beat) or "") or {}
    lterms = [w for w in words(line.get("text")) if w not in STOP
              and w not in ABSTRACT and len(w) > 3]
    if lterms:
        alts.append(" ".join(lterms[:2]))

    # De-duplicate, preserve order, drop anything equal to the primary.
    seen, out = {primary.lower()}, []
    for a in alts:
        a = " ".join(w for w in words(a) if w not in STOP)[:60].strip()
        if a and a.lower() not in seen:
            seen.add(a.lower())
            out.append(a)

    return primary, out[:4]


def searchable(query):
    """Is this query something a camera could have pointed at?

    A query made only of abstractions returns confident, irrelevant results --
    searching `moment` on any stock library returns a man laughing at a laptop.
    That is worse than returning nothing, because nothing is reportable and a
    plausible wrong clip is not.
    """
    terms = [w for w in words(query) if w not in STOP]
    if not terms:
        return False
    return any(w not in ABSTRACT for w in terms)


# ------------------------------------------------------ grade, mood, motion --


def story_text(plan):
    return " ".join(str((l or {}).get("text") or "")
                    for l in plan.get("narration") or []).lower() + " " + \
           " ".join(str((b or {}).get("subject") or "")
                    for b in plan.get("beats") or []).lower()


def choose(table, text, default):
    """Score a word-table against the story and take the winner.

    Scored on *distinct* words matched rather than total hits, so a single word
    repeated forty times cannot carry a grade on its own. That was a real
    failure: a film that said "rain" in every other line graded `verdant`
    because `rain` appears in both tables, and the tie went to the wrong one.
    """
    seen = set(words(text))
    best, best_n = default, 0
    for name, spec in table.items():
        vocab = spec["words"] if isinstance(spec, dict) else spec
        n = len(seen & set(vocab))
        if n > best_n:
            best, best_n = name, n
    return best, best_n


def apply_motion_plan(shots, plan_path):
    """Honour an animation director's motion plan.

    The tier contract is the style contract's, in this style's vocabulary:
    `hold` and `impact` get no *added* camera move — the clip's own motion is
    already there — and the graded tiers scale the move by the shot's amount.

    Two traps, both named in the style contract and both real here:

    - a stale plan naming beats that no longer exist is refused rather than
      applied to the wrong film;
    - damping the quiet beats without spending the saving on the loud ones
      drops the whole film below its motion floor, so `sakuga` is given a
      genuinely bigger move rather than merely "not damped".
    """
    mp = load(plan_path)
    planned = {s.get("beat") or s.get("id"): s for s in mp.get("shots") or []}
    if not planned:
        warn("motion plan has no shots; ignoring it")
        return 0

    ids = {s["beat"] for s in shots}
    missing = [b for b in planned if b not in ids]
    if len(missing) > len(planned) / 2:
        die("motion plan is stale: %d of %d planned shots name beats that do "
            "not exist. Re-run the animation director against this beat plan."
            % (len(missing), len(planned)))

    applied = 0
    for s in shots:
        p = planned.get(s["beat"])
        if not p:
            continue
        tier = str(p.get("tier") or "").lower()
        amount = float(p.get("amount") or 1.0)
        if tier in ("hold", "impact"):
            s["move"] = "hold"
            s["move_amount"] = 0.0
        elif tier in ("limited", "full", "sakuga"):
            s["move_amount"] = round(max(0.0, amount) *
                                     (1.6 if tier == "sakuga" else 1.0), 3)
        if tier == "impact":
            s["impact_at"] = round(float(p.get("at") or 0.0), 3)
        s["tier"] = tier or "limited"
        applied += 1
    return applied


# ----------------------------------------------------------------- compile --


def add_cutaways(shots, notes, limit=MAX_SHOT):
    """Split shots that hold longer than `limit` into several shorter ones.

    A stock clip has a shelf life. Past about five seconds it has shown
    everything it has, and the film goes slack exactly when the narration is
    still going -- which is why ColdFusion cuts on that beat rather than
    letting a picture run.

    The split is honest or it does not happen. Each new piece takes one of the
    beat's *alternate* queries, so it fetches a different clip of the same
    subject: a second angle, not the same footage shown twice. A beat with no
    alternates cannot be cut away from without either repeating a clip or
    inventing a subject the story never mentioned, so it is reported and left
    alone. That is the same rule the rest of this style follows -- say what you
    cannot shoot instead of shooting the nearest thing.
    """
    out = []
    for shot in shots:
        dur = float(shot.get("dur") or 0.0)
        alts = [a for a in (shot.get("alternates") or []) if searchable(a)]
        if dur <= limit or shot.get("placeholder") or not shot.get("query"):
            out.append(shot)
            continue

        want = int(math.ceil(dur / limit))
        pieces = min(want, 1 + len(alts))
        if pieces < 2:
            notes.append({
                "level": "warn", "beat": shot.get("beat"),
                "note": "holds %.1fs, over the %.1fs ceiling, and has no "
                        "alternate query to cut away to. Give beat %r another "
                        "assets[].hint and it will be cut in two."
                        % (dur, limit, shot.get("beat")),
            })
            out.append(shot)
            continue

        span = dur / pieces
        queries = [shot["query"]] + alts[:pieces - 1]
        for k, q in enumerate(queries):
            piece = dict(shot)
            piece["at"] = round(shot["at"] + k * span, 3)
            piece["dur"] = round(span, 3)
            piece["query"] = q
            # The remaining alternates stay available to the fetcher as
            # fallbacks, but a piece must never offer its own siblings --
            # that is how the same clip ends up on screen twice.
            piece["alternates"] = [a for a in alts if a not in queries]
            if k:
                # A chip belongs to the beat, not to every piece of it.
                piece.pop("keyword", None)
                # Alternating the move stops four pushes in a row reading as
                # one long push with cuts in it.
                piece["move"] = "hold" if shot.get("move") != "hold" else "push-in"
            out.append(piece)

        notes.append({
            "level": "info", "beat": shot.get("beat"),
            "note": "held %.1fs, so it was cut into %d shots of %.1fs on "
                    "alternate angles" % (dur, pieces, span),
        })

    for i, shot in enumerate(out):
        shot["id"] = "s%02d" % (i + 1)
    return out


#: What to shoot when the beat is about an idea rather than a thing.
#:
#: This is the problem every stock film hits: "investors grew nervous" has no
#: photograph. ColdFusion's answer, which is visible in any of its films, is
#: not a text card and not a diagram -- it is atmosphere. The picture stops
#: illustrating the sentence and starts matching its *energy*, and the film
#: keeps moving.
#:
#: Every query here is deliberately non-specific: weather, light, traffic,
#: defocused city. That is what keeps it honest. Cutting to a *particular*
#: building or a particular crowd under an abstract line would be claiming
#: something the story never said -- the failure the style contract calls
#: "a stock crowd standing in for a real one". Bokeh claims nothing. A viewer
#: reads it as mood, because it is mood, and the storyboard says so.
ATMOSPHERE = {
    "tension":    ("city traffic at night timelapse", "rain on glass neon",
                   "crowd walking motion blur"),
    "dread":      ("dark storm clouds timelapse", "rain on empty street at night",
                   "long empty corridor"),
    "triumph":    ("sunrise over city skyline", "aerial city at golden hour",
                   "sunlight through clouds"),
    "elegy":      ("defocused city lights bokeh", "empty room with window light",
                   "slow waves at dusk"),
    "curious":    ("abstract light patterns", "fibre optic lights close up",
                   "macro circuit board"),
    "reflective": ("defocused bokeh lights", "clouds moving timelapse",
                   "quiet street in the morning"),
}


def atmosphere_for(mood, n):
    """A non-specific query for a beat that has no photographable subject."""
    pool = ATMOSPHERE.get(mood) or ATMOSPHERE[DEFAULT_MOOD]
    return pool[n % len(pool)]


def build(plan, aspect, grade_override, mood_override, cutaways=True):
    if int(plan.get("schema") or 0) != SCHEMA:
        die("beat plan schema %r; this compiler reads %d"
            % (plan.get("schema"), SCHEMA))

    beats = list(plan.get("beats") or [])
    if not beats:
        die("beat plan has no beats")

    lines = line_index(plan)
    starts, ends, spoken_end = line_starts(plan)
    tail = float((plan.get("timing") or {}).get("tail") or 0.0)
    film_end = round(spoken_end + tail, 3)

    frame = FRAME.get(aspect) or die("unknown aspect %r" % aspect)

    text = story_text(plan)
    grade, gn = (grade_override, 99) if grade_override else \
        choose(GRADES, text, DEFAULT_GRADE)
    mood, mn = (mood_override, 99) if mood_override else \
        choose(MOODS, text, DEFAULT_MOOD)
    if not grade_override and gn == 0:
        warn("no grade word matched the story; falling back to %r. A film that "
             "grades by default looks like every other film this style makes."
             % DEFAULT_GRADE)
    if not mood_override and mn == 0:
        warn("no mood word matched the story; falling back to %r" % DEFAULT_MOOD)

    # ---- shots, in time order, each running until the next one takes over.
    rows = []
    for b in beats:
        t = resolve_at(b.get("at"), starts, ends)
        intent = str(b.get("intent") or "establish")
        if intent not in INTENTS:
            die("beat %r has intent %r, which is outside the closed vocabulary"
                % (b.get("id"), intent))
        rows.append((t, b, intent))
    rows.sort(key=lambda r: r[0])

    notes = []
    shots = []
    for i, (t, b, intent) in enumerate(rows):
        end = rows[i + 1][0] if i + 1 < len(rows) else film_end
        dur = round(max(0.0, end - t), 3)

        primary, alts = query_from(b, lines)
        assets = b.get("assets")
        explicit_empty = isinstance(assets, list) and not assets

        shot = {
            "id": "s%02d" % (i + 1),
            "beat": b.get("id"),
            "at": t,
            "dur": dur,
            "intent": intent,
            "subject": b.get("subject") or "",
            "emphasis": float(b.get("emphasis") or 0.5),
            "query": primary,
            "alternates": alts,
            "move": MOVE.get(intent, "hold"),
            "move_amount": 1.0,
            "speed": SPEED.get(intent, 1.0),
            "grade": grade,
            "clip": None,
        }

        # A keyword chip. The beat plan guarantees the word is spoken in its
        # own line, so putting it on screen is reinforcement rather than a
        # caption. Only the strongest beats get one -- a word on every shot is
        # a slideshow with subtitles.
        kws = [str(k).strip() for k in (b.get("keywords") or []) if str(k).strip()]
        if kws and shot["emphasis"] >= 0.6:
            shot["keyword"] = kws[0].upper()

        if explicit_empty:
            # "Hold what is already on screen" -- the beat plan's documented way
            # of saying a new picture would be a repeat. Extend the previous
            # shot rather than cutting to something unrelated.
            if shots:
                notes.append({"level": "info", "beat": b.get("id"),
                              "note": "empty assets: held the previous shot for "
                                      "%.1fs more instead of cutting" % dur})
                continue
            notes.append({"level": "blocking", "beat": b.get("id"),
                          "note": "the first beat has empty assets, so the film "
                                  "opens on nothing. Give beat %r a subject."
                                  % b.get("id")})

        if not explicit_empty and not searchable(primary):
            # No photograph exists of an idea. Rather than stopping the film
            # with a placeholder, cut to atmosphere that matches the mood --
            # the move every stock documentary makes here. It is recorded as a
            # note and flagged on the shot, because a human should be able to
            # see at a glance which pictures are evidence and which are mood.
            shot["query"] = atmosphere_for(mood, len(shots))
            shot["alternates"] = [a for a in
                                  (ATMOSPHERE.get(mood) or ATMOSPHERE[DEFAULT_MOOD])
                                  if a != shot["query"]]
            shot["atmosphere"] = True
            shot["move"] = "hold"
            notes.append({
                "level": "warn", "beat": b.get("id"), "query": primary,
                "note": "nothing here is photographable: %r reduces to "
                        "abstractions, so this beat runs on atmosphere (%r) "
                        "rather than evidence. If it should show something "
                        "specific, give it an assets[].hint."
                        % (primary or b.get("subject") or "", shot["query"]),
            })

        if dur < MIN_SHOT:
            notes.append({"level": "warn", "beat": b.get("id"),
                          "note": "shot is %.2fs; under %.1fs reads as a flash, "
                                  "not a picture" % (dur, MIN_SHOT)})

        shots.append(shot)

    if not shots:
        die("every beat compiled away; there is no film here")

    # ---- the film must be covered end to end. A stock cut with a gap is a
    # black frame, which reads as a broken file rather than as a pause. Every
    # duration is therefore *derived* from the next shot's start rather than
    # trusted from the beat -- which is also what makes a held beat work, since
    # it left no shot behind and its neighbour simply reaches further.
    shots[0]["at"] = 0.0
    for i in range(len(shots) - 1):
        shots[i]["dur"] = round(shots[i + 1]["at"] - shots[i]["at"], 3)
    shots[-1]["dur"] = round(max(MIN_SHOT, film_end - shots[-1]["at"]), 3)

    # ---- cut away from anything that outstays the footage. This runs after
    # the durations are final, because until now a shot's length was still
    # being decided by where its neighbour starts.
    if cutaways:
        shots = add_cutaways(shots, notes)
    else:
        # The over-length report belongs here rather than in the loop above,
        # where a shot's duration is not settled yet, and it is the cutaway
        # pass's job whenever that pass is running.
        for shot in shots:
            if float(shot.get("dur") or 0) > MAX_SHOT:
                notes.append({"level": "warn", "beat": shot.get("beat"),
                              "note": "holds %.1fs; over %.1fs a stock clip has "
                                      "run out of things to show"
                                      % (shot["dur"], MAX_SHOT)})

    # ---- adjacent shots must not ask the same question, or fetch hands back
    # the same clip twice and the cut looks like a dropped frame.
    for i in range(1, len(shots)):
        if shots[i]["query"] and shots[i]["query"] == shots[i - 1]["query"]:
            notes.append({"level": "warn", "beat": shots[i]["beat"],
                          "note": "same query as the shot before it (%r); the "
                                  "cut will look like a dropped frame"
                                  % shots[i]["query"]})

    sb = {
        "schema": SCHEMA,
        "style": "stock",
        "title": plan.get("title") or "Untitled",
        "seed": plan.get("seed"),
        "aspect": aspect,
        "width": frame["width"],
        "height": frame["height"],
        "fps": 30,
        "duration": round(max(film_end, shots[-1]["at"] + shots[-1]["dur"]), 3),
        "grade": grade,
        "grade_filter": GRADES[grade]["filter"],
        "grade_target": GRADES[grade].get("target", 0.47),
        "music": {"mood": mood},
        "narration": [
            {"id": l.get("id"), "text": l.get("text"),
             "at": starts.get(l.get("id")), "audio": l.get("audio"),
             "duration": l.get("duration")}
            for l in plan.get("narration") or []
        ],
        "acts": plan.get("acts") or [],
        "shots": shots,
        "credits": [],
        "notes": notes,
    }
    if plan.get("mix"):
        sb["mix"] = plan["mix"]

    throttle_keywords(shots)
    return sb


#: A keyword chip is punctuation, not a caption. Two rules keep it that way.
KEYWORD_MIN_GAP = 9.0   #: seconds of screen time between chips
KEYWORD_MAX_SHARE = 0.3  #: never label more than this fraction of the film


def throttle_keywords(shots):
    """Thin the keyword chips down to the ones that punctuate.

    Emphasis alone is too generous a filter: on the validation film 31 of 44
    shots cleared it, so a red chip was on screen for most of the running time
    and the same words came round again and again -- VAULT three times, POLICE
    three times, RAIN twice. At that density the chip stops reading as emphasis
    and starts reading as a debug label.

    Two rules fix it. A word is never shown twice, because the second showing
    carries no information. And chips are spaced, because two in quick
    succession compete rather than accumulate. Where the spacing rule has to
    choose, the higher-emphasis beat wins.
    """
    cand = [s for s in shots if s.get("keyword")]
    for s in cand:
        s.pop("keyword_dropped", None)

    seen, kept = set(), []
    # Strongest first, so a weak beat cannot take the slot a strong one needs.
    for s in sorted(cand, key=lambda s: (-float(s.get("emphasis") or 0), s["at"])):
        w = s["keyword"]
        if w in seen:
            continue
        if any(abs(float(s["at"]) - float(k["at"])) < KEYWORD_MIN_GAP for k in kept):
            continue
        seen.add(w)
        kept.append(s)

    cap = max(1, int(len(shots) * KEYWORD_MAX_SHARE))
    if len(kept) > cap:
        kept.sort(key=lambda s: -float(s.get("emphasis") or 0))
        kept = kept[:cap]

    keep_ids = {s["id"] for s in kept}
    for s in cand:
        if s["id"] not in keep_ids:
            del s["keyword"]
    return len(keep_ids)


def main():
    ap = argparse.ArgumentParser(
        description="Compile a beat plan into a stock-footage storyboard.")
    ap.add_argument("beat_plan")
    ap.add_argument("-o", "--out", help="where to write the storyboard")
    ap.add_argument("--check", action="store_true",
                    help="validate and report; write nothing")
    ap.add_argument("--aspect", default="16:9", choices=sorted(FRAME))
    ap.add_argument("--motion-plan", help="an animation director's motion plan")
    ap.add_argument("--grade", choices=sorted(GRADES),
                    help="force a grade instead of choosing one from the story")
    ap.add_argument("--mood", choices=sorted(MOODS),
                    help="force a music mood")
    ap.add_argument("--no-cutaways", action="store_true",
                    help="leave shots longer than %.0fs whole instead of "
                         "cutting away to an alternate angle" % MAX_SHOT)
    a = ap.parse_args()

    sb = build(load(a.beat_plan), a.aspect, a.grade, a.mood,
               cutaways=not a.no_cutaways)

    if a.motion_plan:
        n = apply_motion_plan(sb["shots"], a.motion_plan)
        print("stock/compile: motion plan applied to %d shots" % n,
              file=sys.stderr)

    blocking = [n for n in sb["notes"] if n["level"] == "blocking"]
    warns = [n for n in sb["notes"] if n["level"] == "warn"]

    for n in sb["notes"]:
        if n["level"] != "info":
            print("stock/compile: %s: %s: %s"
                  % (n["level"], n.get("beat"), n["note"]), file=sys.stderr)

    print("stock/compile: %d shots, %.1fs, grade %r, mood %r  (%d blocking, "
          "%d warnings)" % (len(sb["shots"]), sb["duration"], sb["grade"],
                            sb["music"]["mood"], len(blocking), len(warns)),
          file=sys.stderr)

    if a.check:
        raise SystemExit(1 if blocking else 0)

    out = a.out or "storyboard.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(sb, fh, indent=1, ensure_ascii=False)
    print("stock/compile: wrote %s" % out, file=sys.stderr)

    # A blocking note is a decision for a human, so it is an exit code and not
    # just a line of output -- a pipeline that ignores it ships a film with a
    # labelled placeholder in it.
    raise SystemExit(1 if blocking else 0)


if __name__ == "__main__":
    main()
