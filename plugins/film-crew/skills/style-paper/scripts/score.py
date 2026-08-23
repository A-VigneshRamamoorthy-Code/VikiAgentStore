"""Story -> score. What the film should sound like, decided by what it says.

The compiler used to hand every film the same music block --
`tension / minor / 43.65 Hz / 60 bpm` -- and the same three sound effects, all
of which were *paper foley*: a stamp, a rustle, a pen stroke. So a children's
story about a kite and a manhunt through a winter city were scored
identically, and the only things you ever heard were the sounds of the collage
being assembled. The medium was audible and the story was not.

This module decides the score the way a composer would: read the thing, work
out what it *feels* like, then choose mode, tempo, register and instrument to
match. Two axes do most of the work, following the circumplex model of affect
(Russell 1980), which is the standard two-dimensional description of emotion:

    valence   how positive or negative      -> chooses the mode
    arousal   how activated or still        -> chooses the tempo

That split is not arbitrary. It is the most consistently replicated result in
the music-and-emotion literature: mode is the dominant cue for valence and
tempo the dominant cue for arousal (Gabrielsson & Lindström's review of
musical structure and emotional expression; Juslin & Laukka's meta-analysis of
performance cues). Where those two leave the picture incomplete -- a graveyard
and a hospital are both low-arousal and negative but should not sound alike --
a third pass reads the story's *subject* and colours the instrumentation.

Everything here is deliberately legible and adjustable. A beat plan can
override any field, and an explicit `music` block in the plan still wins
outright; this only decides what happens when nobody said.
"""

import re

# --------------------------------------------------------------- lexicons ----

# Valence: negative words score down, positive up. These are weighted rather
# than binary because "died" should not count the same as "grey".
NEGATIVE = {
    3: ("died", "death", "dead", "killed", "murder", "murdered", "corpse",
        "grave", "buried", "funeral", "mourning", "widow", "orphan",
        "massacre", "atrocity", "famine", "plague", "drowned"),
    2: ("blood", "wound", "scream", "screamed", "terror", "horror", "dread",
        "afraid", "fear", "feared", "panic", "cruel", "betrayed", "betrayal",
        "ruin", "ruined", "wreck", "burned", "burning", "collapse", "lost",
        "grief", "weep", "wept", "sorrow", "despair", "abandoned", "gone",
        "never", "alone", "cold", "frozen", "starving", "broken", "vanished"),
    1: ("dark", "darkness", "shadow", "grey", "gray", "empty", "silence",
        "silent", "bitter", "hard", "harsh", "tired", "worn", "rust",
        "dust", "ash", "storm", "rain", "wind", "winter", "snow", "night",
        "warning", "danger", "risk", "wrong", "failed", "stopped", "nobody"),
}

POSITIVE = {
    3: ("joy", "joyful", "triumph", "triumphant", "rejoiced", "victory",
        "beloved", "wonder", "miracle", "saved", "rescued", "healed", "free",
        "freedom", "reunion", "homecoming"),
    2: ("laugh", "laughed", "laughter", "smile", "smiled", "happy", "glad",
        "delight", "hope", "hopeful", "warm", "warmth", "bright", "brilliant",
        "beautiful", "gentle", "kind", "love", "loved", "song", "sang",
        "dance", "danced", "gift", "welcome", "safe", "spring", "bloom"),
    1: ("light", "lit", "sun", "sunlight", "morning", "green", "garden",
        "child", "children", "friend", "home", "quiet", "calm", "still",
        "gold", "golden", "clear", "open", "new", "young", "sweet",
        "summer", "meadow", "orchard", "blossom", "harvest", "afternoon",
        "played", "playing", "holiday", "festival", "feast", "together",
        "forever", "grew", "grown"),
}

# Arousal: how much is *happening*. High-arousal words are mostly verbs of
# sudden or forceful motion; low-arousal words are verbs and adjectives of
# stillness. Tempo follows this axis.
HIGH_AROUSAL = {
    3: ("exploded", "explosion", "crash", "crashed", "gunfire", "gunshot",
        "screamed", "shouted", "chase", "chased", "pursuit", "attack",
        "attacked", "charge", "charged", "battle", "war", "riot", "stampede"),
    2: ("ran", "running", "run", "fled", "flee", "rushed", "raced", "hurried",
        "leapt", "jumped", "struck", "seized", "grabbed", "slammed", "burst",
        "shattered", "tore", "fought", "shook", "sudden", "suddenly",
        "urgent", "quick", "fast", "hunt", "hunted", "escape", "alarm"),
    1: ("climbed", "climbing", "walked", "walking", "carried", "pushed",
        "pulled", "opened", "turned", "rose", "moved", "worked", "built",
        "storm", "wind", "fire", "crowd", "market", "engine", "machine"),
}

