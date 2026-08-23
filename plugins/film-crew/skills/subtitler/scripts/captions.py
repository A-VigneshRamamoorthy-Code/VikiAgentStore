#!/usr/bin/env python3
"""Write the caption file from the storyboard that was actually rendered.

YouTube will happily generate captions for you. Those captions are a speech
recogniser's guess, and it guesses worst at exactly the words that matter: the
proper nouns, the figures and the place names the film was researched to get
right. "D.B. Cooper" becomes "DB cooer", "Northwest Orient" becomes "northwest
oriented". Uploading our own file replaces a guess with the script.

There are two reasons this is not optional. Captions are what a large minority
of viewers actually read, and they are indexed -- an uploaded caption track is
the only full-text signal the platform gets about a film's content.

Timings come from the storyboard rather than from the audio, because the
storyboard is what the renderer used to place the voice: `timing.lead_in`, then
each line's own duration followed by its `gap_after`. Deriving them any other
way would let the captions drift out of sync with the picture.

    python3 captions.py storyboard.json -o captions.srt
    python3 captions.py storyboard.json -o captions.srt --vtt captions.vtt
    python3 captions.py storyboard.json -o captions.srt --check film.mp4
    python3 captions.py storyboard.json -o captions.srt --script lines.json
"""

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys

# Reading-speed and layout limits. These are not house style, they are the
# accessibility figures broadcasters converged on: a third line pushes the
# safe-area on a phone, and a cue under a second is gone before the eye
# reaches it.
#
# 20 cps is the figure Netflix's English timed-text spec uses for adult
# content, and it is the one that survives contact with real narration. The
# stricter 17 that reads well on paper flags roughly half of a professionally
# captioned feature documentary -- measured on one, 48% of its cues, median
# 16.9, p90 20.1 -- which makes the check noise rather than signal. The cue
# floor needs no such allowance: the same reference holds every cue to at
# least 1.10s.
MAX_CPS = 20.0
MAX_LINE = 42
MAX_LINES = 2
MIN_CUE = 1.0


def die(msg, code=2):
    print("captions: %s" % msg, file=sys.stderr)
    raise SystemExit(code)


def probe_duration(path):
    ff = shutil.which("ffprobe")
    if not ff:
        die("ffprobe is not installed, and this storyboard times its lines by "
            "audio file. `brew install ffmpeg`")
    r = subprocess.run([ff, "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", path],
                       capture_output=True, text=True)
    try:
        return float((r.stdout or "").strip())
    except ValueError:
        die("could not read the duration of %s" % path)


