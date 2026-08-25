"""Follow a live session, publishing as it runs.

The reason this exists is timing. A sitting draws its audience while it is
still sitting: the clip that would have found viewers at 11am finds very few
at 7pm, and a session recorded, cut and uploaded the following morning is
competing against every news channel that managed it the same day. For a live
source, speed is most of the value.

The loop is:

    probe -> fetch the finished part -> analyse -> plan -> publish what is new

Three things about that are less obvious than they look.

**Published work is tracked by span, not by plan id.** `plan.py` numbers items
by rank (`sh01` is whatever currently ranks first), and this loop deliberately
re-plans over the whole session each cycle, so those numbers move. A single
new clash discovered late shifts every lower-ranked id by one -- which would
both skip the newcomer that inherited a published id and re-upload the item
that shifted into a fresh one. Overlap against a recorded span is stable
under renumbering; an id is not.

**Analysis re-runs over the whole session each cycle.** That is a real cost
and a deliberate one: highlight scores are relative to the session, so a
window scored against the first twenty minutes is scored against the wrong
baseline, and a quiet morning would otherwise promote material that a busy
afternoon shows to be unremarkable.

**A cycle that failed publishes nothing.** Stage failures used to be
discarded, which meant a cycle whose analysis died would go on to publish
against whatever `plan.json` happened to be left on disk -- stale candidates
measured against a newer live edge.
"""
import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import Project, hhmmss, say  # noqa: E402
import source_state  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PROGRESS = "live_progress.json"
LOCK = "live.lock"

# Two spans count as the same moment when they overlap by this much of the
# shorter one. Boundary snapping shifts an in/out point by a few seconds
# between cycles, so the test has to tolerate drift without merging two
# genuinely adjacent highlights.
SAME_MOMENT = 0.6


def _run(script, *args):
    cmd = [sys.executable, os.path.join(HERE, script), *[str(a) for a in args]]
    return subprocess.run(cmd).returncode == 0


def progress(pr):
    return pr.load(PROGRESS, default={"items": [], "cycles": 0,
                                      "covered_until": 0.0})


def _span(item):
    """Session start and end for a planned item.

    Shorts carry `start`/`end` directly, but an episode is a list of clips and
    has neither. Reading `.get("end")` on one yields 0, which silently reads
    as "ends at the very beginning" -- every episode would look unready
    forever and the live run would publish nothing but Shorts.
    """
    if item.get("clips"):
        starts = [c["start"] for c in item["clips"]]
        ends = [c["end"] for c in item["clips"]]
        return min(starts), max(ends)
    return item.get("start", 0.0), item.get("end", 0.0)


def overlaps(a, b, frac=SAME_MOMENT):
    """Do two spans describe the same moment?"""
    lo = max(a[0], b[0])
    hi = min(a[1], b[1])
    if hi <= lo:
        return False
    shorter = min(a[1] - a[0], b[1] - b[0])
    return shorter > 0 and (hi - lo) / shorter >= frac


def already(prog, kind, span):
    """The record for this moment, if we have touched it before."""
    for rec in prog["items"]:
        if rec["kind"] == kind and overlaps((rec["start"], rec["end"]), span):
            return rec
    return None


def local_end(pr):
    """How much session we actually hold on disk.

    This -- not the reported duration -- is the real limit on what can be
    cut. A stream can be an hour long while the local copy is twenty minutes
    behind, and cutting against the reported length would seek past the end
    of the media.
    """
    for path in (pr.audio, pr.scan_video):
        if not os.path.exists(path):
            continue
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True)
        try:
            return float(r.stdout.strip())
        except (TypeError, ValueError):
            continue
    return None


def ready(end, safe_until):
    """Only publish a moment the stream has moved safely past.

    A highlight that ends near the live edge is the one most likely to be
    cut short: the recording is still being assembled there, and a clip taken
    at the boundary can land on footage that shifts underneath it. Holding
    back until the session is a margin beyond the end costs a few minutes and
    avoids republishing a truncated clip.
    """
    return bool(end) and end <= safe_until


def clear_artifacts(pr, item_id):
    """Remove a half-finished item so it can be retried.

    `cut.py`, `build.py` and `shorts.py` all refuse to overwrite an existing
    artifact without an explicit hash-bound approval -- a good rule for a
    human re-run, and a trap here. If a publish dies after cutting, every
    later cycle hits that refusal and the moment can never publish again. The
    files belong to this loop and it is the loop's job to clean them up.
    """
    for d in (pr.p("clips"), pr.p("out"), pr.p("out", "shorts")):
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if fn.startswith(item_id):
                try:
                    os.remove(os.path.join(d, fn))
                except OSError:
                    pass


