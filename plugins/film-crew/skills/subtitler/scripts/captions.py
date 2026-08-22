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
# accessibility figures broadcasters converged on: much above 17 cps and a
# viewer cannot finish a cue before it leaves, and a third line pushes the
# safe-area on a phone.
MAX_CPS = 17.0
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


def cues(sb, base, script=None):
    """Walk the storyboard's narration into timed, wrapped cues.

    `script` supplies the words for storyboards that time their lines by audio
    file and never recorded the text. Carrying `text` in the storyboard is
    better -- it keeps the words next to the timing that was rendered -- but a
    board built before that was expected can still be captioned rather than
    left to the platform's recogniser.
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
    for n, ln in enumerate(lines, 1):
        lid = ln.get("id") or str(n)
        text = (ln.get("text") or words.get(lid) or "").strip()
        dur = ln.get("duration")
        if dur is None:
            audio = ln.get("audio")
            if not audio:
                die("line %s carries neither `duration` nor `audio`, so it "
                    "cannot be timed" % lid)
            p = audio if os.path.isabs(audio) else os.path.join(base, audio)
            if not os.path.exists(p):
                die("line %s points at %s, which does not exist. Render the "
                    "voice before captioning." % (lid, audio))
            dur = probe_duration(p)
        dur = float(dur)

        if text:
            blocks = [wrap(c) for c in chunk(text, MAX_LINE * MAX_LINES)]
            weights = [max(1, sum(len(x) for x in b)) for b in blocks]
            total = float(sum(weights))
            start = t
            for j, (block, weight) in enumerate(zip(blocks, weights)):
                # the last cue lands on t + dur exactly, so rounding cannot
                # accumulate into drift across a long film
                end = (t + dur if j == len(blocks) - 1
                       else start + dur * (weight / total))
                out.append({"id": lid if len(blocks) == 1
                            else "%s.%d" % (lid, j + 1),
                            "start": start, "end": end, "lines": block})
                start = end
        t += dur + float(ln.get("gap_after", 0.0) or 0.0)

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
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero if anything is wrong")
    a = ap.parse_args()

    if not os.path.exists(a.storyboard):
        die("no such storyboard: %s" % a.storyboard)
    with open(a.storyboard) as fh:
        sb = json.load(fh)

    if a.script and not os.path.exists(a.script):
        die("no such script: %s" % a.script)
    cs, span = cues(sb, os.path.dirname(os.path.abspath(a.storyboard)),
                    a.script)

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
