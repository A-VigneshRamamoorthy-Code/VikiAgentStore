"""Find what is worth publishing in a long session, and tell fights apart from debate.

Assembly webcasts ship with no captions and no shot list, so the audio has to
carry the analysis. Two different questions are asked of it:

**"Is anything happening here?"** -- answered by loudness and its dynamics.
Flat, quiet stretches are figures being read into the record; sustained energy
with internal variation is an exchange.

**"Is this a fight?"** -- loudness alone cannot answer this, because a minister
delivering a forceful speech is loud too. What separates an uproar from a
speech is *structure*:

  * **Silence collapses.** Orderly debate leaves gaps between speakers. When
    members shout over each other the gaps disappear.
  * **The spectrum flattens.** One voice is harmonic and peaky. Many
    simultaneous voices, desk-thumping and shouting approach broadband noise,
    which spectral flatness measures directly.
  * **Onsets crowd together.** Interruptions produce far more energy onsets per
    second than turn-taking does.
  * **It escalates.** Rows build, so loudness trends upward across the window.

Each signal is weak alone -- applause and laughter also flatten the spectrum
and fill the silence -- so a clash must satisfy several at once, and the label
is always a *candidate* for ASR or human confirmation, never a fact. See
`reference/clash-detection.md` for calibration and the honesty rule.

Outputs `meta/features.json` (per-second) and `meta/candidates.json`.
"""
import argparse
import math
import os
import subprocess

import numpy as np

from config import Project, hhmmss, say

SR = 16000
FRAME = 512           # 32 ms
HOP = 256             # 16 ms
CHUNK_SEC = 120


