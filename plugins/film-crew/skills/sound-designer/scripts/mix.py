#!/usr/bin/env python3
"""Lay a music bed under a finished film, duck it under the narration, and
measure what actually came out.

Before this stage existed the pipeline shipped films that were narration and
nothing else. That is not a stylistic gap, it is a retention one: an unscored
cut sounds like a voicemail, and the silence between sentences reads as a
mistake rather than as a beat.

The two things this module refuses to do on faith:

* **It ducks by measurement, not by a fixed gain.** `sidechaincompress` keys
  the music off the actual narration envelope, so the bed drops when a word
  lands and recovers in the gaps, instead of sitting at one timid level that is
  both inaudible under speech and too loud in a pause.
* **It reports the loudness it achieved, not the one it aimed for.** Adding a
  bed changes the integrated loudness of the whole film, so a level that was
  measured before the mix is no longer true after it.

    python3 mix.py film.mp4 -o mixed.mp4 --bed music.wav --report mix.json
    python3 mix.py film.mp4 --report mix.json          # measure only, no bed
"""

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# Defaults chosen so a bed is *felt* rather than *heard*: -26 LUFS sits roughly
# 12 LU under conversational narration, which is the point at which listeners
# report "music" without reporting "loud music".
BED_LUFS = -26.0
DUCK_RATIO = 8
DUCK_THRESHOLD = 0.04
DUCK_ATTACK_MS = 20
DUCK_RELEASE_MS = 420
FADE = 1.5


def die(msg, code=2):
    print("mix: %s" % msg, file=sys.stderr)
    raise SystemExit(code)


def need(binary):
    p = shutil.which(binary)
    if not p:
        die("%s is not installed. `brew install ffmpeg`" % binary)
    return p


def duration(path):
    """Seconds, from the container rather than from a guess."""
    r = subprocess.run([need("ffprobe"), "-v", "error", "-show_entries",
                        "format=duration", "-of",
                        "default=nw=1:nk=1", path],
                       capture_output=True, text=True)
    try:
        return float((r.stdout or "").strip())
    except ValueError:
        die("could not read the duration of %s" % path)


def has_audio(path):
    r = subprocess.run([need("ffprobe"), "-v", "error", "-select_streams", "a",
                        "-show_entries", "stream=index", "-of",
                        "default=nw=1:nk=1", path],
                       capture_output=True, text=True)
    return bool((r.stdout or "").strip())


def measure(path):
    """Integrated loudness and true peak of whatever is at `path`.

    Returns `None` rather than raising when the file carries no audio at all,
    because "silent" is a legitimate thing to report about a draft.
    """
    if not has_audio(path):
        return None
    r = subprocess.run([need("ffmpeg"), "-hide_banner", "-nostats", "-i", path,
                        "-af", "ebur128=peak=true:framelog=quiet",
                        "-f", "null", "-"], capture_output=True, text=True)
    err = r.stderr or ""
    m = re.search(r"I:\s*(-?[\d.]+)\s*LUFS", err)
    if not m:
        return None
    out = {"lufs": float(m.group(1))}
    peaks = re.findall(r"Peak:\s*(-?[\d.]+)\s*dBFS", err)
    if peaks:
        out["true_peak_dbfs"] = float(peaks[-1])
    rng = re.search(r"LRA:\s*(-?[\d.]+)\s*LU", err)
    if rng:
        out["lra_lu"] = float(rng.group(1))
    return out


def bed_filter(total, bed_dur):
    """Loop, trim, fade and level the bed so it fits the film exactly.

    The loop count is derived from the two durations instead of being a large
    constant: `aloop` with a huge count on a long bed makes ffmpeg allocate the
    whole looped buffer, and on a 40-minute film that is measured in gigabytes.
    """
    loops = max(0, math.ceil(total / max(bed_dur, 0.1)) - 1)
    parts = []
    if loops:
        parts.append("aloop=loop=%d:size=%d" % (loops, int(bed_dur * 48000) + 1))
    parts += [
        "atrim=0:%.3f" % total,
        "asetpts=N/SR/TB",
        "loudnorm=I=%.1f:TP=-2.0:LRA=11" % BED_LUFS,
        "afade=t=in:st=0:d=%.2f" % FADE,
        "afade=t=out:st=%.3f:d=%.2f" % (max(0.0, total - FADE), FADE),
    ]
    return ",".join(parts)