LOW_AROUSAL = {
    2: ("still", "stillness", "motionless", "sleeping", "asleep", "slept",
        "frozen", "silence", "silent", "hush", "waited", "waiting", "patient",
        "slowly", "slow", "drifted", "lingered", "rested", "quiet"),
    1: ("sat", "stood", "lay", "watched", "listened", "remembered",
        "thought", "knew", "held", "kept", "stayed", "always", "years",
        "evening", "dusk", "night", "snow", "mist", "fog"),
}

# Subject: what the story is *about*. This is what separates two stories that
# share a valence/arousal coordinate but should not share an orchestration.
SUBJECTS = {
    "supernatural": ("ghost", "ghosts", "haunted", "spirit", "spirits",
                     "cursed", "curse", "omen", "vanished", "impossible",
                     "nobody was there", "no one was there", "footsteps",
                     "whisper", "whispered", "shadow", "unseen", "witch"),
    "crime": ("police", "detective", "evidence", "witness", "suspect",
              "stolen", "theft", "thief", "investigation", "trial", "court",
              "arrest", "arrested", "case", "file", "record", "testimony",
              "verdict", "guilty", "crime", "fraud", "cover-up"),
    "war": ("war", "soldier", "soldiers", "army", "battle", "front", "siege",
            "bomb", "bombed", "rifle", "trench", "enemy", "surrender"),
    "sea": ("sea", "ocean", "wave", "waves", "tide", "harbour", "harbor",
            "ship", "boat", "sail", "sailed", "shore", "coast", "island",
            "lighthouse", "fisherman", "drowned", "port"),
    # Air *travel* only. Sky, cloud and star belong to `celestial`: a story
    # about measuring a star is not a story about a journey, and putting them
    # here scored an astronomy film as a sea voyage.
    "air": ("flight", "flew", "plane", "aircraft", "airborne", "wing",
            "wings", "kite", "balloon", "runway", "pilot", "took off"),
    "celestial": ("star", "stars", "sky", "moon", "sun", "cloud", "clouds",
                  "planet", "orbit", "eclipse", "comet", "constellation",
                  "telescope", "heavens", "dawn", "dusk"),
    "mountain": ("mountain", "hill", "peak", "summit", "cliff", "ridge",
                 "slope", "stairs", "steps", "climb", "climbed", "ascent"),
    "winter": ("snow", "snowed", "ice", "frozen", "frost", "winter", "cold",
               "blizzard", "sleet", "glacier"),
    "child": ("child", "children", "boy", "girl", "kid", "toy", "toys",
              "school", "playground", "lullaby", "bedtime", "grandmother",
              "grandfather", "story", "once upon"),
    "sacred": ("church", "temple", "prayer", "prayed", "bell", "bells",
               "hymn", "altar", "priest", "monk", "shrine", "candle",
               "pilgrim", "pilgrimage", "vigil", "faith"),
    "machine": ("engine", "factory", "machine", "motor", "train", "railway",
                "gear", "gears", "piston", "steam", "workshop", "furnace"),
    "city": ("city", "street", "streets", "crowd", "market", "traffic",
             "station", "café", "cafe", "apartment", "office", "tram"),
    "science": ("experiment", "experiments", "laboratory", "lab", "microscope",
                "telescope", "specimen", "specimens", "sample", "samples",
                "measured", "measurement", "discovered", "discovery",
                "theory", "hypothesis", "evidence", "data", "study",
                "research", "bacteria", "molecule", "chemical", "formula",
                "invented", "invention", "engineer", "engineered", "proved"),
    "domestic": ("kitchen", "table", "bread", "supper", "hearth", "door",
                 "window", "letter", "letters", "chair", "lamp", "house"),
}

# ------------------------------------------------------------------ moods ----