def _stream(path):
    """Decode to 16 kHz mono PCM and yield it a chunk at a time.

    A full session at this rate is well over a gigabyte as float32, so it is
    never materialised; features reduce to one row per second on the fly.
    """
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR),
           "-f", "s16le", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL)
    want = CHUNK_SEC * SR * 2
    carry = b""
    try:
        while True:
            buf = proc.stdout.read(want)
            if not buf:
                break
            data = carry + buf
            usable = (len(data) // 2) * 2
            carry = data[usable:]
            yield np.frombuffer(data[:usable], np.int16).astype(np.float32) / 32768.0
    finally:
        proc.stdout.close()
        proc.wait()


def _frames(x):
    n = 1 + max(0, (len(x) - FRAME) // HOP)
    if n <= 0:
        return np.zeros((0, FRAME), np.float32)
    idx = np.arange(FRAME)[None, :] + HOP * np.arange(n)[:, None]
    return x[idx] * np.hanning(FRAME).astype(np.float32)[None, :]


def features(path):
    """Per-second acoustic features for the whole session."""
    per_sec = int(round(SR / HOP))
    rows = []
    prev_mag = None
    tail = np.zeros(0, np.float32)

    for chunk in _stream(path):
        x = np.concatenate([tail, chunk])
        fr = _frames(x)
        if len(fr) == 0:
            tail = x
            continue
        used = HOP * (len(fr) - 1) + FRAME
        tail = x[max(0, used - FRAME + HOP):]

        mag = np.abs(np.fft.rfft(fr, axis=1)).astype(np.float32) + 1e-10
        power = mag ** 2
        rms = np.sqrt(np.mean(fr ** 2, axis=1)) + 1e-10

        # Spectral flatness: geometric over arithmetic mean of the power
        # spectrum. Near 1.0 is broadband noise, near 0 a clean harmonic voice.
        flat = np.exp(np.mean(np.log(power), axis=1)) / np.mean(power, axis=1)

        if prev_mag is None:
            prev_mag = mag[0]
        ref = np.vstack([prev_mag[None, :], mag[:-1]])
        flux = np.mean(np.maximum(mag - ref, 0.0), axis=1)
        prev_mag = mag[-1]

        for s in range(len(fr) // per_sec):
            a, b = s * per_sec, (s + 1) * per_sec
            r = rms[a:b]
            rows.append({
                "db": round(float(20 * math.log10(max(float(np.mean(r)), 1e-9))), 3),
                "peak_db": round(float(20 * math.log10(max(float(np.max(r)), 1e-9))), 3),
                # The *floor* within the second is the silence-collapse signal:
                # turn-taking drops it into the room tone, people shouting over
                # each other never let it fall. An absolute RMS gate cannot do
                # this job -- it is entirely dependent on how hot the webcast
                # is mixed -- so the raw floor is kept and normalised later
                # against this session's own distribution.
                "min_db": round(float(20 * math.log10(max(float(np.min(r)), 1e-9))), 3),
                "flat": round(float(np.mean(flat[a:b])), 5),
                "flux": round(float(np.mean(flux[a:b])), 5),
            })
    return rows


def _norm(v, lo_pct=10, hi_pct=95):
    a = np.asarray(v, np.float32)
    lo, hi = np.percentile(a, lo_pct), np.percentile(a, hi_pct)
    return np.clip((a - lo) / max(1e-6, hi - lo), 0, 1)


def score_windows(rows, win=45, step=5):
    """Score every window for general interest and for clash separately."""
    n = len(rows)
    if n < win + 10:
        return []

    db = _norm([r["db"] for r in rows])
    flat = _norm([r["flat"] for r in rows])
    flux = _norm([r["flux"] for r in rows])
    # Silence collapse, normalised against this session's own noise floor.
    floor = _norm([r["min_db"] for r in rows])
    raw_db = np.asarray([r["db"] for r in rows], np.float32)

    ramp = np.arange(win, dtype=np.float32)
    ramp -= ramp.mean()
    ramp_norm = float(np.sum(ramp ** 2)) or 1.0

    out = []
    for s in range(0, n - win, step):
        e = s + win
        seg = raw_db[s:e]
        energy = float(np.mean(db[s:e]))
        peak = float(np.max(db[s:e]))
        dyn = float(np.std(seg)) / 12.0
        slope = float(np.sum(ramp * (seg - seg.mean())) / ramp_norm)

        highlight = 0.50 * energy + 0.28 * peak + 0.22 * min(dyn, 1.0)

        continuity = float(np.mean(floor[s:e]))
        clash = (0.30 * energy
                 + 0.26 * continuity
                 + 0.20 * float(np.mean(flat[s:e]))
                 + 0.16 * float(np.mean(flux[s:e]))
                 + 0.08 * min(max(slope * 6.0, 0.0), 1.0))

        out.append({
            "start": s, "end": e,
            "highlight": round(highlight, 4),
            "clash": round(clash, 4),
            "energy": round(energy, 4),
            "continuity": round(continuity, 4),
            "flatness": round(float(np.mean(flat[s:e])), 4),
            "onset": round(float(np.mean(flux[s:e])), 4),
            "slope": round(slope, 4),
            "mean_db": round(float(seg.mean()), 2),
        })
    return out


def pick(windows, top_n=40, guard=180):
    """Non-overlapping best windows, clash-labelled where signals agree.

    `guard` keeps picks apart so the shortlist spans the whole session instead
    of clustering inside a single long argument.

    Clash labelling is deliberately **outlier-based, not threshold-based**. A
    fixed cutoff either fires on every session or on none, because webcast
    mixes differ wildly. Instead a window must be both in the top slice of this
    session *and* a genuine statistical outlier -- at least `MAD_K` median
    absolute deviations above the session median. A calm session has no
    outliers and correctly yields no flags.
    """
    if not windows:
        return []

    cl = np.asarray([w["clash"] for w in windows])
    med = float(np.median(cl))
    mad = float(np.median(np.abs(cl - med))) or 1e-6
    MAD_K = 3.0
    clash_gate = max(float(np.percentile(cl, 93)), med + MAD_K * mad)
    cont_gate = float(np.percentile([w["continuity"] for w in windows], 85))
    flat_gate = float(np.percentile([w["flatness"] for w in windows], 80))

    ranked = sorted(windows, key=lambda w: max(w["highlight"], w["clash"]),
                    reverse=True)
    picked = []
    for w in ranked:
        if any(abs(w["start"] - p["start"]) < guard for p in picked):
            continue
        w = dict(w)
        w["clash_pct"] = round(float((cl < w["clash"]).mean() * 100), 1)
        w["clash_sigma"] = round((w["clash"] - med) / mad, 2)
        w["kind"] = "clash" if (w["clash"] >= clash_gate
                                and w["continuity"] >= cont_gate
                                and w["flatness"] >= flat_gate) else "speech"
        w["tc"] = hhmmss(w["start"])
        picked.append(w)
        if len(picked) >= top_n:
            break
    picked.sort(key=lambda w: w["start"])
    return picked


def main():
    ap = argparse.ArgumentParser(description="Highlight and clash detection")
    ap.add_argument("project")
    ap.add_argument("--window", type=int, default=45)
    ap.add_argument("--top", type=int, default=40)
    a = ap.parse_args()
    pr = Project(a.project)

    if not os.path.exists(pr.audio):
        raise SystemExit(f"missing {pr.audio}; run ingest.py first")

    say(f"analysing {pr.audio}")
    rows = features(pr.audio)
    say(f"{len(rows)} seconds of features")
    pr.save("features.json", rows)

    cands = pick(score_windows(rows, win=a.window), top_n=a.top)
    pr.save("candidates.json", cands)

    fights = [c for c in cands if c["kind"] == "clash"]
    say(f"{len(cands)} candidates, {len(fights)} flagged as clash")
    for c in cands:
        mark = "CLASH" if c["kind"] == "clash" else "     "
        say(f"  {c['tc']} {mark} hl={c['highlight']:.3f} cl={c['clash']:.3f} "
            f"cont={c['continuity']:.2f} flat={c['flatness']:.2f}")
    say("clash labels are CANDIDATES -- confirm by ASR or by eye before any "
        "title calls it a fight")


if __name__ == "__main__":
    main()
