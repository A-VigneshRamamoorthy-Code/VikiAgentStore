"""Fetch what the analysis stages need from the source session.

Two artefacts, deliberately small:

  * `src/audio.m4a`  - full-session audio, drives energy, clash and ASR passes
  * `src/scan_360p.mp4` - a 360p copy, used only for the VIP face sweep

The 1080p footage is never downloaded in full. An eight-hour session is tens of
gigabytes, and only a few minutes of it survive the edit, so the publishable
sections are pulled individually in `cut.py` instead.
"""
import argparse
import json
import os
import subprocess

from config import Project, hhmmss, say


def probe(project):
    """Read duration and title without downloading the media."""
    out = subprocess.run(
        ["yt-dlp", "--no-warnings", "--skip-download", "--print",
         "%(duration)s\t%(title)s\t%(id)s", project.url],
        capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"probe failed: {out.stderr[-400:]}")
    dur, title, vid = out.stdout.strip().split("\t", 2)
    info = {"duration": float(dur), "title": title, "video_id": vid,
            "runtime": hhmmss(float(dur)), "url": project.url}
    project.save("source.json", info)
    say(f"source: {title}")
    say(f"duration: {info['runtime']} ({info['duration']:.0f}s)")
    return info


def _live_args(project, until=None):
    """Extra yt-dlp arguments needed when the source is still broadcasting.

    Two things go wrong without these. yt-dlp's default for a live stream is
    `--no-live-from-start`, which begins at the *current* moment and stays
    attached until the broadcast ends -- so the call never returns during a
    sitting, and the media it eventually writes starts at t=0 where the
    download began rather than where the session began. Every later cut seeks
    in session-absolute time, so that offset silently points every clip at
    the wrong footage.

    `--live-from-start` fixes the origin, and a bounded `--download-sections`
    makes the call terminate instead of following the stream forever.
    """
    if not project.get("source", "live", default=False):
        return []
    args = ["--live-from-start"]
    if until and until > 0:
        args += ["--download-sections", f"*0-{until:.0f}"]
    return args


def audio(project, force=False, until=None):
    dest = project.audio
    if os.path.exists(dest) and not force and os.path.getsize(dest) > 1_000_000:
        say(f"audio cached: {dest}")
        return dest
    say("fetching audio ...")
    subprocess.run(
        ["yt-dlp", "-f", "bestaudio[ext=m4a]/bestaudio", "--no-part",
         *_live_args(project, until),
         "-o", dest, project.url], check=True)
    say(f"audio: {dest} ({os.path.getsize(dest)/1e6:.0f} MB)")
    return dest


def scan_video(project, force=False, until=None):
    """360p copy for the face sweep.

    Resolution is chosen for the detector, not for looks: a chamber wide shot
    puts speaker faces at roughly 40-70px at 360p, which is the smallest size
    ArcFace still discriminates. Going higher costs scan time for no recall.
    """
    dest = project.scan_video
    if os.path.exists(dest) and not force and os.path.getsize(dest) > 1_000_000:
        say(f"scan video cached: {dest}")
        return dest
    say("fetching 360p scan copy (large, runs for a while) ...")
    subprocess.run(
        ["yt-dlp", "-f", "worstvideo[height>=360]+bestaudio/worst[height>=360]",
         "--no-part", "--merge-output-format", "mp4",
         *_live_args(project, until),
         "-o", dest, project.url],
        check=True)
    say(f"scan video: {dest} ({os.path.getsize(dest)/1e6:.0f} MB)")
    return dest


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("project")
    ap.add_argument("--stage", default="all",
                    choices=["probe", "audio", "scan", "all"])
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--until", type=float, default=None,
                    help="for a live source, fetch only up to this many "
                         "seconds from the session start, so the call "
                         "terminates instead of following the broadcast")
    a = ap.parse_args()
    pr = Project(a.project)

    if a.stage in ("probe", "all"):
        probe(pr)
    if a.stage in ("audio", "all"):
        audio(pr, a.force, a.until)
    if a.stage == "scan" or (a.stage == "all" and pr.get("vip", "enabled")):
        scan_video(pr, a.force, a.until)
    elif a.stage == "all":
        say("vip disabled -- skipping the 360p scan copy")


if __name__ == "__main__":
    main()