# Each mood names a scale, a tempo and an instrumentation the renderer knows
# how to build. The names are the ones this plugin already documents in
# `sound-designer/reference/scoring.md` -- `tension`, `elegy`, `curious`,
# `drive`, `reflective` -- plus `music_box`, `memorial`, `crime` and `warm`
# from the renderer, and four genuinely new ones. Aligning with the documented
# vocabulary matters more than inventing a tidier one: an author who has read
# the scoring guide should be able to name any mood in it and hear it.
#
# Mode choices follow their conventional affect, which is well attested:
#   major        bright, resolved
#   lydian       raised 4th -- wonder, "the impossible is possible"
#   mixolydian   flat 7th   -- rustic, open-road, nostalgic-but-warm
#   dorian       raised 6th on a minor -- searching rather than grieving
#   aeolian      natural minor -- plain melancholy, memory
#   phrygian     flat 2nd   -- menace; the semitone above the tonic is the
#                              closest and roughest diatonic interval there is
#
# Every tempo here sits at or below 92 bpm. That is not timidity, it is the
# one hard rule the scoring guide states: *"Narration is already carrying the
# pace. A bed at 90 bpm under a 145 wpm read fights it; at 60 bpm it supports
# it."* The 130-150 bpm band that trailer music lives in is deliberately
# absent -- it belongs to films with no one talking over them.
MOODS = {
    # --- bright ---------------------------------------------------------
    "music_box": dict(scale="major",      bpm=68, root=65.41, melody_root=84,
                      colour="innocence, small wonders, childhood"),
    "warm":      dict(scale="major",      bpm=66, root=65.41, melody_root=76,
                      colour="intimacy, kitchens and letters, safety"),
    "wonder":    dict(scale="lydian",     bpm=72, root=61.74, melody_root=81,
                      colour="awe, discovery, the sublime"),
    # --- open -----------------------------------------------------------
    "pastoral":  dict(scale="mixolydian", bpm=78, root=73.42, melody_root=76,
                      colour="outdoors, rustic, unhurried"),
    "curious":   dict(scale="dorian",     bpm=78, root=73.42, melody_root=74,
                      colour="discovery, how a thing works, searching"),
    "voyage":    dict(scale="dorian",     bpm=72, root=55.00, melody_root=72,
                      colour="distance crossed, sea and air"),
    # --- driven ---------------------------------------------------------
    "drive":     dict(scale="minor",      bpm=88, root=49.00, melody_root=71,
                      colour="momentum, a thing gathering speed"),
    "crime":     dict(scale="minor",      bpm=92, root=36.71, melody_root=67,
                      colour="procedural tension, evidence, pursuit"),
    "tension":   dict(scale="minor",      bpm=62, root=43.65, melody_root=67,
                      colour="unsolved, withheld, something not yet known"),
    # --- grave ----------------------------------------------------------
    "reflective": dict(scale="aeolian",   bpm=58, root=49.00, melody_root=69,
                       colour="archival distance, memory, long ago"),
    "elegy":     dict(scale="aeolian",    bpm=54, root=49.00, melody_root=69,
                      colour="quiet sorrow, looking back at a loss"),
    "memorial":  dict(scale="minor",      bpm=47, root=43.65, melody_root=67,
                      colour="grief, ceremony, the weight of the dead"),
    "dread":     dict(scale="phrygian",   bpm=56, root=41.20, melody_root=65,
                      colour="menace, the supernatural, something wrong"),
}

#: Subjects that argue strongly for a particular mood regardless of affect.
SUBJECT_MOOD = {
    "supernatural": ("dread", 3),
    "crime":        ("crime", 3),
    "war":          ("memorial", 2),
    "sea":          ("voyage", 2),
    "air":          ("voyage", 2),
    "celestial":    ("wonder", 2),
    "child":        ("music_box", 2),
    "sacred":       ("memorial", 2),
    "machine":      ("drive", 1),
    "mountain":     ("pastoral", 1),
    "city":         ("curious", 1),
    "science":      ("curious", 3),
    "domestic":     ("warm", 2),
    "winter":       ("elegy", 1),
}

#: Subjects that describe *where* a story happens rather than *what happens*.
#: They are still the best signal available for the ambience bed and the
#: palette -- a story set at sea should sound and look like the sea whatever
#: it is about -- but they must not decide the mood, because "at sea" is true
#: of both a holiday and a shipwreck.
SETTING_SUBJECTS = frozenset({
    "sea", "air", "mountain", "city", "winter", "domestic", "celestial",
    "machine",
})


