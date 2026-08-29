"""Cutting from a locally recorded copy instead of re-fetching sections.

Some live streams will not serve `--download-sections` at all: the manifest is
live DASH and yt-dlp answers "This format cannot be partially downloaded", so
every per-clip fetch in `cut.py` fails while `source_state.py` still correctly
reports `live` and the loop looks perfectly healthy. A whole sitting can be
lost to this. `reference/live-sessions.md` prescribes the fallback -- record
continuously and cut locally -- and this module is that path.

It is inert unless `source.local_video` is set, so the normal fetch-per-clip
behaviour is unchanged for every source that supports sections.

Two things here are load-bearing:

**The usable end is the shorter of the two recordings, not the audio.** The
audio stream is a fraction of the video's bitrate, so it catches up to the
live edge many minutes before the picture does. `local_end()` in `live.py`
probes the audio, so without capping, analysis would score -- and planning
would happily schedule -- an hour of session for which no picture exists yet,
and every one of those cuts would seek past the end of the video. Capping the
audio written to `src/` to the video's extent makes every downstream stage
agree on one ceiling without any of them needing to know why.

**Cuts are re-encoded, not copied.** `-c copy` snaps the video back to the
preceding keyframe while the audio starts exactly on the seek point, which is
the desync described in `reference/cutting.md` and is invisible in a container
probe. Seeking each input separately and re-encoding makes both streams begin
on the requested frame.
"""
import os
import subprocess

from config import say


def _abs(root, path):
    if not path:
        return ""
    return path if os.path.isabs(path) else os.path.join(root, path)


def paths(project):
    """The recorded video and audio files, or `None` if not in local mode."""
    v = _abs(project.root, project.get("source", "local_video", default=""))
    a = _abs(project.root, project.get("source", "local_audio", default=""))
    if not v:
        return None
    return v, (a or v)


def duration(path):
    if not path or not os.path.exists(path):
        return None
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except (TypeError, ValueError):
        return None


def usable_end(project):
    """How much session exists in *both* streams.

    A clip needs picture and sound, so the shorter recording is the ceiling.
    """
    p = paths(project)
    if not p:
        return None
    have = [d for d in (duration(p[0]), duration(p[1])) if d]
    return min(have) if have else None


def build_audio(project, dest):
    """Write `src/audio.m4a` from the local recording, capped to the video.

    Copied rather than re-encoded: this file is only ever read by the analysis
    and boundary passes, so re-encoding it would cost minutes per cycle and
    change nothing they measure.
    """
    p = paths(project)
    if not p:
        return None
    video, audio = p
    end = usable_end(project)
    if not end or end <= 0:
        say("local source: nothing recorded yet")
        return None
    tmp = dest + ".part.m4a"
    for f in (tmp, dest):
        if os.path.exists(f):
            os.remove(f)
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", audio, "-t", f"{end:.2f}",
         "-map", "0:a:0", "-c", "copy", "-movflags", "+faststart", tmp],
        capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(tmp):
        raise RuntimeError(f"local audio snapshot failed: {r.stderr[-400:]}")
    os.replace(tmp, dest)
    say(f"local audio: {dest} ({os.path.getsize(dest)/1e6:.0f} MB, "
        f"capped to {end/60:.1f} min held in both streams)")
    return dest


def build_scan(project, dest, height=360):
    """360p copy for the face sweep, transcoded from the local recording."""
    p = paths(project)
    if not p:
        return None
    video, audio = p
    end = usable_end(project)
    if not end or end <= 0:
        return None
    tmp = dest + ".part.mp4"
    for f in (tmp, dest):
        if os.path.exists(f):
            os.remove(f)
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", video, "-t", f"{end:.2f}",
         "-map", "0:v:0", "-vf", f"scale=-2:{height}", "-an",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "30", tmp],
        capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(tmp):
        raise RuntimeError(f"local scan copy failed: {r.stderr[-400:]}")
    os.replace(tmp, dest)
    say(f"local scan copy: {dest} ({os.path.getsize(dest)/1e6:.0f} MB)")
    return dest


def cut(project, start, end, dest):
    """Cut one segment out of the local recording, video and audio together.

    Each input is seeked independently before `-i` so the decoder starts at a
    keyframe and discards forward to the exact point; with a re-encode on the
    output both streams then begin on the requested frame, which is what keeps
    them in sync.
    """
    p = paths(project)
    if not p:
        return False
    video, audio = p
    have = usable_end(project)
    if have and end > have:
        raise RuntimeError(
            f"segment {start:.0f}-{end:.0f} runs past the {have:.0f}s "
            f"recorded so far -- refusing to cut a truncated clip")
    dur = end - start
    fps = project.get("video", "fps", default=30)
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-ss", f"{start:.3f}", "-i", video]
    if audio != video:
        cmd += ["-ss", f"{start:.3f}", "-i", audio,
                "-map", "0:v:0", "-map", "1:a:0"]
    else:
        cmd += ["-map", "0:v:0", "-map", "0:a:0"]
    cmd += ["-t", f"{dur:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-r", str(fps), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart", dest]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(dest):
        raise RuntimeError(f"local cut failed {start:.0f}-{end:.0f}: "
                           f"{r.stderr[-400:]}")
    return True
