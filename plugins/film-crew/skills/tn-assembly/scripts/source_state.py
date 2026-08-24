"""Decide what kind of source we are looking at before any work starts.

The pipeline behaves very differently depending on the answer, and getting it
wrong is expensive in both directions. Treating a live stream as a recording
means the session ends before anything is published, and for a live sitting
the audience arrives while it is still running -- publishing an hour late is
most of the value gone. Treating a recording as live means sitting in a
polling loop forever waiting for a stream that already finished.

So the question is settled once, explicitly, and written to
`meta/source_state.json` for later stages to read:

  live      -- still broadcasting. Cut and publish as it runs, keep following.
  recorded  -- finished. One pass, no tracking.
  upcoming  -- scheduled but not started. Nothing to cut yet.
  none      -- no URL given and the channel has no live stream.

`none` is a real answer, not a failure. Reporting "no live session yet" is
more useful than inventing work.
"""
import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import Project, say  # noqa: E402

LIVE = "live"
RECORDED = "recorded"
UPCOMING = "upcoming"
NONE = "none"

# The title goes last on purpose. It is the only free-text field, and a title
# containing a tab would otherwise shift every field after it -- silently
# putting a fragment of the title where the video id belongs.
FIELDS = ("%(live_status)s\t%(is_live)s\t%(duration)s\t%(id)s\t"
          "%(webpage_url)s\t%(release_timestamp)s\t%(title)s")
NFIELDS = 7


def _probe(url):
    """Ask yt-dlp what this URL is, without downloading anything.

    Returns `(info, error)`. A `None` info with an error string means the
    probe itself failed, which is different from "there is nothing here" --
    the caller has to be able to tell a network failure from an answer.
    """
    out = subprocess.run(
        ["yt-dlp", "--no-warnings", "--skip-download", "--playlist-items", "1",
         "--print", FIELDS, url],
        capture_output=True, text=True)
    if out.returncode != 0 or not out.stdout.strip():
        return None, (out.stderr or "").strip()[-300:] or "no output"
    line = out.stdout.strip().splitlines()[0]
    parts = line.split("\t", NFIELDS - 1)
    while len(parts) < NFIELDS:
        parts.append("")
    status, is_live, dur, vid, page, started, title = parts[:NFIELDS]

    # An in-progress broadcast has no length: yt-dlp prints "NA" because
    # `lengthSeconds` is absent until the stream ends. Folding that into 0.0
    # would be indistinguishable from a zero-length video, and every consumer
    # computing a live edge from it would silently get a nonsense answer.
    # `None` forces the caller to deal with "unknown".
    try:
        duration = float(dur)
    except (TypeError, ValueError):
        duration = None

    # `release_timestamp` is when the broadcast started, and it *is* present
    # while it is running. It is the only reliable way to know how much
    # session exists so far, since duration arrives only once it ends.
    try:
        began = float(started)
    except (TypeError, ValueError):
        began = None
    if duration is None and began:
        elapsed = time.time() - began
        if elapsed > 0:
            duration = elapsed

    return {"live_status": status, "is_live": is_live == "True",
            "duration": duration, "began": began, "title": title,
            "video_id": vid,
            "url": (page if page.startswith("http") else url)}, None


def classify(info):
    """Map yt-dlp's vocabulary onto the two behaviours we actually have.

    `post_live` is the awkward one: the broadcast has stopped but YouTube is
    still assembling the final recording, so the duration keeps moving and a
    cut taken now may point at footage that shifts underneath it. It is
    treated as live -- keep following -- because the alternative is producing
    clips against a length that is still changing.
    """
    s = (info.get("live_status") or "").strip()
    if s == "is_live" or info.get("is_live"):
        return LIVE
    if s == "is_upcoming":
        return UPCOMING
    if s == "post_live":
        return LIVE
    return RECORDED


def channel_url(value):
    """Normalise whatever the config gives us into a browsable channel URL.

    The shipped config carries a bare handle (`"politainment"`), not `@name`
    and not a URL, so a check for a leading `@` misses the only form that is
    actually in use and the probe ends up requesting the literal string
    `politainment/live`. A channel that *is* live then reports as `none`,
    which is the most misleading answer available.
    """
    v = (value or "").strip().rstrip("/")
    if not v:
        return ""
    if v.startswith("http://") or v.startswith("https://"):
        return v
    if v.startswith("@"):
        return f"https://www.youtube.com/{v}"
    if v.startswith("UC") and len(v) == 24:
        return f"https://www.youtube.com/channel/{v}"
    return f"https://www.youtube.com/@{v}"


def channel_live(url):
    """Look for a live stream on a channel.

    YouTube exposes `<channel>/live`, which redirects to the live broadcast
    when there is one. `/streams` is checked as well because `/live` only
    resolves while something is actually on air, and an upcoming stream is
    worth reporting distinctly from nothing at all.

    A live result wins over an upcoming one: a channel can have tomorrow's
    sitting scheduled while today's is still running, and returning the
    scheduled one would park the tracker on a stream that has not started.
    """
    base = url.rstrip("/")
    best = None
    errors = []
    for suffix in ("/live", "/streams"):
        info, err = _probe(base + suffix)
        if not info:
            errors.append(err)
            continue
        st = classify(info)
        if st == LIVE:
            return info, None
        if st == UPCOMING and best is None:
            best = info
    return best, (errors if len(errors) == 2 else None)


def resolve(pr, url=None):
    """Work out the source and its state, preferring an explicit URL."""
    url = url or pr.get("source", "url", default="") or ""
    if url:
        info, err = _probe(url)
        if not info:
            raise SystemExit(f"could not read {url}: {err}")
        return classify(info), info

    # The source channel is not the destination channel. `channel.*` is where
    # finished videos are uploaded -- looking there for a sitting to cut would
    # find our own re-uploads, so it is only a fallback and only if someone
    # has deliberately pointed it at the broadcaster.
    raw = (pr.get("source", "channel_url", default="")
           or pr.get("source", "channel", default=""))
    if not raw:
        raise SystemExit(
            "no source.url and no source.channel_url in project.json -- "
            "nothing to check. Give a video URL, or set source.channel_url "
            "to the broadcaster's channel (not your upload channel).")
    chan = channel_url(raw)
    say(f"no source URL; checking {chan} for a live stream ...")
    info, errors = channel_live(chan)
    if not info:
        if errors:
            # every probe failed: that is a broken lookup, not an empty one,
            # and reporting "no live session" would hide it
            raise SystemExit(
                f"could not check {chan}: {errors[0]}")
        return NONE, {"checked_channel": chan}
    return classify(info), info


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("project")
    ap.add_argument("--url", default=None,
                    help="override project.json's source.url")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    pr = Project(a.project)

    state, info = resolve(pr, a.url)
    rec = {"state": state, **info}
    pr.save("source_state.json", rec)

    if state == NONE:
        say("no live session yet")
    elif state == UPCOMING:
        say(f"scheduled but not started: {info.get('title','')}")
    elif state == LIVE:
        say(f"LIVE: {info.get('title','')}")
        say("publish as it runs -- see live.py")
    else:
        say(f"recorded: {info.get('title','')} "
            f"({(info.get('duration') or 0)/3600:.2f}h)")
    if not a.quiet:
        print(json.dumps(rec, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
