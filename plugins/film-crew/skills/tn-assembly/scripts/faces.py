#!/usr/bin/env python3
"""
Locates a configured public figure across the full session using face recognition.

The assembly feed cuts to a medium close-up of whoever is speaking, so a face
match with a reasonably large bounding box is a strong signal that the person
is on camera and holding the floor.

Frames are pulled straight from ffmpeg as raw BGR over a pipe -- decoding 8
hours to JPEG on disk would cost far more time and space than the detection
itself.

  --probe   verify the reference face is detected and embeddable
  --scan    sweep the session, writing meta/vip_hits.json
"""
import argparse
import os
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import Project, atomic_write_json  # noqa: E402

# Set by configure() from the project. The VIP is never named in code -- who
# matters changes with the story, and hardcoding a person makes the skill
# useless for the next one.
PR = None
VIDEO = REF = WORK = HITS = None

VW, VH = 640, 360
STEP = 3.0          # seconds between sampled frames; a speaker holds the floor
                    # far longer than this, so 3s loses nothing
MIN_FACE = 42       # px wide; below this ArcFace has too little detail to trust
TOTAL_FRAMES = 0


def configure(project):
    global PR, VIDEO, REF, WORK, HITS, STEP, MIN_FACE, TOTAL_FRAMES
    PR = Project(project)
    VIDEO = PR.scan_video
    WORK = PR.p("work")
    HITS = PR.p("meta", "vip_hits.json")
    os.makedirs(WORK, exist_ok=True)

    refs = PR.get("vip", "ref_images", default=[])
    if not refs:
        raise SystemExit(
            "vip.ref_images is empty in project.json. Add at least one clear, "
            "front-facing reference photo of the person to detect.")
    REF = PR.p(refs[0])
    if not os.path.exists(REF):
        raise SystemExit(f"missing reference image {REF}")

    STEP = PR.get("vip", "step", default=STEP)
    MIN_FACE = PR.get("vip", "min_face", default=MIN_FACE)
    dur = PR.get("source", "duration", default=0) or 0
    TOTAL_FRAMES = int(dur / STEP) if dur else 0
    return PR


def say(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def analyser():
    """Detector and recogniser loaded separately.

    FaceAnalysis.get() runs the recognition model on every detected face, and a
    wide chamber shot contains 20-30 of them -- so ~30 ArcFace passes per frame
    for faces far too small to identify. Splitting the two lets us detect
    cheaply and embed only the close-ups, which is where the answer lives.
    """
    from insightface.model_zoo import get_model
    root = os.path.expanduser("~/.insightface/models/buffalo_l")
    det = get_model(os.path.join(root, "det_10g.onnx"))
    det.prepare(ctx_id=-1, input_size=(512, 512))
    rec = get_model(os.path.join(root, "w600k_r50.onnx"))
    rec.prepare(ctx_id=-1)
    return det, rec


def faces_in(det, rec, img, min_face=None):
    """Detect, keep only sufficiently large faces, then embed just those."""
    from insightface.app.common import Face
    min_face = MIN_FACE if min_face is None else min_face
    bboxes, kpss = det.detect(img, max_num=0, metric="default")
    out = []
    for i in range(bboxes.shape[0]):
        b = bboxes[i]
        if (b[2] - b[0]) < min_face:
            continue
        f = Face(bbox=b[0:4], kps=kpss[i] if kpss is not None else None,
                 det_score=b[4])
        rec.get(img, f)
        out.append(f)
    return out


def norm(v):
    n = np.linalg.norm(v)
    return v / n if n else v


def ref_embedding(det, rec):
    import cv2
    img = cv2.imread(REF, cv2.IMREAD_COLOR)
    if img is None:
        raise SystemExit(f"cannot read {REF}")
    # the reference is a small thumbnail crop; upscale so the detector has
    # enough pixels to work with
    if max(img.shape[:2]) < 640:
        f = 640 / max(img.shape[:2])
        img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
    faces = faces_in(det, rec, img, min_face=40)
    if not faces:
        raise SystemExit("no face found in the reference image")
    faces.sort(key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]),
               reverse=True)
    f = faces[0]
    say(f"reference: {len(faces)} face(s), using bbox "
        f"{[int(x) for x in f.bbox]}, det_score {f.det_score:.3f}")
    return norm(f.embedding)