def build(film, bed, out, total, report_path):
    ff = need("ffmpeg")
    pre = measure(film)

    if bed:
        bd = duration(bed)
        chain = (
            "[0:a]aformat=sample_rates=48000:channel_layouts=stereo,"
            "asplit=2[vo][key];"
            "[1:a]aformat=sample_rates=48000:channel_layouts=stereo,%s[bed];"
            "[bed][key]sidechaincompress=threshold=%.3f:ratio=%d:attack=%d:"
            "release=%d:makeup=1[duck];"
            "[vo][duck]amix=inputs=2:duration=first:dropout_transition=0:"
            "normalize=0[mix]"
            % (bed_filter(total, bd), DUCK_THRESHOLD, DUCK_RATIO,
               DUCK_ATTACK_MS, DUCK_RELEASE_MS)
        )
        cmd = [ff, "-y", "-i", film, "-i", bed, "-filter_complex", chain,
               "-map", "0:v", "-map", "[mix]", "-c:v", "copy",
               "-c:a", "aac", "-b:a", "192k", "-shortest", out]
    else:
        # No bed is a legitimate outcome, but the stage still owns the file, so
        # it re-emits rather than leaving the caller to guess which path is the
        # mixed one.
        cmd = [ff, "-y", "-i", film, "-c", "copy", out]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        die("ffmpeg failed:\n%s" % (r.stderr or "")[-1500:])

    post = measure(out)
    rep = {
        "film": os.path.basename(film),
        "output": os.path.basename(out),
        "duration_s": round(duration(out), 3),
        "bed": os.path.basename(bed) if bed else None,
        "bed_target_lufs": BED_LUFS if bed else None,
        "ducking": ({"ratio": DUCK_RATIO, "threshold": DUCK_THRESHOLD,
                     "attack_ms": DUCK_ATTACK_MS,
                     "release_ms": DUCK_RELEASE_MS} if bed else None),
        "loudness_before": pre,
        "loudness_after": post,
    }
    if report_path:
        os.makedirs(os.path.dirname(os.path.abspath(report_path)) or ".",
                    exist_ok=True)
        with open(report_path, "w") as fh:
            json.dump(rep, fh, indent=2)
    return rep


def carry_timeline(film, out):
    """Copy the render's timeline sidecar alongside the mixed film.

    The mix renames the film -- `cooper.mp4` becomes `cooper.mixed.mp4` -- but
    every downstream stage looks for a timeline *beside the film it was handed*.
    Without this the captioner and the story editor are pointed at the mixed cut
    and find nothing, so they fall back to re-deriving timings from the
    storyboard and drift out of sync with the film that actually shipped.

    Copying is honest here because the mix changes levels, not time: no line
    moves, and the duration is preserved to the frame. If it ever did retime,
    this would have to re-derive rather than copy.
    """
    src = os.path.splitext(film)[0] + ".timeline.json"
    dst = os.path.splitext(out)[0] + ".timeline.json"
    if os.path.abspath(src) == os.path.abspath(dst):
        return None
    if not os.path.exists(src):
        print("mix: WARNING -- no timeline beside %s. Captions will fall back "
              "to re-deriving timings from the storyboard and may drift from "
              "the cut that shipped. Re-render to publish one."
              % os.path.basename(film), file=sys.stderr)
        return None
    shutil.copyfile(src, dst)
    return dst


def main():
    ap = argparse.ArgumentParser(
        description="Mix a music bed under a finished film and measure it.")
    ap.add_argument("film")
    ap.add_argument("-o", "--out", help="mixed film (default: alongside, "
                                        "suffixed .mixed.mp4)")
    ap.add_argument("--bed", help="music bed; looped and ducked to fit")
    ap.add_argument("--report", help="write mix_report.json here")
    a = ap.parse_args()

    if not os.path.exists(a.film):
        die("no such film: %s" % a.film)
    if a.bed and not os.path.exists(a.bed):
        die("no such music bed: %s" % a.bed)
    if not has_audio(a.film):
        die("%s has no audio track. Mix runs after the film is rendered with "
            "its narration, not before." % os.path.basename(a.film))

    out = a.out or (os.path.splitext(a.film)[0] + ".mixed.mp4")
    if os.path.abspath(out) == os.path.abspath(a.film):
        die("refusing to overwrite the rendered film in place -- the mix is a "
            "new artifact, and the render must stay re-checkable")

    total = duration(a.film)
    rep = build(a.film, a.bed, out, total, a.report)
    tl = carry_timeline(a.film, out)

    print("mix: %s -> %s  (%.1fs)" % (os.path.basename(a.film),
                                      os.path.basename(out),
                                      rep["duration_s"]))
    if tl:
        print("  carried timeline -> %s" % os.path.basename(tl))
    if rep["bed"]:
        print("  bed %s ducked %d:1 under narration" % (rep["bed"],
                                                        DUCK_RATIO))
    else:
        print("  no music bed -- narration only")
    after = rep["loudness_after"]
    if after:
        line = "  loudness %.1f LUFS" % after["lufs"]
        if "true_peak_dbfs" in after:
            line += ", true peak %.1f dBFS" % after["true_peak_dbfs"]
        print(line)
        if after.get("true_peak_dbfs", -99) > -1.0:
            print("mix: WARNING -- true peak %.1f dBFS will clip on lossy "
                  "transcode. Lower the bed or re-master the voice."
                  % after["true_peak_dbfs"], file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
