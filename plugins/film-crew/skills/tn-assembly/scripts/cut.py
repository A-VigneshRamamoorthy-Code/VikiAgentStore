"""Fetch each planned segment from the source at full resolution.

Two failure modes this exists to avoid, both learned the hard way:

**Desync.** Pulling a section with `ffmpeg -ss ... -c copy` snaps the *video*
back to the nearest preceding keyframe while the *audio* starts exactly at the
seek point. On a webcast with sparse keyframes the picture ran five seconds
behind the sound, and nothing in the container metadata reveals it -- both
streams report a start time of zero. `yt-dlp --force-keyframes-at-cuts`
re-encodes around the cut so both streams begin on the requested frame.

**Abrupt cuts.** A fixed window slices through the middle of a sentence. Every
in and out point is snapped onto a speech onset and a following pause first,
so clips begin and end where a person actually stopped talking.

Only the planned seconds are downloaded, never the whole session.
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from boundaries import snap  # noqa: E402
from config import Project, parse_approvals, require_overwrite_approval, say  # noqa: E402


def fetch(url, start, end, dest, fmt, live=False):
    cmd = ["yt-dlp", "-f", fmt,
           "--download-sections", f"*{start:.2f}-{end:.2f}",
           "--force-keyframes-at-cuts", "--no-part",
           "--merge-output-format", "mp4"]
    if live:
        # without this a live source is seeked relative to the moment the
        # download starts, not to the start of the session, so every clip
        # lands at the wrong offset
        cmd.append("--live-from-start")
    cmd += ["-o", dest, url]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(dest):
        raise RuntimeError(f"fetch failed {start:.0f}-{end:.0f}: "
                           f"{r.stderr[-400:]}")


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,width,height,duration", "-of", "json", path],
        capture_output=True, text=True).stdout
    return json.loads(out).get("streams", [])


def cut_one(pr, item, dest, do_snap=True, approvals=None):
    approvals = approvals or {}
    require_overwrite_approval(dest, pr, approvals)
    a, b = float(item["start"]), float(item["end"])
    info = {}
    if do_snap:
        # A Short must snap inside its own length band. Falling back to the
        # longform band (34-95s) silently refuses every boundary for a short
        # clip, so it would ship unsnapped -- i.e. cut mid-sentence.
        if item.get("kind") == "short":
            a, b, info = snap(pr, a, b,
                              min_len=pr.get("shorts", "min_len"),
                              max_len=pr.get("shorts", "max_len"))
        else:
            a, b, info = snap(pr, a, b)
    if os.path.exists(dest):
        os.remove(dest)
    fetch(pr.url, a, b, dest, pr.get("source", "format", default="137+140"),
          live=pr.get("source", "live", default=False))
    streams = probe(dest)
    v = next((s for s in streams if s["codec_type"] == "video"), {})
    say(f"  {os.path.basename(dest)}  {v.get('width')}x{v.get('height')}  "
        f"{float(v.get('duration', 0)):.2f}s  {info.get('reason', '')}")
    return {"cut_start": round(a, 2), "cut_end": round(b, 2),
            "duration": round(b - a, 2),
            "file": os.path.relpath(dest, pr.root), "boundary": info}


def main():
    ap = argparse.ArgumentParser(
        description="Cut planned segments from the source video")
    ap.add_argument("project")
    ap.add_argument("--only", default=None,
                    help="episode or short id, e.g. ep01 or sh02")
    ap.add_argument("--no-snap", action="store_true",
                    help="skip boundary snapping (faster, cuts mid-sentence)")
    ap.add_argument("--approve-overwrite", action="append", default=[],
                    help="allow replacing an existing artifact as path:sha256")
    a = ap.parse_args()

    pr = Project(a.project)
    approvals = parse_approvals(a.approve_overwrite)
    plan = pr.load("plan")
    if not plan:
        raise SystemExit("no meta/plan.json -- run plan.py first")
    if not pr.url:
        raise SystemExit("project.json has no source.url")

    for ep in plan["episodes"]:
        if a.only and ep["id"] != a.only:
            continue
        out = pr.p("clips", ep["id"])
        os.makedirs(out, exist_ok=True)
        say(f"{ep['id']}: {len(ep['clips'])} clips")
        for i, clip in enumerate(ep["clips"], 1):
            dest = os.path.join(out, f"clip_{i:02d}.mp4")
            clip.update(cut_one(pr, clip, dest, not a.no_snap, approvals))

    for s in plan["shorts"]:
        if a.only and s["id"] != a.only:
            continue
        out = pr.p("clips", "shorts")
        os.makedirs(out, exist_ok=True)
        dest = os.path.join(out, f"{s['id']}.mp4")
        say(f"{s['id']}: {s['length']:.0f}s")
        s.update(cut_one(pr, s, dest, not a.no_snap, approvals))

    pr.save("plan", plan)
    say(f"updated {pr.p('meta', 'plan.json')} with cut points")


if __name__ == "__main__":
    main()
