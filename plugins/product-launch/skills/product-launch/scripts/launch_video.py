#!/usr/bin/env python3
"""product-launch — turn a product demo recording into a polished launch video.

Cross-platform engine: ffmpeg + Python (Pillow + numpy).

  python3 launch_video.py --config config.json --contact-sheet   # review footage
  python3 launch_video.py --config config.json                   # render the video
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ffmpeg_utils
import probe as probe_mod


DEFAULTS = {
    "output": None, "fps": 30, "resolution": [1920, 1080], "fit": "height",
    "personality": "playful", "transitions": "wipe", "logo_bug": True, "sfx": True,
    "segments": [], "captions": [],
    "brand": {"name": "Product", "tagline": "", "primary": "#5B8DEF",
              "bg_gradient": ["#14172B", "#1E2348", "#101326"], "logo": None},
    "intro": {"enabled": True, "duration": 2.8, "title": "{brand.name}", "subtitle": "{brand.tagline}"},
    "outro": {"enabled": True, "headline": "", "cta_text": None, "link": None,
              "footnote": None, "duration": 6.0, "end_card": True},
    "music": {"enabled": True, "vibe": "modern-playful", "bpm": 120, "gain": 0.9},
    "font": None, "font_bold": None,
}


def merge(base, override):
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path):
    with open(path) as f:
        cfg = json.load(f)
    return merge(DEFAULTS, cfg)


def timeline(cfg, in_dur):
    segs = cfg.get("segments") or []
    if not segs:
        ranges = [(0.0, in_dur)]
    else:
        ranges = []
        for s in segs:
            a, b = float(s["start"]), float(s["end"])
            a, b = max(0.0, a), min(in_dur, b)
            if b > a:
                ranges.append((a, b))
        if not ranges:
            ranges = [(0.0, in_dur)]
    intro = float(cfg["intro"]["duration"]) if cfg["intro"].get("enabled", True) else 0.0
    outro = float(cfg["outro"]["duration"]) if cfg["outro"].get("enabled", True) else 0.0
    lengths = [e - s for s, e in ranges]
    demo_start = intro
    demo_end = intro + sum(lengths)
    joins = [intro + sum(lengths[:i]) for i in range(1, len(ranges))]
    total = demo_end + outro
    endcard_at = None
    if outro > 0 and cfg["outro"].get("end_card", True) and outro > 4:
        tx_msg = demo_end + min(3.0, outro * 0.5)
        endcard_at = tx_msg + 0.35
    return {
        "ranges": ranges, "intro_dur": intro, "outro_dur": outro,
        "demo_start": demo_start, "demo_end": demo_end, "outro_start": demo_end,
        "joins": joins, "total": total, "endcard_at": endcard_at,
    }


def build_base(ffmpeg, cfg, tl, input_path, base_path):
    W, H = cfg["resolution"]
    bg = "0x" + (cfg["brand"].get("bg_gradient") or ["#101326"])[0].lstrip("#")
    graph = ffmpeg_utils.base_filter(tl["ranges"], cfg["fit"], W, H, cfg["fps"],
                                     tl["intro_dur"], tl["outro_dur"], bg)
    cmd = [ffmpeg, "-y", "-i", input_path, "-filter_complex", graph,
           "-map", "[outv]", "-an", "-r", str(cfg["fps"]),
           "-c:v", "libx264", "-crf", "14", "-preset", "veryfast", base_path]
    r = ffmpeg_utils.run(cmd)
    if r.returncode != 0 or not os.path.exists(base_path):
        raise RuntimeError("Base build failed:\n" + r.stderr[-1500:])


def composite(ffmpeg, cfg, tl, base_path, audio_path, out_path, scene):
    W, H = cfg["resolution"]
    fps = cfg["fps"]
    frames = int(round(tl["total"] * fps)) + 2
    inputs = ["-i", base_path,
              "-f", "rawvideo", "-pixel_format", "rgba", "-video_size", f"{W}x{H}",
              "-framerate", str(fps), "-i", "pipe:0"]
    maps = ["-map", "[v]"]
    afilter = ""
    if audio_path:
        inputs += ["-i", audio_path]
        maps += ["-map", "2:a", "-c:a", "aac", "-b:a", "192k"]
    cmd = [ffmpeg, "-y", *inputs,
           "-filter_complex", "[0:v][1:v]overlay=0:0:format=auto:eof_action=pass[v]",
           *maps, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
           "-preset", "medium", "-movflags", "+faststart", "-shortest", out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE)
    step = max(1, frames // 10)
    try:
        for i in range(frames):
            proc.stdin.write(scene.render_frame(i / fps).tobytes())
            if i % step == 0:
                print(f"  overlay {int(100*i/frames):3d}%", end="\r", flush=True)
    except BrokenPipeError:
        pass
    try:
        proc.stdin.close()
    except Exception:
        pass
    err = proc.stderr.read().decode(errors="ignore")
    proc.wait()
    print("  overlay 100%      ")
    if proc.returncode != 0 or not os.path.exists(out_path):
        raise RuntimeError("Composite failed:\n" + err[-1800:])


def main():
    ap = argparse.ArgumentParser(description="Create a product launch video from a demo recording.")
    ap.add_argument("--config", required=True)
    ap.add_argument("--input")
    ap.add_argument("--output")
    ap.add_argument("--ffmpeg")
    ap.add_argument("--fps", type=int)
    ap.add_argument("--contact-sheet", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.input:
        cfg["input"] = args.input
    if args.fps:
        cfg["fps"] = args.fps
    if not cfg.get("input"):
        sys.exit("config.input (or --input) is required: path to the demo recording.")
    in_path = os.path.expanduser(cfg["input"])
    if not os.path.exists(in_path):
        sys.exit(f"Input not found: {in_path}")

    out_path = args.output or cfg.get("output") or (os.path.splitext(in_path)[0] + "_launch.mp4")
    cfg["output"] = out_path

    ffmpeg, ffprobe = ffmpeg_utils.find_tools(args.ffmpeg)
    meta = ffmpeg_utils.probe(ffprobe, in_path)
    print(f"Input: {meta['width']}x{meta['height']} @ {meta['fps']:.1f}fps, "
          f"{meta['duration']:.2f}s, audio={meta['has_audio']}")

    if args.contact_sheet:
        sheet = os.path.splitext(out_path)[0] + "_contact_sheet.png"
        probe_mod.contact_sheet(ffmpeg, in_path, sheet, meta["duration"])
        print(f"Contact sheet -> {sheet}")
        print("Review it to choose `segments` (source seconds to keep) and caption "
              "timings (OUTPUT seconds after assembly).")
        return

    tl = timeline(cfg, meta["duration"])
    print(f"Timeline: intro {tl['intro_dur']:.1f}s + demo {tl['demo_end']-tl['demo_start']:.1f}s "
          f"+ outro {tl['outro_dur']:.1f}s = {tl['total']:.1f}s "
          f"({len(tl['ranges'])} segment(s), {len(tl['joins'])} join(s))")

    if args.dry_run:
        W, H = cfg["resolution"]
        bg = "0x" + (cfg["brand"].get("bg_gradient") or ["#101326"])[0].lstrip("#")
        print("\n[dry-run] base filter_complex:\n",
              ffmpeg_utils.base_filter(tl["ranges"], cfg["fit"], W, H, cfg["fps"],
                                       tl["intro_dur"], tl["outro_dur"], bg))
        print(f"\n[dry-run] would render {int(round(tl['total']*cfg['fps']))} overlay frames "
              f"at {W}x{H} and mux audio -> {out_path}")
        return

    # heavy deps only needed for a real render
    import assets
    import audio as audio_mod

    with tempfile.TemporaryDirectory() as td:
        base = os.path.join(td, "base.mp4")
        print("Building base (trim/assemble/scale)…")
        build_base(ffmpeg, cfg, tl, in_path, base)

        wav = None
        if cfg["music"].get("enabled", True) or cfg.get("sfx", True):
            print("Synthesizing audio…")
            wav = os.path.join(td, "audio.wav")
            audio_mod.render_audio(cfg, tl, wav)

        print("Rendering motion-graphics overlay + compositing…")
        scene = assets.Scene(cfg, tl)
        composite(ffmpeg, cfg, tl, base, wav, out_path, scene)

    print(f"\nDONE -> {out_path}")
    print("Verify it (and optionally run --contact-sheet on the OUTPUT) before sharing.")


if __name__ == "__main__":
    main()