def frames(step=STEP):
    """Yield (timestamp, bgr_frame) sampled every `step` seconds."""
    cmd = ["ffmpeg", "-v", "error", "-i", VIDEO,
           "-vf", f"fps=1/{step},scale={VW}:{VH}",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=10 ** 8)
    size = VW * VH * 3
    i = 0
    try:
        while True:
            buf = p.stdout.read(size)
            if len(buf) < size:
                break
            yield i * step, np.frombuffer(buf, np.uint8).reshape(VH, VW, 3)
            i += 1
    finally:
        try:
            p.stdout.close()
            p.terminate()
        except Exception:
            pass


def probe():
    det, rec = analyser()
    e = ref_embedding(det, rec)
    say(f"embedding dim {e.shape[0]}, norm {np.linalg.norm(e):.3f}")
    n = 0
    for ts, fr in frames(step=60.0):
        fs = faces_in(det, rec, fr)
        if fs:
            best = max(float(np.dot(norm(f.embedding), e)) for f in fs)
            big = max((f.bbox[2] - f.bbox[0]) for f in fs)
            say(f"t={ts:7.0f}s closeups={len(fs)} bestsim={best:+.3f} "
                f"widest={big:.0f}px")
        n += 1
        if n >= 12:
            break


def scan():
    """Sweep the session, keeping only close-up faces.

    The wide chamber shot yields 20-30 faces of 24-50px, which ArcFace cannot
    discriminate. Restricting to faces >= MIN_FACE px both removes that noise
    and naturally selects the shots worth cutting -- the feed frames a speaker
    in medium close-up when they hold the floor.

    Every close-up embedding is kept so speakers can be clustered afterwards.
    A cluster centroid averages away per-frame noise, which matters because the
    only reference available is a small, heavily stylised thumbnail crop.
    """
    import cv2
    det, rec = analyser()
    ref = ref_embedding(det, rec)
    os.makedirs(WORK, exist_ok=True)
    crops = os.path.join(WORK, "vip_crops")
    os.makedirs(crops, exist_ok=True)

    out, embs = [], []
    t0 = time.time()
    n = kept = 0
    for ts, fr in frames():
        n += 1
        fs = faces_in(det, rec, fr)
        if fs:
            kept += 1
            for f in fs:
                e = norm(f.embedding)
                s = float(np.dot(e, ref))
                bb = f.bbox
                out.append({
                    "t": round(ts, 1),
                    "sim": round(s, 4),
                    "w": round(float(bb[2] - bb[0]), 1),
                    "det": round(float(f.det_score), 3),
                    "i": len(embs),
                })
                embs.append(e.astype(np.float16))
                if s >= 0.30:
                    x1, y1, x2, y2 = [int(v) for v in bb]
                    m = int((x2 - x1) * 0.45)
                    crop = fr[max(0, y1 - m):y2 + m, max(0, x1 - m):x2 + m]
                    if crop.size:
                        cv2.imwrite(os.path.join(
                            crops, f"{int(ts):06d}_{s:.3f}.jpg"), crop)
        if n % 500 == 0:
            el = time.time() - t0
            eta = (TOTAL_FRAMES - n) / max(n / el, 0.01) / 60
            say(f"{n}/{TOTAL_FRAMES} ({ts/3600:.2f}h) {el:.0f}s, "
                f"{n/max(el,1):.1f} fps, eta {eta:.0f}min, {kept} closeups, "
                f"best {max((o['sim'] for o in out), default=0):.3f}")
    embs_path = os.path.join(WORK, "vip_embs.npy")
    embs_tmp = f"{embs_path}.tmp.{os.getpid()}"
    try:
        with open(embs_tmp, "wb") as f:
            np.save(f, np.array(embs, np.float16))
        os.replace(embs_tmp, embs_path)
    finally:
        if os.path.exists(embs_tmp):
            os.remove(embs_tmp)
    atomic_write_json(HITS, {"step": STEP, "min_face": MIN_FACE,
                             "sampled": n, "video": VIDEO, "hits": out})
    say(f"wrote {HITS}: {len(out)} close-up faces from {n} sampled frames")


def main():
    ap = argparse.ArgumentParser(
        description="Detect a configured public figure in the session")
    ap.add_argument("project")
    ap.add_argument("--probe", action="store_true",
                    help="calibrate similarity against the reference")
    ap.add_argument("--scan", action="store_true",
                    help="sweep the session, writing meta/vip_hits.json")
    a = ap.parse_args()
    configure(a.project)
    if a.probe:
        probe()
    elif a.scan:
        scan()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
