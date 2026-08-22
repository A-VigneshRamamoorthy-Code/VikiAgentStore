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


def audio(project, force=False):
    dest = project.audio
    if os.path.exists(dest) and not force and os.path.getsize(dest) > 1_000_000:
        say(f"audio cached: {dest}")
        return dest
    say("fetching audio ...")
    subprocess.run(
        ["yt-dlp", "-f", "bestaudio[ext=m4a]/bestaudio", "--no-part",
         "-o", dest, project.url], check=True)
    say(f"audio: {dest} ({os.path.getsize(dest)/1e6:.0f} MB)")
    return dest


def scan_video(project, force=False):
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
         "--no-part", "--merge-output-format", "mp4", "-o", dest, project.url],
        check=True)
    say(f"scan video: {dest} ({os.path.getsize(dest)/1e6:.0f} MB)")
    return dest


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("project")
    ap.add_argument("--stage", default="all",
                    choices=["probe", "audio", "scan", "all"])
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    pr = Project(a.project)

    if a.stage in ("probe", "all"):
        probe(pr)
    if a.stage in ("audio", "all"):
        audio(pr, a.force)
    if a.stage == "scan" or (a.stage == "all" and pr.get("vip", "enabled")):
        scan_video(pr, a.force)
    elif a.stage == "all":
        say("vip disabled -- skipping the 360p scan copy")


if __name__ == "__main__":
    main()