def _hits(text, table):
    """Total weight of `table`'s terms occurring in `text`."""
    total = 0
    for weight, words in table.items():
        for w in words:
            if " " in w:
                if w in text:
                    total += weight
            elif re.search(r"\b%s\b" % re.escape(w), text):
                total += weight
    return total


def analyse(text):
    """Read a story and return its affect coordinates and subjects.

    `valence` and `arousal` are normalised to roughly -1..+1 by the story's
    own length, so a long film is not automatically read as more emotional
    than a short one -- only as more emotional *per word*.
    """
    t = (text or "").lower()
    words = max(40, len(t.split()))
    scale = words / 100.0

    neg, pos = _hits(t, NEGATIVE), _hits(t, POSITIVE)
    hi, lo = _hits(t, HIGH_AROUSAL), _hits(t, LOW_AROUSAL)

    valence = (pos - neg) / (scale * 6.0)
    arousal = (hi - lo) / (scale * 5.0)

    subjects = {}
    for name, words_ in SUBJECTS.items():
        n = sum(1 for w in words_
                if (w in t if " " in w
                    else re.search(r"\b%s\b" % re.escape(w), t)))
        if n:
            subjects[name] = n

    return {
        "valence": max(-1.5, min(1.5, valence)),
        "arousal": max(-1.5, min(1.5, arousal)),
        "subjects": subjects,
        "counts": {"neg": neg, "pos": pos, "high": hi, "low": lo},
    }


def choose_mood(text, palette_hint=None):
    """Pick the mood, and say why.

    Returns `(mood, scores, reason)`. The reason is kept because a composer
    who cannot say why is not making a choice, and because the compiler prints
    it -- an author who disagrees needs to see what the film thought it was.
    """
    a = analyse(text)
    t_low = (text or "").lower()
    v, ar = a["valence"], a["arousal"]
    subs = a["subjects"]

    scores = {m: 0.0 for m in MOODS}

    # Valence -> mode family. Distance from the mood's own implied valence.
    IMPLIED_V = {"music_box": 0.8, "warm": 0.7, "wonder": 0.6, "pastoral": 0.5,
                 "curious": 0.2, "voyage": 0.1, "drive": -0.1, "crime": -0.5,
                 "tension": -0.3, "reflective": -0.4, "elegy": -0.7,
                 "memorial": -0.9, "dread": -0.9}
    IMPLIED_A = {"music_box": -0.2, "warm": -0.4, "wonder": -0.1,
                 "pastoral": 0.1, "curious": 0.3, "voyage": 0.1,
                 "drive": 0.8, "crime": 0.4, "tension": 0.0,
                 "reflective": -0.5, "elegy": -0.7, "memorial": -0.6,
                 "dread": -0.2}

    for m in MOODS:
        dv = abs(v - IMPLIED_V[m])
        da = abs(ar - IMPLIED_A[m])
        # Valence weighs more than arousal: getting the mode wrong is a worse
        # error than getting the tempo wrong, because a listener forgives a
        # slow chase and does not forgive a cheerful funeral.
        scores[m] += 3.0 - (dv * 1.4 + da * 0.9)

    for sub, n in subs.items():
        if sub in SUBJECT_MOOD:
            mood, w = SUBJECT_MOOD[sub]
            # A place is not a subject. The sea is *where* a drowning happened,
            # not what the story is about, and a setting that outvotes the
            # story's own affect produces exactly the wrong film: four
            # mentions of the sea scored eleven drowned men as a `voyage`.
            # Settings still choose the ambience bed and the palette, which is
            # the job they are actually good at.
            weight = 0.16 if sub in SETTING_SUBJECTS else 0.5
            scores[mood] += w * min(3, n) * weight

    # A cheerful funeral is a worse mistake than a dull one. When the story
    # has a clear emotional sign, moods of the opposite sign are penalised in
    # proportion to how clear it is, so no amount of scenery can carry a mood
    # across the line.
    if abs(v) > 0.45:
        for m in MOODS:
            if IMPLIED_V[m] * v < 0:
                scores[m] -= min(2.5, abs(v)) * abs(IMPLIED_V[m]) * 1.6

    if palette_hint and palette_hint in scores:
        scores[palette_hint] += 0.8

    # Grief and threat sit at almost the same affect coordinate -- both are
    # very negative and neither is agitated -- so geometry alone cannot
    # separate them, and `dread` was winning stories about burials. The
    # difference is not how bad it is but *when*: dread is anticipatory,
    # something is coming; elegy and memorial are retrospective, it already
    # happened. Completed loss is what the story's own words report.
    mourning = _hits(t_low, {3: NEGATIVE[3]})
    threat = subs.get("supernatural", 0) + subs.get("crime", 0) \
        + _hits(t_low, {2: ("warning", "coming", "waiting", "watching",
                            "hunted", "stalked", "creeping", "whisper",
                            "whispers", "something")})
    if mourning >= 3 and threat == 0 and not subs.get("science"):
        scores["memorial"] += 1.1
        scores["elegy"] += 1.1
        scores["dread"] -= 1.6

    # A genre is a claim about *what kind of story this is*, and affect
    # geometry cannot make it. A mill closing is negative and moderately
    # agitated, which puts it at almost exactly the coordinate of a heist;
    # only the words "vault" and "police" can tell them apart. Genre moods
    # therefore need their own subject cue and are damped without one, which
    # hands the space back to the moods that describe feeling rather than
    # furniture.
    if not (subs.get("crime") or threat):
        scores["crime"] -= 1.4
    if not threat:
        scores["dread"] -= 1.4
    if not subs.get("child"):
        scores["music_box"] -= 0.8

    best = max(scores, key=lambda m: scores[m])
    top = sorted(subs.items(), key=lambda kv: -kv[1])[:3]
    reason = ("valence %+.2f arousal %+.2f%s"
              % (v, ar,
                 (", about " + ", ".join(s for s, _ in top)) if top else ""))
    return best, scores, reason