def stamp(t, sep=","):
    """SRT and WebVTT differ only in the decimal separator.

    Rounded to whole milliseconds *first*, then decomposed. Rounding the
    fractional part on its own lets 0.9996 s become "00,1000" -- a four-digit
    millisecond field that strict parsers reject outright.
    """
    if t < 0 or t != t:
        t = 0.0
    ms = int(round(float(t) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    sec, ms = divmod(ms, 1000)
    return "%02d:%02d:%02d%s%03d" % (h, m, sec, sep, ms)


def wrap(text):
    """Break a line for reading, at a clause if one is available.

    A caption broken mid-phrase is measurably slower to read than the same
    words broken at a comma, so the split point is chosen by punctuation first
    and by width only as a fallback.
    """
    text = " ".join(text.split())
    if len(text) <= MAX_LINE:
        return [text]

    mid = len(text) / 2.0
    best, best_cost = None, None
    for m in re.finditer(r"[,;:\u2014-]\s+|\s+(?=(?:and|but|because|which|"
                         r"who|that|then|when|while|after|before)\b)", text):
        cut = m.end()
        left, right = text[:cut].strip(), text[cut:].strip()
        if not left or not right:
            continue
        if len(left) > MAX_LINE or len(right) > MAX_LINE:
            continue
        cost = abs(cut - mid)
        if best_cost is None or cost < best_cost:
            best, best_cost = (left, right), cost
    if best:
        return list(best)

    # No usable clause break: fall back to the space nearest the middle that
    # keeps both halves legal.
    spaces = [m.start() for m in re.finditer(r"\s+", text)]
    legal = [i for i in spaces
             if len(text[:i].strip()) <= MAX_LINE
             and len(text[i:].strip()) <= MAX_LINE]
    if legal:
        i = min(legal, key=lambda i: abs(i - mid))
        return [text[:i].strip(), text[i:].strip()]
    # Genuinely unbreakable (one very long token): emit it and let the check
    # report it rather than silently truncating a word.
    i = min(spaces, key=lambda i: abs(i - mid)) if spaces else MAX_LINE
    return [text[:i].strip(), text[i:].strip()]


def wraps_clean(piece):
    """True when `piece` fits in the allowed lines without over-running one."""
    lines = wrap(piece)
    return len(lines) <= MAX_LINES and all(len(ln) <= MAX_LINE for ln in lines)


def force_split(piece):
    """Split a piece that cannot be wrapped, at the best space available.

    Preferring a space that leaves both halves wrappable keeps the recursion
    finite and avoids trading one over-long line for two.
    """
    spaces = [m.start() for m in re.finditer(r"\s+", piece)]
    if not spaces:
        return [piece]
    mid = len(piece) / 2.0
    good = [i for i in spaces
            if wraps_clean(piece[:i].strip()) and wraps_clean(piece[i:].strip())]
    i = min(good or spaces, key=lambda i: abs(i - mid))
    return [piece[:i].strip(), piece[i:].strip()]


def chunk(text, limit):
    """Split narration into pieces that each fit inside one caption.

    Pieces are aimed at an even length rather than packed greedily, so a long
    sentence does not come out as one full caption followed by a two-word
    orphan. A clause ending past the target is preferred to a width break.

    A piece must be *wrappable*, not merely shorter than `limit`. The limit is
    `MAX_LINE * MAX_LINES`, which only splits into two legal lines when a space
    happens to fall near the middle; when none does, an 84-character piece
    wraps to a 44-character line and fails the very check this function feeds.
    Pieces that cannot be wrapped are therefore split again.
    """
    text = " ".join(text.split())
    if len(text) <= limit and wraps_clean(text):
        return [text]
    n = int(math.ceil(len(text) / float(limit)))
    target = len(text) / float(n)
    out, cur = [], ""
    if n < 2:
        n, target = 2, len(text) / 2.0
    for word in text.split(" "):
        cand = (cur + " " + word).strip()
        if cur and len(cand) > limit:
            out.append(cur)
            cur = word
            continue
        cur = cand
        if len(cur) >= target and cur[-1] in ",;:.!?\u2014":
            out.append(cur)
            cur = ""
    if cur:
        out.append(cur)

    final, queue = [], list(out)
    while queue:
        piece = queue.pop(0)
        if wraps_clean(piece):
            final.append(piece)
            continue
        halves = force_split(piece)
        if len(halves) < 2 or any(not h for h in halves):
            final.append(piece)   # one unbreakable token; the check reports it
            continue
        queue[:0] = halves
    return final


def load_timeline(path):
    """Read a renderer-published timeline into {id: (start, end)}."""
    with open(path) as fh:
        doc = json.load(fh)
    items = doc.get("lines")
    if not isinstance(items, list):
        die("%s carries no `lines`, so it supplies no timings." % path)
    spans = {}
    for it in items:
        if not isinstance(it, dict) or "id" not in it:
            continue
        try:
            start, end = float(it["start"]), float(it["end"])
        except (KeyError, TypeError, ValueError):
            die("%s: line %r needs numeric `start` and `end`."
                % (path, it.get("id")))
        if end < start:
            die("%s: line %r ends (%.3f) before it starts (%.3f)."
                % (path, it["id"], end, start))
        spans[it["id"]] = (start, end)
    if not spans:
        die("%s lists no usable lines." % path)
    return spans, doc


def find_timeline(sb_path, film):
    """Locate a published timeline for this cut, if one was written.

    Looks beside the film first -- that is the cut being captioned -- then
    beside the storyboard, which is where a board rendered in place puts it.
    """
    seen = []
    for stem in (film, sb_path):
        if not stem:
            continue
        cand = os.path.splitext(stem)[0] + ".timeline.json"
        if cand not in seen:
            seen.append(cand)
    for cand in seen:
        if os.path.exists(cand):
            return cand
    return None


def share_time(dur, weights):
    """Divide a line's time among its cues without stranding one of them.

    A proportional split gives every cue the same reading speed, which is both
    the fairest division and the one `check` is written against -- so it is the
    starting point, not the fallback. Flooring every cue first and sharing only
    the remainder by weight looks fairer but is not: the floor is paid for
    entirely by the long piece, so a line comfortably inside the reading limit
    as a whole could be split into a fast first cue and a leisurely second one.
    That manufactured 11 of the 21 over-speed cues in a 13-minute film whose
    lines were all within the limit to begin with.

    The floor still matters -- a short trailing clause like "have known." given
    a proportional half-second is on screen too briefly to read whatever its
    reading speed says -- so cues below it are raised, and the deficit comes off
    the cues that have room, in proportion to the room they have.

    When even the floor does not fit, the line is simply too crowded; divide it
    evenly and let `check` report it rather than picking a victim.
    """
    n = len(weights)
    if n == 1:
        return [dur]
    if dur < n * MIN_CUE:
        return [dur / n] * n
    total = float(sum(weights)) or 1.0
    out = [dur * (w / total) for w in weights]
    starved = [i for i, p in enumerate(out) if p < MIN_CUE]
    if not starved:
        return out
    deficit = sum(MIN_CUE - out[i] for i in starved)
    donors = [i for i in range(n) if i not in starved]
    spare = sum(out[i] - MIN_CUE for i in donors)
    if spare <= 0:
        return [dur / n] * n
    for i in starved:
        out[i] = MIN_CUE
    for i in donors:
        out[i] -= deficit * ((out[i] - MIN_CUE) / spare)
    return out


def cues(sb, base, script=None, spans=None):
    """Walk the storyboard's narration into timed, wrapped cues.

    `script` supplies the words for storyboards that time their lines by audio
    file and never recorded the text. Carrying `text` in the storyboard is
    better -- it keeps the words next to the timing that was rendered -- but a
    board built before that was expected can still be captioned rather than
    left to the platform's recogniser.

    `spans` is the renderer's own published timeline. Prefer it over anything
    derived here: the renderer trims each clip's recorded silence before it
    lays the voice down, so the file on disk is about a second longer than
    what plays, and re-measuring it walks the captions steadily off the
    picture.
    """
    lines = sb.get("narration") or []
    if not lines:
        die("this storyboard has no `narration`, so there is nothing to "
            "caption")

    words = {}
    if script:
        with open(script) as fh:
            raw = json.load(fh)
        items = raw.get("narration") if isinstance(raw, dict) else raw
        if items is None:
            die("%s carries no `narration`, so it supplies no words. Pass a "
                "list of lines, or an object with a `narration` key." % script)
        if not isinstance(items, list):
            die("%s should hold a list of narration lines." % script)
        for item in items:
            if isinstance(item, dict) and item.get("id") and item.get("text"):
                words[item["id"]] = item["text"]

    t = float((sb.get("timing") or {}).get("lead_in", 0.0) or 0.0)
    out = []
    missing = []
    for n, ln in enumerate(lines, 1):
        lid = ln.get("id") or ("l%d" % n)
        text = (ln.get("text") or words.get(lid) or "").strip()
        if spans is not None and lid in spans:
            start_at, end_at = spans[lid]
            t, dur = start_at, end_at - start_at
        else:
            if spans is not None:
                # Already doomed: the `missing` check below diagnoses this
                # properly. Probing the clip first would let an unrelated
                # "audio does not exist" error mask the real cause.
                missing.append(lid)
                dur = float(ln.get("duration") or 0.0)
            else:
                dur = ln.get("duration")
                if dur is None:
                    audio = ln.get("audio")
                    if not audio:
                        die("line %s carries neither `duration` nor `audio`, so "
                            "it cannot be timed" % lid)
                    p = (audio if os.path.isabs(audio)
                         else os.path.join(base, audio))
                    if not os.path.exists(p):
                        die("line %s points at %s, which does not exist. Render "
                            "the voice before captioning." % (lid, audio))
                    dur = probe_duration(p)
        dur = float(dur)

        if text:
            blocks = [wrap(c) for c in chunk(text, MAX_LINE * MAX_LINES)]
            weights = [max(1, sum(len(x) for x in b)) for b in blocks]
            shares = share_time(dur, weights)
            start = t
            for j, (block, share) in enumerate(zip(blocks, shares)):
                # the last cue lands on t + dur exactly, so rounding cannot
                # accumulate into drift across a long film
                end = t + dur if j == len(blocks) - 1 else start + share
                out.append({"id": lid if len(blocks) == 1
                            else "%s.%d" % (lid, j + 1),
                            "start": start, "end": end, "lines": block})
                start = end
        t += dur + float(ln.get("gap_after", 0.0) or 0.0)

    if missing:
        die("the timeline does not place %d narration line(s) -- %s%s. It was "
            "written for a different cut of this board; re-render, or drop "
            "--timeline to fall back to measuring the clips."
            % (len(missing), ", ".join(missing[:5]),
               "" if len(missing) <= 5 else ", ..."))

    if not out:
        die("no narration line carries any `text`. A storyboard timed purely "
            "by audio still needs the words -- they are what gets indexed. "
            "Either carry `text` beside `audio` in the storyboard, or pass "
            "--script lines.json.")
    return out, t


def render_srt(cs):
    blocks = []
    for i, c in enumerate(cs, 1):
        blocks.append("%d\n%s --> %s\n%s\n"
                      % (i, stamp(c["start"]), stamp(c["end"]),
                         "\n".join(c["lines"])))
    return "\n".join(blocks)


def render_vtt(cs):
    body = "\n".join("%s --> %s\n%s\n"
                     % (stamp(c["start"], "."), stamp(c["end"], "."),
                        "\n".join(c["lines"])) for c in cs)
    return "WEBVTT\n\n" + body


def check(cs, film, span):
    """Report what is wrong rather than quietly shipping it."""
    problems = []
    for c in cs:
        dur = c["end"] - c["start"]
        chars = sum(len(x) for x in c["lines"])
        if dur < MIN_CUE:
            problems.append("%s: on screen for %.2fs; below the %.1fs floor"
                            % (c["id"], dur, MIN_CUE))
        if dur > 0 and chars / dur > MAX_CPS:
            problems.append("%s: %.1f chars/sec; above the %.0f limit -- the "
                            "line is too long for its clip"
                            % (c["id"], chars / dur, MAX_CPS))
        if len(c["lines"]) > MAX_LINES:
            problems.append("%s: %d lines; at most %d"
                            % (c["id"], len(c["lines"]), MAX_LINES))
        for L in c["lines"]:
            if len(L) > MAX_LINE:
                problems.append("%s: %d characters on one line; at most %d"
                                % (c["id"], len(L), MAX_LINE))
    for a, b in zip(cs, cs[1:]):
        if b["start"] < a["end"] - 1e-6:
            problems.append("%s overlaps %s" % (a["id"], b["id"]))

    if film:
        ff = shutil.which("ffprobe")
        if ff:
            r = subprocess.run([ff, "-v", "error", "-show_entries",
                                "format=duration", "-of",
                                "default=nw=1:nk=1", film],
                               capture_output=True, text=True)
            try:
                real = float((r.stdout or "").strip())
            except ValueError:
                real = None
            if real is not None:
                if cs[-1]["end"] > real + 0.5:
                    problems.append(
                        "the last cue ends at %.2fs but %s is only %.2fs long "
                        "-- the captions were built from a different cut"
                        % (cs[-1]["end"], os.path.basename(film), real))
                elif abs(span - real) > 1.5:
                    problems.append(
                        "storyboard timeline is %.2fs but %s is %.2fs -- they "
                        "drifted by %.2fs"
                        % (span, os.path.basename(film), real,
                           abs(span - real)))
    return problems


def main():
    ap = argparse.ArgumentParser(
        description="Build the caption file from a rendered storyboard.")
    ap.add_argument("storyboard")
    ap.add_argument("-o", "--out", required=True, help="captions.srt")
    ap.add_argument("--vtt", help="also write WebVTT here")
    ap.add_argument("--script", metavar="LINES",
                    help="lines.json to take the words from, when the "
                         "storyboard times by audio and carries no text")
    ap.add_argument("--check", metavar="FILM",
                    help="verify the timeline against the finished film")
    ap.add_argument("--timeline", metavar="JSON",
                    help="the renderer's published timeline; found "
                         "automatically beside the film or the storyboard")
    ap.add_argument("--no-timeline", action="store_true",
                    help="ignore any published timeline and measure the "
                         "narration clips instead")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero if anything is wrong")
    a = ap.parse_args()

    if not os.path.exists(a.storyboard):
        die("no such storyboard: %s" % a.storyboard)
    with open(a.storyboard) as fh:
        sb = json.load(fh)

    if a.script and not os.path.exists(a.script):
        die("no such script: %s" % a.script)

    spans = None
    tldoc = None
    if not a.no_timeline:
        tlp = a.timeline or find_timeline(a.storyboard, a.check)
        if a.timeline and not os.path.exists(a.timeline):
            die("no such timeline: %s" % a.timeline)
        if tlp:
            spans, tldoc = load_timeline(tlp)
            print("captions: timing from %s" % tlp)
    if spans is None:
        # Only worth saying when it matters: a board that declares plain
        # `duration` values is already exact, but one timed by audio file is
        # about to be measured off clips that are longer than what plays.
        if any(ln.get("duration") is None and ln.get("audio")
               for ln in (sb.get("narration") or [])):
            print("captions: WARNING -- no published timeline; timing from "
                  "the narration clips, which still carry their recorded "
                  "silence and will run long. Re-render to publish one.",
                  file=sys.stderr)

    cs, span = cues(sb, os.path.dirname(os.path.abspath(a.storyboard)),
                    a.script, spans)
    if tldoc and tldoc.get("duration"):
        # The walked span stops after the last line's gap; the renderer's own
        # figure includes the tail it actually held on, which is what the film
        # is long.
        span = float(tldoc["duration"])

    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    with open(a.out, "w") as fh:
        fh.write(render_srt(cs))
    if a.vtt:
        with open(a.vtt, "w") as fh:
            fh.write(render_vtt(cs))

    print("captions: %d cues, %s -> %s"
          % (len(cs), stamp(cs[0]["start"]), stamp(cs[-1]["end"])))
    print("  %s" % a.out + (" + %s" % a.vtt if a.vtt else ""))

    problems = check(cs, a.check, span)
    for p in problems:
        print("captions: %s" % p, file=sys.stderr)
    if problems:
        print("captions: %d problem(s)" % len(problems), file=sys.stderr)
        if a.strict:
            return 1
    else:
        print("  reading speed, line length and continuity all within limits")
    return 0


if __name__ == "__main__":
    sys.exit(main())