def publish_one(pr, prog, item_id, kind, span, marketing):
    """Cut, build and hand one finished item to packaging.

    Progress is written *before* the upload, not after. An upload that
    succeeds and then loses the record is the one failure this loop must not
    have: it produces a public video the tracker believes is unpublished, and
    every later cycle would try to publish it again.
    """
    say(f"publishing {item_id} ({hhmmss(span[0])}-{hhmmss(span[1])}) ...")
    clear_artifacts(pr, item_id)

    if not _run("cut.py", pr.root, "--only", item_id):
        return False
    stage = "shorts.py" if kind == "shorts" else "build.py"
    if not _run(stage, pr.root, "--only", item_id):
        return False

    rec = {"kind": kind, "id": item_id, "start": span[0], "end": span[1],
           "stage": "rendered", "at": time.time()}
    prog["items"].append(rec)
    pr.save(PROGRESS, prog)

    if not marketing:
        return True

    rec["stage"] = "uploading"
    pr.save(PROGRESS, prog)
    r = subprocess.run([sys.executable, marketing, pr.root,
                        "--only", item_id])
    if r.returncode != 0:
        rec["stage"] = "rendered"
        rec["note"] = "packaging failed; built but not uploaded"
        pr.save(PROGRESS, prog)
        say(f"  packaging failed for {item_id}; left built but unpublished")
        return False
    rec["stage"] = "published"
    pr.save(PROGRESS, prog)
    _report_first(prog)
    return True


# Time-to-first-video is the metric that matters on a live source, and it is
# the one that silently regressed: a run that felt busy took two and a half
# hours to put anything on the channel, because the work that blocks the first
# publish is invisible unless it is measured. Printing it makes a regression
# obvious in the log instead of the next morning.
FIRST_TARGET = 900.0
_STARTED = None


def _report_first(prog):
    if _STARTED is None:
        return
    if sum(1 for r in prog.get("items", []) if r["stage"] == "published") != 1:
        return
    took = time.time() - _STARTED
    how = "within" if took <= FIRST_TARGET else "OVER"
    say(f"first video live after {took/60:.1f} min "
        f"({how} the {FIRST_TARGET/60:.0f} min target)")
    if took > FIRST_TARGET:
        say("  a live sitting is a perishable story -- see "
            "reference/live-sessions.md 'Time to first video'")