def music_for(text, palette_hint=None, seed=0, gain=0.85, wpm=None):
    """The storyboard `music` block for this story.

    `wpm` is the narration's measured words-per-minute. If given, it caps the
    tempo: the scoring guide's one hard rule is that the bed must not fight
    the read, and its worked example -- *"a bed at 90 bpm under a 145 wpm read
    fights it; at 60 bpm it supports it"* -- works out at roughly 2.4 words
    per beat. Anything faster and the two pulses argue. This is extrapolated
    from a single documented data point, so it is a ceiling rather than a
    target: it only ever slows a cue down.
    """
    mood, scores, reason = choose_mood(text, palette_hint)
    spec = dict(MOODS[mood])
    colour = spec.pop("colour")
    out = {"mood": mood, "gain": gain, "seed": int(seed) % 9973}
    out.update(spec)

    a = analyse(text)
    # Arousal nudges the tempo within the mood rather than across moods, so a
    # tense elegy is a slightly faster elegy and not suddenly a chase.
    base = out["bpm"]
    bpm = base * (1.0 + 0.12 * a["arousal"])
    capped = False
    if wpm:
        # The narration limits how far *excitement* may push the tempo -- it
        # never drags a cue below the tempo its own mood documents. Applied as
        # a hard clamp instead, a 145 wpm read pinned every mood to 65.9 bpm
        # and a heist sounded exactly like a lullaby, which is the failure
        # this whole module exists to remove. The mood table is fitted; the
        # words-per-beat coefficient is extrapolated from one worked example,
        # so where they disagree the fitted number wins.
        ceiling = max(base, float(wpm) / 2.2)
        if bpm > ceiling:
            bpm, capped = ceiling, True
    out["bpm"] = round(max(40, min(96, bpm)), 1)
    out["_why"] = "%s — %s (%s%s)" % (
        mood, colour, reason,
        (", tempo capped to the %.0f wpm read" % wpm) if capped else "")
    out["_scores"] = {k: round(v, 2) for k, v in
                      sorted(scores.items(), key=lambda kv: -kv[1])[:4]}
    return out


# ------------------------------------------------------------------ cues ----

