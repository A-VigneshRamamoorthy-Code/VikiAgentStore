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
REFS = []
DISTRACTORS = []

VW, VH = 640, 360
STEP = 3.0          # seconds between sampled frames; a speaker holds the floor
                    # far longer than this, so 3s loses nothing
MIN_FACE = 42       # px wide; below this ArcFace has too little detail to trust
TOTAL_FRAMES = 0


def configure(project):
    global PR, VIDEO, REF, REFS, DISTRACTORS, WORK, HITS, STEP, MIN_FACE, TOTAL_FRAMES
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
    REFS = [PR.p(r) for r in refs]
    for r in REFS:
        if not os.path.exists(r):
            raise SystemExit(f"missing reference image {r}")
    REF = REFS[0]

    # Competing faces, and the reason they exist.
    #
    # With a single template every face in the chamber is scored against one
    # person, so the only question the scanner can answer is "how much does
    # this resemble him" -- never "does it resemble someone else more". In a
    # real sitting that is not enough. The presiding officer scored 0.794
    # against the VIP here: past every threshold in use, and wrong. He was
    # caught by cropping the frame and looking at it, which does not scale.
    #
    # Enrolling the faces that recur on camera but are not the subject gives
    # those hits somewhere correct to land, and turns a bare similarity into a
    # comparison. Distractors need no names -- an unnamed template is enough
    # to say "more like that man than like the VIP", which is the only claim
    # needed to suppress the hit.
    DISTRACTORS = [PR.p(d) for d in PR.get("vip", "distractor_images",
                                           default=[])]
    DISTRACTORS = [d for d in DISTRACTORS if os.path.exists(d)]

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


def ref_embedding(det, rec, path=None, label="reference"):
    import cv2
    src = path or REF
    img = cv2.imread(src, cv2.IMREAD_COLOR)
    if img is None:
        raise SystemExit(f"cannot read {src}")
    # the reference is a small thumbnail crop; upscale so the detector has
    # enough pixels to work with
    if max(img.shape[:2]) < 640:
        f = 640 / max(img.shape[:2])
        img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
    faces = faces_in(det, rec, img, min_face=40)
    if not faces:
        raise SystemExit(f"no face found in the reference image {src}")
    faces.sort(key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]),
               reverse=True)
    f = faces[0]
    say(f"{label}: {os.path.basename(src)}, {len(faces)} face(s), using bbox "
        f"{[int(x) for x in f.bbox]}, det_score {f.det_score:.3f}")
    return norm(f.embedding)


def template(det, rec, paths, label):
    """Average several photos of one person into a single template.

    One photo is a brittle template. The same face at a different head angle
    can lose to a competing person's average, which is how a distractor built
    from a single frame still let the wrong hit through here -- it only held
    up once two more poses of the same man were added.
    """
    vecs = [ref_embedding(det, rec, p, label) for p in paths]
    return norm(np.mean(vecs, axis=0)) if len(vecs) > 1 else vecs[0]


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
    # calibrate against the same template the sweep will use, or the numbers
    # reported here do not describe the run they are meant to calibrate
    e = template(det, rec, REFS, "reference")
    alts = [template(det, rec, [d], "distractor") for d in DISTRACTORS]
    say(f"embedding dim {e.shape[0]}, norm {np.linalg.norm(e):.3f}")
    n = 0
    for ts, fr in frames(step=60.0):
        fs = faces_in(det, rec, fr)
        if fs:
            best = max(float(np.dot(norm(f.embedding), e)) for f in fs)
            big = max((f.bbox[2] - f.bbox[0]) for f in fs)
            extra = ""
            if alts:
                alt = max(float(np.dot(norm(f.embedding), a))
                          for f in fs for a in alts)
                extra = f" alt={alt:+.3f} margin={best - alt:+.3f}"
            say(f"t={ts:7.0f}s closeups={len(fs)} bestsim={best:+.3f}{extra} "
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
    ref = template(det, rec, REFS, "reference")
    alts = [template(det, rec, [d], "distractor") for d in DISTRACTORS]
    if alts:
        say(f"{len(alts)} distractor template(s) loaded; a hit is suppressed "
            f"when one of them scores higher than the VIP")
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
                d = max((float(np.dot(e, a)) for a in alts), default=0.0)
                bb = f.bbox
                rec_ = {
                    "t": round(ts, 1),
                    "sim": round(s, 4),
                    "w": round(float(bb[2] - bb[0]), 1),
                    "det": round(float(f.det_score), 3),
                    "i": len(embs),
                }
                if alts:
                    # margin, not similarity, is what separates a real match
                    # from a confident-looking mistake
                    rec_["alt"] = round(d, 4)
                    rec_["margin"] = round(s - d, 4)
                out.append(rec_)
                embs.append(e.astype(np.float16))
                # a crop the VIP loses is a crop of somebody else, and saving
                # it only invites the reviewer to confirm the wrong face
                if s >= 0.30 and s > d:
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
