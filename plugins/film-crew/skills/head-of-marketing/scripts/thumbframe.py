"""Pick the thumbnail frame that actually shows the speaker.

Why this exists
---------------
The thumbnail frame used to be the midpoint of the clip. A midpoint is an
arbitrary instant, and a legislature broadcast spends a great deal of its time
not looking at a face: wide shots of a half-empty chamber, the Chair's desk,
graphics, slates between items, and the dissolve in and out of each of those.
Published episodes came back with no person in the picture at all -- and
because ``thumbnail._place_block`` positions the headline against a detected
face, a frame with no face also lost the lower-third and left the text
stranded mid-picture. One bad frame choice produced both complaints.

So the frame is chosen rather than assumed. Candidates are sampled across the
clip and scored on whether a human face is present, large, sharp and properly
exposed, and the best one wins. The scan is deliberately cheap -- small
greyscale-ish stills, a handful per clip -- because this runs per item on a
live session where minutes matter.

Usage
-----
    python3 thumbframe.py VIDEO --start 1234 --end 1290 --out frame.jpg
    python3 thumbframe.py VIDEO --start 1234 --end 1290 --out frame.jpg --json

Exits non-zero only if no frame could be extracted at all; a clip that
genuinely never shows a face still yields its best available frame, flagged
``"face": false`` in the JSON so the caller can decide.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

SAMPLES = 9          # stills per clip; 9 across ~60 s is one every ~7 s
SCAN_W = 640         # scoring width -- face detection does not need more
MIN_FACE_FRAC = 0.045   # face height as a fraction of frame height


def _say(m):
    print(f"[thumbframe] {m}", flush=True)


def grab(video, when, path, width=None):
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-ss", f"{when:.2f}", "-i", video, "-frames:v", "1"]
    if width:
        cmd += ["-vf", f"scale={width}:-2"]
    cmd += [path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0 and os.path.exists(path) \
        and os.path.getsize(path) > 0


def _faces(img):
    """Face boxes with detector confidence, best effort.

    Mirrors thumbnail._face_boxes so the frame that scores well here is the
    same frame that module can position a headline against -- picking a frame
    with a face the other detector cannot see would reintroduce the bug.
    """
    import numpy as np
    arr = np.asarray(img.convert("RGB"))
    try:
        from insightface.app import FaceAnalysis
        global _FA
        try:
            app = _FA
        except NameError:
            app = None
        if app is None:
            app = FaceAnalysis(name="buffalo_l",
                               allowed_modules=["detection"],
                               providers=["CPUExecutionProvider"])
            app.prepare(ctx_id=-1, det_size=(640, 640))
            _FA = app
        return [(tuple(int(v) for v in f.bbox), float(f.det_score))
                for f in app.get(arr[:, :, ::-1])]
    except Exception:
        pass
    try:
        import cv2
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        grey = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        found = cascade.detectMultiScale(grey, 1.1, 5, minSize=(48, 48))
        return [((int(x), int(y), int(x + w), int(y + h)), 0.6)
                for x, y, w, h in found]
    except Exception:
        return []


def _sharpness(img):
    """Variance of a Laplacian, normalised. Low means blur or a dissolve."""
    import numpy as np
    g = np.asarray(img.convert("L"), dtype="float32")
    lap = (g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:]
           - 4.0 * g[1:-1, 1:-1])
    return float(lap.var())


def _exposure(img):
    """1.0 for a well-spread histogram, falling towards flat or crushed.

    This is what rejects slates and fades: a title card is a couple of flat
    colours and a fade-to-black has almost no spread at all, and both score
    far below any real shot of a room.
    """
    import numpy as np
    g = np.asarray(img.convert("L"), dtype="float32") / 255.0
    spread = float(g.std())
    mean = float(g.mean())
    if mean < 0.06 or mean > 0.94:      # black frame or blown white
        return 0.0
    return min(spread / 0.22, 1.0)


def score(img):
    """How good this frame is as a thumbnail, and why."""
    faces = _faces(img)
    exposure = _exposure(img)
    sharp = _sharpness(img)
    sharp_n = min(sharp / 220.0, 1.0)

    big = 0.0
    conf = 0.0
    if faces:
        (x0, y0, x1, y1), det = max(
            faces, key=lambda fb: (fb[0][3] - fb[0][1]) * (fb[0][2] - fb[0][0]))
        big = (y1 - y0) / float(img.height)
        conf = det

    # A face is the single thing that makes a thumbnail work, so it carries
    # most of the weight; sharpness and exposure mainly exist to reject the
    # dissolves and slates that a face detector sometimes half-believes in.
    face_term = 0.0
    if big >= MIN_FACE_FRAC:
        face_term = min(big / 0.34, 1.0) * min(conf / 0.62, 1.0)
    total = face_term * 0.68 + sharp_n * 0.17 + exposure * 0.15
    return {"score": round(total, 4), "face": big >= MIN_FACE_FRAC,
            "face_frac": round(big, 4), "det": round(conf, 3),
            "sharp": round(sharp_n, 3), "exposure": round(exposure, 3)}


def pick(video, start, end, out, samples=SAMPLES):
    from PIL import Image
    start, end = float(start), float(end)
    span = max(end - start, 0.5)
    # Skip the first and last tenth: cuts, dissolves and the tail of the
    # previous shot live at the edges of a clip.
    lo, hi = start + span * 0.10, end - span * 0.10
    step = (hi - lo) / max(samples - 1, 1)

    tmp = tempfile.mkdtemp(prefix="thumbframe-")
    best, best_at, results = None, None, []
    try:
        for i in range(samples):
            at = lo + step * i
            p = os.path.join(tmp, f"s{i:02d}.jpg")
            if not grab(video, at, p, width=SCAN_W):
                continue
            try:
                s = score(Image.open(p))
            except Exception as e:
                _say(f"scoring failed at {at:.1f}s ({str(e)[:40]})")
                continue
            s["at"] = round(at, 2)
            results.append(s)
            if best is None or s["score"] > best["score"]:
                best, best_at = s, at
    finally:
        for f in os.listdir(tmp):
            try:
                os.unlink(os.path.join(tmp, f))
            except OSError:
                pass
        os.rmdir(tmp)

    if best is None:
        return None
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    if not grab(video, best_at, out):
        return None
    faces = sum(1 for r in results if r["face"])
    _say(f"{len(results)} sampled, {faces} with a face; "
         f"chose {best_at:.1f}s (score {best['score']}, "
         f"face {best['face_frac']:.2f})")
    best["out"] = out
    best["candidates"] = len(results)
    best["with_face"] = faces
    return best


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video")
    ap.add_argument("--start", type=float, required=True)
    ap.add_argument("--end", type=float, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--samples", type=int, default=SAMPLES)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if not os.path.exists(a.video):
        raise SystemExit(f"no such video: {a.video}")
    got = pick(a.video, a.start, a.end, a.out, a.samples)
    if not got:
        raise SystemExit("could not extract any frame")
    if a.json:
        print(json.dumps(got, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