#: The dramatic shape of a four-act story, as multipliers on the film's base
#: cue. This is the arc every score has and this style's never did: it chose
#: one mood and played it wall to wall, so a discovery and a death were
#: scored identically. The columns are the levers the research ranks highest
#: — tempo first, then register and density; mode is deliberately *not* on
#: the list, because it is a weaker lever than either and it is the one this
#: module already over-used.
#:
#: `peak`/`tail` shape the loudness inside a cue; `silence` is the gap left
#: in front of it. Roughly one part in eight of a film should have no music
#: at all, and it should fall where the picture can carry itself.
ARC = [
    # tempo  register  density  peak  tail  rests  lead-in silence
    {"name": "establish", "tempo": 0.92, "register": -1, "density": 0.75,
     "peak": 0.80, "tail": 0.66, "rests": 0.28, "silence": 2.5,
     "note": "the world, stated plainly and a little below its own tempo"},
    {"name": "develop", "tempo": 1.00, "register": 0, "density": 1.0,
     "peak": 0.95, "tail": 0.78, "rests": 0.18, "silence": 1.2,
     "note": "the story proper, at the mood's own tempo"},
    {"name": "press", "tempo": 1.12, "register": 1, "density": 1.5,
     "peak": 1.15, "tail": 0.90, "rests": 0.08, "silence": 0.8,
     "note": "faster, an octave up and twice as busy — the approach"},
    {"name": "resolve", "tempo": 0.84, "register": -1, "density": 0.6,
     "peak": 0.86, "tail": 0.40, "rests": 0.34, "silence": 3.0,
     "note": "slower, lower, sparser: a cadence rather than a stop"},
]


def cue_sheet(text, acts, wpm=None, palette_hint=None, seed=0, gain=0.85):
    """Spot a film into cues.

    `acts` is a list of ``(start_seconds, end_seconds)``. Returns a `music`
    block carrying a `cues` list — one cue per act, each shifted along the
    arc above, each preceded by a little silence.

    Two things here matter more than the numbers. The first is that the cues
    are *separated*: a gap in front of every cue is what makes the next one
    an event rather than a continuation. The second is that the film's last
    cue resolves — it slows, thins and drops, instead of being cut off by the
    end of the picture, which is what "the music just stops" sounds like.
    """
    base = music_for(text, palette_hint=palette_hint, seed=seed, gain=gain,
                     wpm=wpm)
    a = analyse(text)
    cues = []
    n = max(1, len(acts))
    for idx, (t0, t1) in enumerate(acts):
        shape = ARC[min(idx, len(ARC) - 1)] if n > 1 else ARC[1]
        if n > 1 and idx == n - 1:
            shape = ARC[-1]
        lead = min(float(shape["silence"]), max(0.0, (t1 - t0) * 0.22))
        start = t0 + lead
        dur = max(0.0, t1 - start)
        if dur < 2.0:
            continue
        cue = {
            "at": round(start, 2),
            "dur": round(dur, 2),
            "bpm": round(max(40.0, min(104.0,
                                       base["bpm"] * shape["tempo"])), 1),
            "register": shape["register"],
            "density": shape["density"],
            "peak": shape["peak"],
            "tail": shape["tail"],
            "rests": shape["rests"],
            "seed": (int(seed) + idx * 17) % 9973,
            "_act": idx,
            "_shape": shape["name"],
        }
        # A quiet story does not need a tune. Below the arousal floor the
        # opening cue becomes a drone with sparse punctuation over it, which
        # is what a composer would write and what this synth is actually
        # good at.
        if a["arousal"] < 0.30 and idx == 0:
            cue["drone"] = True
        cues.append(cue)
    out = dict(base)
    out["cues"] = cues
    out["_why"] = base.get("_why", "") + \
        (" — spotted into %d cues" % len(cues) if cues else "")
    return out


# ------------------------------------------------------------------- sfx ----

# Story sounds, in priority order. The first pattern that matches a line wins,
# so the specific ones (a bell, a gunshot) are listed before the ambient ones
# (wind, a city). Each maps to a synthesiser in `audio.SFX`.
#
# These are *diegetic*: sounds the characters could hear. They are what was
# missing -- the old build only ever played the sound of paper being handled,
# which is a sound belonging to the medium, not to the world.
SFX_RULES = [
    (r"\b(?:bell|bells|toll|tolled|chime|chimed|church)\b", "bell"),
    (r"\b(?:thunder|lightning|storm broke)\b", "thunder"),
    (r"\b(?:gunshot|gunfire|shot rang|rifle|pistol)\b", "crack"),
    (r"\b(?:door|gate|hinge|creak|creaked|opened it|pushed it open)\b", "creak"),
    (r"\b(?:footstep|footsteps|steps behind|walked|walking|climbed|"
     r"climbing|ran|running|trudg)\w*\b", "steps"),
    (r"\b(?:lantern|candle|flame|fire|burning|lit it|light it|torch|"
     r"hearth|furnace)\b", "fire"),
    (r"\b(?:wave|waves|surf|tide|sea|ocean|shore|harbour|harbor)\b", "waves"),
    (r"\b(?:rain|raining|downpour|drizzle|rained)\b", "rain"),
    (r"\b(?:snow|blizzard|wind|gale|draught|draft|cold air|gust)\b", "wind"),
    (r"\b(?:bird|birds|gull|gulls|crow|crows|sparrow)\b", "birds"),
    (r"\b(?:engine|motor|train|machine|factory|piston|steam)\b", "engine"),
    (r"\b(?:crowd|market|street|city|traffic|station|voices)\b", "crowd"),
    (r"\b(?:clock|hour|minute|ticking|midnight|noon)\b", "clock"),
    (r"\b(?:heart|heartbeat|pulse|breath|breathing)\b", "heart"),
    (r"\b(?:water|river|stream|well|rain barrel|poured)\b", "water"),
]