def cycle(pr, marketing, edge_margin, opening=False):
    state, info = source_state.resolve(pr)
    live = state == source_state.LIVE
    reported = info.get("duration")

    # keep the pinned URL and liveness in project.json: every child process
    # reads them from there, and a stream discovered from a channel would
    # otherwise be invisible to ingest.py and cut.py
    if info.get("url") and info["url"] != pr.get("source", "url", default=""):
        pr.set("source", "url", value=info["url"])
    pr.set("source", "live", value=bool(live))

    say(f"state={state} reported={hhmmss(reported or 0)}"
        f"{'' if reported else ' (unknown)'}")

    ok = _run("ingest.py", pr.root, "--stage", "audio", "--force",
              *(["--until", f"{reported:.0f}"] if live and reported else []))
    if not ok:
        say("ingest failed -- skipping this cycle rather than "
            "publishing against stale analysis")
        return live, 0
    if pr.get("vip", "enabled"):
        if _run("ingest.py", pr.root, "--stage", "scan", "--force",
                *(["--until", f"{reported:.0f}"] if live and reported else [])):
            _run("faces.py", pr.root, "--scan")
        else:
            say("scan copy failed -- continuing without new VIP data")
    if not _run("analyse.py", pr.root) or not _run("plan.py", pr.root):
        say("analysis or planning failed -- publishing nothing this cycle")
        return live, 0

    # what we hold locally is the real ceiling; the reported length is only a
    # hint and is missing entirely for much of a broadcast
    have = local_end(pr)
    edge = have if have else reported
    if not edge:
        say("cannot determine how much session exists yet -- "
            "no reported duration and no local media. Nothing published.")
        return live, 0
    safe_until = (edge - edge_margin) if live else edge
    say(f"have={hhmmss(edge)} safe_until={hhmmss(max(safe_until, 0))}")

    prog = progress(pr)
    plan = pr.load("plan.json", default={})
    items = []
    for key in ("episodes", "shorts"):
        for it in plan.get(key, []) or []:
            if isinstance(it, dict) and it.get("id"):
                items.append((_span(it), it["id"], key))
    if opening:
        # Nothing is published yet, so on this cycle a Short is the fastest
        # route to a live video and the only format that reliably finds an
        # audience (reference/distribution.md). An episode is several clips
        # assembled with an intro and outro; the first one took nearly five
        # minutes to build while a Short took about thirty seconds, and on a
        # cold channel it then earned ten impressions.
        #
        # The usual ordering exists so a Short always has its long-form to
        # point at. That still holds from the second cycle on; here the first
        # Short's link is backfilled once its parent exists, which is a much
        # smaller cost than an hour of a live sitting going unpublished.
        # `plan.py` already emits Shorts strongest-first, so plan order is
        # the publishing order.
        items.sort(key=lambda t: (t[2] != "shorts", t[0]))
    else:
        # episodes first, then by position in the session. A Short is cut to
        # point viewers at its long-form, so publishing it while the episode
        # does not exist yet sends the traffic nowhere.
        items.sort(key=lambda t: (t[2] != "episodes", t[0]))

    published = 0
    for span, item_id, kind in items:
        seen = already(prog, kind, span)
        if seen and seen["stage"] in ("published", "rendered"):
            continue
        if seen and seen["stage"] == "uploading":
            say(f"  {seen['id']} was interrupted mid-upload -- "
                f"skipping. Check the channel before re-running it.")
            continue
        if not ready(span[1], safe_until):
            continue
        if publish_one(pr, prog, item_id, kind, span, marketing):
            published += 1

    prog["cycles"] = prog.get("cycles", 0) + 1
    prog["covered_until"] = max(safe_until, 0)
    pr.save(PROGRESS, prog)
    done = sum(1 for r in prog["items"] if r["stage"] == "published")
    say(f"cycle done: {published} published this cycle, {done} total")
    return live, published


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("project")
    ap.add_argument("--interval", type=float, default=900,
                    help="seconds between cycles while the session runs")
    ap.add_argument("--edge-margin", type=float, default=300,
                    help="stay this far behind the live edge before cutting")
    ap.add_argument("--marketing", default=None,
                    help="path to a per-item packaging script; without it "
                         "items are built but not uploaded")
    ap.add_argument("--max-cycles", type=int, default=0,
                    help="stop after N cycles (0 = until the session ends)")
    a = ap.parse_args()
    pr = Project(a.project)
    global _STARTED
    _STARTED = time.time()

    if a.marketing and not os.path.exists(a.marketing):
        raise SystemExit(f"--marketing script not found: {a.marketing}")

    state, _ = source_state.resolve(pr)
    if state == source_state.NONE:
        say("no live session yet")
        return 0
    if state == source_state.UPCOMING:
        say("session is scheduled but has not started")
        return 0
    if state == source_state.RECORDED:
        say("source is a finished recording -- no tracking needed, "
            "run pipeline.py instead")
        return 0

    lock = pr.p("meta", LOCK)
    if os.path.exists(lock):
        raise SystemExit(
            f"{lock} exists -- another tracker is already following this "
            f"session. Two would publish the same moments twice. Remove the "
            f"file if that run is definitely dead.")
    os.makedirs(pr.p("meta"), exist_ok=True)
    with open(lock, "w") as fh:
        json.dump({"pid": os.getpid(), "started": time.time()}, fh)

    try:
        n = 0
        while True:
            n += 1
            say(f"--- cycle {n} ---")
            live, _ = cycle(pr, a.marketing, a.edge_margin, opening=(n == 1))
            if not live:
                # A cycle that saw a finished stream already ran with the
                # margin removed -- `safe_until` is the full length when the
                # source is not live -- so the tail is covered and a further
                # "final pass" would only re-download and re-analyse the whole
                # session to publish nothing.
                say("session ended and the tail is covered -- "
                    "live tracking complete")
                return 0
            if a.max_cycles and n >= a.max_cycles:
                say(f"stopping after {n} cycles as requested")
                return 0
            say(f"sleeping {a.interval:.0f}s")
            time.sleep(a.interval)
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