#: Ambient beds by subject — a continuous sound the whole act sits inside,
#: rather than a one-shot. Keyed by the subject names `analyse` returns.
SUBJECT_AMBIENCE = {
    "sea": "waves",
    "winter": "wind",
    "mountain": "wind",
    "city": "crowd",
    "machine": "engine",
    "air": "wind",
}


def surface_for(text):
    """What the ground is made of, for footstep synthesis."""
    t = (text or "").lower()
    for pattern, name in (
        (r"\b(?:snow|blizzard|drift|ice|frost|frozen)\b", "snow"),
        (r"\b(?:gravel|scree|shingle|pebble|dirt|track)\b", "gravel"),
        (r"\b(?:floorboard|stair(?:case)?s?|deck|hall|corridor|attic|"
         r"landing|porch)\b", "wood"),
        (r"\b(?:grass|meadow|field|lawn|moss)\b", "grass"),
        (r"\b(?:catwalk|gantry|ladder|girder|hull|deckplate)\b", "metal"),
        (r"\b(?:stone|cobble|pavement|street|steps|flag(?:stone)?s?)\b", "stone"),
    ):
        if re.search(pattern, t):
            return name
    return "stone"


def sfx_for(line):
    """The one story sound this line most wants, or None."""
    t = (line or "").lower()
    for pattern, name in SFX_RULES:
        if re.search(pattern, t):
            return name
    return None


def ambience_for(text):
    """A continuous bed for the film, chosen from its dominant subject."""
    subs = analyse(text)["subjects"]
    best, best_n = None, 0
    for sub, n in subs.items():
        if sub in SUBJECT_AMBIENCE and n > best_n:
            best, best_n = SUBJECT_AMBIENCE[sub], n
    return best


def explain(text, palette_hint=None):
    """Human-readable summary — used by the compiler's notes."""
    m = music_for(text, palette_hint)
    amb = ambience_for(text)
    return "%s  %s %.0fbpm%s" % (
        m["_why"], m["scale"], m["bpm"],
        ("  ambience=" + amb) if amb else "")


def _main(argv=None):
    """Preview what a narration would be scored as, without compiling it."""
    import argparse
    import json as _json
    import sys
    ap = argparse.ArgumentParser(
        description="Show the mood, tempo, ambience and effects a story "
                    "would be given.")
    ap.add_argument("source", nargs="?",
                    help="a text file, a beat-plan.json, or - for stdin")
    ap.add_argument("--explain", action="store_true",
                    help="one human-readable line instead of JSON")
    a = ap.parse_args(argv)

    raw = sys.stdin.read() if (a.source in (None, "-")) \
        else open(a.source, encoding="utf-8").read()
    # A beat plan is the thing most callers have to hand; pull the narration
    # out of it rather than scoring its punctuation and field names.
    text = raw
    if raw.lstrip().startswith("{"):
        try:
            plan = _json.loads(raw)
            text = " ".join(str(ln.get("text") or "")
                            for ln in (plan.get("narration") or [])) or raw
        except ValueError:
            pass

    if a.explain:
        print(explain(text))
        return 0

    music = music_for(text)
    out = {
        "music": {k: v for k, v in music.items() if not k.startswith("_")},
        "why": music.get("_why"),
        "ambience": ambience_for(text),
        "footstep_surface": surface_for(text),
        "subjects": analyse(text)["subjects"],
    }
    print(_json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
