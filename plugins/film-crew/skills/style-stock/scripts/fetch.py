#!/usr/bin/env python3
"""Find and download the footage a stock storyboard asks for.

    python3 fetch.py storyboard.json                 # resolve every shot
    python3 fetch.py storyboard.json --dry-run       # search, download nothing
    python3 fetch.py storyboard.json --only s07 s08  # re-cut two shots
    python3 fetch.py storyboard.json --pool ./clips  # offline; no network

This is the only stage in the style that touches the network, and it is a
separate stage for three reasons that each cost something to learn:

* **It is metered.** Pexels allows 200 requests an hour. A film of forty shots
  with three fallback queries each can spend a sixth of that in one run, so
  every search is cached on disk and a re-compile does not re-search.
* **It is not deterministic.** The same query returns different clips next
  week. Once a film is cut, its footage must stop moving — so the *resolved*
  storyboard records clip ids, and re-running is a no-op unless asked.
* **It is where the licence is established.** Every clip that lands writes a
  credit. A film whose provenance is reconstructed afterwards is a film whose
  provenance is guessed.

Requires ``PEXELS_API_KEY``. Get one free and instantly at
https://www.pexels.com/api/ . There is no key-free path: the site's internal
API answers 401, its search HTML embeds no video URLs, and its robots.txt
disallows both. Do not go looking for one.
"""

import argparse
import concurrent.futures as futures
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

PEXELS_SEARCH = "https://api.pexels.com/v1/videos/search"
PEXELS_VIDEO = "https://api.pexels.com/videos/videos/"
PIXABAY_SEARCH = "https://pixabay.com/api/videos/"

UA = "film-crew-style-stock/1.0 (+https://github.com/A-VigneshRamamoorthy-Code/VikiAgentStore)"

#: Pause between search requests. 200/hour is one every 18 s if you were to
#: sustain it, which no film does -- but bursting forty searches in four
#: seconds is what gets a key rate-limited, so this is politeness rather than
#: arithmetic.
SEARCH_PAUSE = 0.35

#: Never download anything larger than this. Pexels serves 4K originals that
#: run to 90 MB for twenty seconds; forty of those is 3.5 GB to make a film
#: that is delivered at 1080p. Picking the smallest file that still exceeds
#: the target frame is not a compromise, it is the correct choice.
MAX_PIXELS = 2560 * 1440

#: A clip must beat the delivery frame in *both* dimensions or it is upscaled,
#: which on real footage looks like a smear rather than like softness.
#: Tolerance exists because 1920x1080 footage cropped to 16:9 is exactly equal,
#: not greater.
UPSCALE_SLACK = 0.98


def log(msg):
    print("stock/fetch: %s" % msg, file=sys.stderr)


def die(msg):
    log(msg)
    raise SystemExit(1)


# -------------------------------------------------------------------- keys --


def load_dotenv():
    """Read a .env from the tree above us, without overwriting real env vars.

    The key is a credential, so it lives in a gitignored .env rather than in
    the storyboard, the skill or anything else that gets committed. Walking up
    means the file can sit at the repository root and serve every project
    inside it.
    """
    seen = set()
    roots = []
    # Walk up from the working directory *and* from this skill, so a key at
    # the repository root serves the skill no matter where it is invoked
    # from. Only the cwd was walked before, which meant running the fetcher
    # against an absolute storyboard path from somewhere else on disk could
    # not see the very .env sitting above the script.
    for start in (os.getcwd(), HERE):
        here = os.path.abspath(start)
        while True:
            if here not in roots:
                roots.append(here)
            parent = os.path.dirname(here)
            if parent == here:
                break
            here = parent

    for root in roots:
        p = os.path.join(root, ".env")
        if p in seen or not os.path.isfile(p):
            continue
        seen.add(p)
        try:
            with open(p, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k and k not in os.environ:
                        os.environ[k] = v
        except OSError:
            continue


# ------------------------------------------------------------------ search --


class Searcher:
    """Pexels first, Pixabay as a fallback, both cached on disk.

    The cache is keyed by provider + query + orientation, and it is the reason
    a film can be re-compiled and re-fetched all afternoon on a 200/hour quota.
    """

    def __init__(self, cache_dir, orientation, dry_run=False):
        self.cache_dir = cache_dir
        self.orientation = orientation
        self.dry_run = dry_run
        self.calls = 0
        self.cached = 0
        self.remaining = None
        os.makedirs(cache_dir, exist_ok=True)
        self.pexels_key = os.environ.get("PEXELS_API_KEY", "").strip()
        self.pixabay_key = os.environ.get("PIXABAY_API_KEY", "").strip()

    def _cache_path(self, provider, query):
        h = hashlib.sha256(
            ("%s|%s|%s" % (provider, query, self.orientation)).encode("utf-8")
        ).hexdigest()[:16]
        return os.path.join(self.cache_dir, "%s-%s.json" % (provider, h))

    def _get(self, url, headers):
        req = urllib.request.Request(url, headers=dict(headers, **{"User-Agent": UA}))
        with urllib.request.urlopen(req, timeout=45) as r:
            body = r.read().decode("utf-8")
            rem = r.headers.get("X-Ratelimit-Remaining")
            if rem is not None:
                self.remaining = rem
            return json.loads(body)

    def search(self, query):
        """Every candidate clip for a query, best-first, as normalised dicts."""
        if not query.strip():
            return []
        out = self._provider("pexels", query)
        if not out:
            out = self._provider("pixabay", query)
        return out

    def _provider(self, provider, query):
        cache = self._cache_path(provider, query)
        if os.path.isfile(cache):
            try:
                with open(cache, encoding="utf-8") as fh:
                    self.cached += 1
                    return json.load(fh)
            except (OSError, ValueError):
                pass

        if self.dry_run:
            return []

        if provider == "pexels":
            if not self.pexels_key:
                return []
            url = PEXELS_SEARCH + "?" + urllib.parse.urlencode({
                "query": query, "orientation": self.orientation,
                "per_page": 15, "page": 1,
            })
            headers = {"Authorization": self.pexels_key}
        else:
            if not self.pixabay_key:
                return []
            url = PIXABAY_SEARCH + "?" + urllib.parse.urlencode({
                "key": self.pixabay_key, "q": query,
                "video_type": "film", "per_page": 20,
            })
            headers = {}

        try:
            time.sleep(SEARCH_PAUSE)
            self.calls += 1
            data = self._get(url, headers)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                die("%s rate-limited (HTTP 429). Searches already made are "
                    "cached, so waiting an hour and re-running resumes where "
                    "this stopped." % provider)
            if e.code in (401, 403):
                die("%s rejected the key (HTTP %d). Check %s_API_KEY."
                    % (provider, e.code, provider.upper()))
            log("%s: HTTP %d for %r" % (provider, e.code, query))
            return []
        except (urllib.error.URLError, ValueError, TimeoutError) as e:
            log("%s: %s for %r" % (provider, e, query))
            return []

        rows = (_norm_pexels(data) if provider == "pexels"
                else _norm_pixabay(data))
        try:
            with open(cache, "w", encoding="utf-8") as fh:
                json.dump(rows, fh)
        except OSError:
            pass
        return rows


    def by_id(self, source, clip_id):
        """Fresh metadata for a clip already chosen, by its id.

        The download URL is deliberately not kept in the storyboard because it
        is a signed Vimeo link that expires within the hour. That makes the
        storyboard a lockfile rather than a manifest: it pins *which* clip, and
        the URL has to be asked for again. This is what lets the committed
        example be reproduced without redistributing a single byte of footage.
        """
        if source == "pexels":
            if not self.pexels_key:
                return None
            url = PEXELS_VIDEO + str(clip_id)
            headers = {"Authorization": self.pexels_key}
        elif source == "pixabay":
            if not self.pixabay_key:
                return None
            url = PIXABAY_SEARCH + "?" + urllib.parse.urlencode(
                {"key": self.pixabay_key, "id": str(clip_id)})
            headers = {}
        else:
            return None

        try:
            time.sleep(SEARCH_PAUSE)
            self.calls += 1
            data = self._get(url, headers)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                die("%s rejected the key (HTTP %d)." % (source, e.code))
            log("%s: HTTP %d restoring clip %s" % (source, e.code, clip_id))
            return None
        except (urllib.error.URLError, ValueError, TimeoutError) as e:
            log("%s: %s restoring clip %s" % (source, e, clip_id))
            return None

        rows = (_norm_pexels({"videos": [data]}) if source == "pexels"
                else _norm_pixabay(data))
        return rows[0] if rows else None


def _norm_pexels(data):
    out = []
    for v in (data or {}).get("videos") or []:
        files = []
        for f in v.get("video_files") or []:
            if f.get("file_type") != "video/mp4" or not f.get("link"):
                continue
            w, h = int(f.get("width") or 0), int(f.get("height") or 0)
            if w <= 0 or h <= 0:
                continue
            files.append({
                # `quality` is documented as 'hd' or 'sd'. In practice it is
                # very often null, and 'uhd' appears on 4K clips although it
                # is undocumented. So it is recorded and never relied on --
                # pixel count is the only field that always tells the truth.
                "quality": f.get("quality"),
                "width": w, "height": h,
                "fps": float(f.get("fps") or 0) or None,
                "url": f["link"],
            })
        if not files:
            continue
        out.append({
            "source": "pexels",
            "id": str(v.get("id")),
            "page": v.get("url"),
            "author": (v.get("user") or {}).get("name") or "unknown",
            "author_url": (v.get("user") or {}).get("url"),
            "duration": float(v.get("duration") or 0),
            "files": files,
        })
    return out


def _norm_pixabay(data):
    out = []
    for v in (data or {}).get("hits") or []:
        files = []
        for name in ("large", "medium", "small", "tiny"):
            f = (v.get("videos") or {}).get(name) or {}
            if not f.get("url"):
                continue
            w, h = int(f.get("width") or 0), int(f.get("height") or 0)
            if w <= 0 or h <= 0:
                continue
            files.append({"quality": name, "width": w, "height": h,
                          "fps": None, "url": f["url"]})
        if not files:
            continue
        out.append({
            "source": "pixabay",
            "id": str(v.get("id")),
            "page": v.get("pageURL"),
            "author": v.get("user") or "unknown",
            "author_url": ("https://pixabay.com/users/%s-%s/"
                           % (v.get("user"), v.get("user_id"))
                           if v.get("user_id") else None),
            "duration": float(v.get("duration") or 0),
            "files": files,
        })
    return out


# ------------------------------------------------------------------ choose --


def pick_file(cand, want_w, want_h):
    """The smallest file that still covers the delivery frame.

    Sorting by "best" means downloading 4K to deliver 1080p. Sorting by
    "smallest" means upscaling. The right answer is the smallest file that is
    still at or above the frame -- and, if nothing is, the largest available,
    with the shortfall reported rather than hidden.
    """
    ok = [f for f in cand["files"]
          if f["width"] >= want_w * UPSCALE_SLACK
          and f["height"] >= want_h * UPSCALE_SLACK
          and f["width"] * f["height"] <= MAX_PIXELS]
    if ok:
        return min(ok, key=lambda f: f["width"] * f["height"]), False
    ok = [f for f in cand["files"]
          if f["width"] >= want_w * UPSCALE_SLACK
          and f["height"] >= want_h * UPSCALE_SLACK]
    if ok:
        return min(ok, key=lambda f: f["width"] * f["height"]), False
    return max(cand["files"], key=lambda f: f["width"] * f["height"]), True


def score(cand, shot, want_w, want_h):
    """How well a candidate answers a shot. Higher is better."""
    s = 0.0
    best = max(cand["files"], key=lambda f: f["width"] * f["height"])

    if best["width"] >= want_w and best["height"] >= want_h:
        s += 40
    else:
        s -= 30

    # A clip must be long enough to hold the shot, with a little to spare so
    # the cut is not forced to land on the clip's own last frame -- where
    # stock footage very often fades, whip-pans or shows a watermark.
    need = float(shot.get("dur") or 0) * abs(float(shot.get("speed") or 1.0))
    have = float(cand.get("duration") or 0)
    if have >= need + 1.5:
        s += 30
    elif have >= need:
        s += 12
    else:
        s -= 18 * (need - have)

    # Prefer a clip whose shape is close to the delivery frame, because
    # cropping a 4:3 clip into 16:9 throws away a third of the picture and
    # whatever the videographer framed for is usually in the part discarded.
    want_ar = want_w / float(want_h)
    ar = best["width"] / float(best["height"])
    s -= min(20.0, abs(ar - want_ar) * 24.0)

    # A mild preference for clips that are not vastly longer than the shot.
    # This is bandwidth as much as taste -- a 68 s clip is downloaded whole to
    # use three seconds of it -- but it is also a quality signal, because a
    # clip four times longer than the cut is usually a long static drone shot
    # with one interesting second somewhere in the middle.
    if have > need * 4 and have > 25:
        s -= min(8.0, (have - need * 4) * 0.12)

    return s


def resolve(shot, searcher, used, want_w, want_h):
    """Find a clip for one shot, walking its fallback queries.

    Returns (clip, query_used, note). A shot that cannot be answered gets a
    clip of None -- never a substitute. That is the style contract's rule 2,
    and it is the whole reason this style can be trusted with a documentary:
    a film that shows the wrong building is making a false claim in pictures,
    and it does it silently.
    """
    queries = [shot.get("query") or ""] + list(shot.get("alternates") or [])
    tried = []
    for q in queries:
        q = (q or "").strip()
        if not q:
            continue
        tried.append(q)
        cands = searcher.search(q)
        if not cands:
            continue
        ranked = sorted(cands, key=lambda c: score(c, shot, want_w, want_h),
                        reverse=True)
        for c in ranked:
            key = "%s:%s" % (c["source"], c["id"])
            if key in used:
                continue
            f, upscaled = pick_file(c, want_w, want_h)
            need = float(shot.get("dur") or 0) * abs(float(shot.get("speed") or 1.0))
            clip = {
                "source": c["source"], "id": c["id"], "page": c["page"],
                "author": c["author"], "author_url": c.get("author_url"),
                "license": "Pexels" if c["source"] == "pexels" else "Pixabay",
                "url": f["url"], "width": f["width"], "height": f["height"],
                "fps": f["fps"], "quality": f.get("quality"),
                "duration": c.get("duration") or 0.0,
                "query": q,
                "upscaled": upscaled,
                "short": (c.get("duration") or 0.0) < need,
            }
            return clip, q, ("widened to %r" % q if q != queries[0] else None)
    return None, None, "no result for any of %s" % (tried or ["(no query)"])


# ---------------------------------------------------------------- download --


SYNTHETIC_THRESHOLD = 0.85


def looks_synthetic(path):
    """True if the clip is vector animation, a motion-graphics template, or a
    still image dressed up as a video.

    Stock libraries are full of these and one landing in a live-action film is
    the worst defect this style produces: on the validation film a flat cyan
    cartoon of a bank arrived among forty rainy night clips, right at the
    story's twist.

    The test is temporal. Two frames a second apart are compared and the
    fraction of *bit-identical* pixels is measured. A camera sensor never
    repeats itself -- grain, dither and compression noise guarantee that even
    a locked-off shot of a blank wall changes slightly. Rendered artwork
    repeats exactly.

    The threshold is not a guess. Measured across a real 44-shot film:

        cartoon (the known bad clip)   0.921
        tunnel lines, static           0.667   <- highest legitimate
        red alarm light                0.660
        film median                    0.112

    0.85 sits in the empty gap between 0.921 and 0.667.

    Two cheaper tests were tried first and **both failed**; they are recorded
    so nobody repeats them. *Distinct colour count* put the cartoon at 83 and
    genuine dark clips at 28, 30 and 32 -- inseparable. *Noise floor in flat
    blocks* put the cartoon at exactly 0.000 and four genuine night clips at
    0.000 too, because h264 crushes dark flat regions to zero variance.

    This catches fully synthetic footage. It will not catch a photoreal 3D
    render, and it is not meant to -- that one cuts fine anyway.
    """
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        return False  # cannot test; never block on a missing optional dep

    tmp = tempfile.mkdtemp(prefix="stock-synth-")
    try:
        frames = []
        for i, ss in enumerate(("0.5", "1.5")):
            png = os.path.join(tmp, "%d.png" % i)
            p = subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-ss", ss, "-i", path,
                 "-frames:v", "1", "-vf", "scale=240:-2", png],
                capture_output=True)
            if p.returncode or not os.path.isfile(png):
                return False
            frames.append(np.asarray(Image.open(png).convert("RGB"),
                                     dtype=np.int16))
        if len(frames) != 2 or frames[0].shape != frames[1].shape:
            return False
        identical = (np.abs(frames[0] - frames[1]).max(axis=2) == 0).mean()
        return float(identical) >= SYNTHETIC_THRESHOLD
    except (OSError, ValueError):
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def download(clip, footage_dir):
    """Fetch the mp4, once, into a content-addressed cache.

    Pexels serves signed, time-limited Vimeo CDN URLs -- a link read from a
    cached search response an hour later is dead. The cache is therefore keyed
    on the clip id and the *file*, never on the URL, and a file already on
    disk is never re-fetched.
    """
    name = "%s-%s-%dx%d.mp4" % (clip["source"], clip["id"],
                                clip["width"], clip["height"])
    path = os.path.join(footage_dir, name)
    if os.path.isfile(path) and os.path.getsize(path) > 4096:
        return path, 0

    tmp = path + ".part"
    req = urllib.request.Request(clip["url"], headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=180) as r, open(tmp, "wb") as fh:
            n = 0
            while True:
                chunk = r.read(1 << 18)
                if not chunk:
                    break
                fh.write(chunk)
                n += len(chunk)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            OSError) as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        return None, 0
    os.replace(tmp, path)
    return path, n


# -------------------------------------------------------------------- main --


def main():
    ap = argparse.ArgumentParser(
        description="Search and download the footage a stock storyboard needs.")
    ap.add_argument("storyboard")
    ap.add_argument("-o", "--out", help="resolved storyboard (default: in place)")
    ap.add_argument("--footage", help="where clips land (default: ./footage)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be fetched; touch no network")
    ap.add_argument("--only", nargs="*", help="re-resolve only these shot ids")
    ap.add_argument("--refetch", action="store_true",
                    help="ignore clips already resolved in the storyboard")
    ap.add_argument("--jobs", type=int, default=6)
    a = ap.parse_args()

    load_dotenv()

    try:
        with open(a.storyboard, encoding="utf-8") as fh:
            sb = json.load(fh)
    except (OSError, ValueError) as e:
        die("cannot read %s: %s" % (a.storyboard, e))

    base = os.path.dirname(os.path.abspath(a.storyboard))
    footage = a.footage or os.path.join(base, "footage")
    os.makedirs(footage, exist_ok=True)

    want_w, want_h = int(sb.get("width") or 1920), int(sb.get("height") or 1080)
    orientation = ("portrait" if want_h > want_w
                   else "square" if want_h == want_w else "landscape")

    if not os.environ.get("PEXELS_API_KEY") and not a.dry_run:
        die("PEXELS_API_KEY is not set.\n"
            "  Get one free and instantly at https://www.pexels.com/api/ ,\n"
            "  then put it in a .env that is gitignored:\n"
            "      echo 'PEXELS_API_KEY=...' >> .env\n"
            "  There is no key-free path: the internal API answers 401, the\n"
            "  search HTML carries no video URLs, and robots.txt disallows both.")

    searcher = Searcher(os.path.join(footage, ".search-cache"), orientation,
                        dry_run=a.dry_run)

    shots = sb.get("shots") or []
    want = set(a.only or [])
    used = set()
    for s in shots:
        c = s.get("clip")
        if not c:
            continue
        # Reserve every clip that is staying in the film. A shot is being
        # re-resolved only if it is named in --only, or if --refetch was given
        # with no --only at all (i.e. the whole film is being re-shot).
        rereso = (s["id"] in want) if want else bool(a.refetch)
        if not rereso:
            used.add("%s:%s" % (c["source"], c["id"]))

    # ---- search serially (the quota is per-hour, and order matters for
    # de-duplication), then download in parallel (the bottleneck is the CDN).
    todo = []
    unresolved = []
    restored = 0
    for s in shots:
        if want and s["id"] not in want:
            continue
        if s.get("clip") and not a.refetch:
            # A clip record is not footage. On a fresh clone the storyboard is
            # committed but `footage/` is not -- it is regenerable, and the
            # licence forbids redistributing the clips anyway -- so the record
            # points at a file that is not there. Believing the record would
            # report "all shots have footage" over an empty directory and hand
            # the renderer 44 missing inputs.
            c = s["clip"]
            f = c.get("file")
            p = f if (f and os.path.isabs(f)) else os.path.join(base, f or "")
            if f and os.path.isfile(p) and os.path.getsize(p) > 4096:
                continue
            fresh = searcher.by_id(c.get("source"), c.get("id"))
            if not fresh:
                log("%s: %s %s is gone from the library; re-searching"
                    % (s["id"], c.get("source"), c.get("id")))
                s["clip"] = None
            else:
                # Keep the pinned choice, take only the fresh signed URL.
                pick, upscaled = pick_file(fresh, want_w, want_h)
                if pick and pick.get("url"):
                    # Keep the pinned choice and its credit; take only the
                    # fresh signed URL and the geometry that comes with it.
                    c["url"] = pick["url"]
                    c["width"] = pick.get("width", c.get("width"))
                    c["height"] = pick.get("height", c.get("height"))
                    c["upscaled"] = bool(upscaled)
                    todo.append((s, c))
                    restored += 1
                    continue
                s["clip"] = None
        if s.get("placeholder"):
            unresolved.append((s, "compile marked it unphotographable"))
            continue
        clip, q, note = resolve(s, searcher, used, want_w, want_h)
        if not clip:
            s["clip"] = None
            s["placeholder"] = "no-footage"
            unresolved.append((s, note))
            continue
        used.add("%s:%s" % (clip["source"], clip["id"]))
        s["clip"] = clip
        if note:
            log("%s: %s" % (s["id"], note))
        todo.append((s, clip))

    if restored:
        log("restored %d pinned clip(s) whose files were missing" % restored)
    log("searched %d queries (%d cached, %d network calls)%s"
        % (searcher.calls + searcher.cached, searcher.cached, searcher.calls,
           "" if searcher.remaining is None
           else "; %s requests left this month" % searcher.remaining))

    if a.dry_run:
        for s, clip in todo:
            log("would fetch %s <- %s %s (%dx%d, %.0fs) by %s"
                % (s["id"], clip["source"], clip["id"], clip["width"],
                   clip["height"], clip["duration"], clip["author"]))
    else:
        bytes_total = 0
        with futures.ThreadPoolExecutor(max_workers=max(1, a.jobs)) as pool:
            jobs = {pool.submit(download, clip, footage): (s, clip)
                    for s, clip in todo}
            for fut in futures.as_completed(jobs):
                s, clip = jobs[fut]
                path, n = fut.result()
                bytes_total += n
                if not path:
                    log("%s: download failed; leaving a placeholder" % s["id"])
                    s["clip"] = None
                    s["placeholder"] = "download-failed"
                    unresolved.append((s, "download failed"))
                    continue
                clip["file"] = os.path.relpath(path, base)
                # The signed CDN URL expires. Keeping it in the storyboard
                # invites a later stage to use it and get a 403 on a file it
                # already has on disk.
                clip.pop("url", None)
        log("downloaded %.1f MB into %s"
            % (bytes_total / 1048576.0, os.path.relpath(footage, base)))

        # ---- reject synthetic footage and re-shoot the beat.
        #
        # This runs after download because the test is temporal: it needs two
        # real frames, which no amount of metadata can supply. Pexels has no
        # "live action only" search parameter, so this is the only gate.
        # Bounded retries -- a query that keeps returning artwork is a query
        # problem, and looping forever would just burn quota.
        for attempt in range(2):
            rejected = []
            for s, clip in todo:
                if not clip.get("file") or clip.get("_checked"):
                    continue
                clip["_checked"] = True
                if looks_synthetic(os.path.join(base, clip["file"])):
                    log("%s: %s %s is animation, not footage — re-shooting"
                        % (s["id"], clip["source"], clip["id"]))
                    rejected.append(s)
            if not rejected:
                break
            todo = []
            for s in rejected:
                # The clip stays in `used`, so resolve() cannot hand it back.
                clip, q, note = resolve(s, searcher, used, want_w, want_h)
                if not clip:
                    s["clip"] = None
                    s["placeholder"] = "no-footage"
                    unresolved.append((s, note or "only animation available"))
                    continue
                used.add("%s:%s" % (clip["source"], clip["id"]))
                s["clip"] = clip
                todo.append((s, clip))
            for s, clip in todo:
                path, n = download(clip, footage)
                if not path:
                    s["clip"] = None
                    s["placeholder"] = "download-failed"
                    unresolved.append((s, "download failed"))
                    continue
                clip["file"] = os.path.relpath(path, base)
                clip.pop("url", None)

    # ---- credits. Written every run from the resolved shots, so the ledger
    # can never drift from the cut it describes.
    credits, seen = [], set()
    for s in shots:
        c = s.get("clip")
        if not c:
            continue
        key = "%s:%s" % (c["source"], c["id"])
        if key in seen:
            continue
        seen.add(key)
        credits.append({
            "file": c.get("file"),
            "license": c["license"],
            "credit": "%s by %s on %s" % (
                "Video", c["author"],
                "Pexels" if c["source"] == "pexels" else "Pixabay"),
            "author": c["author"],
            "author_url": c.get("author_url"),
            "page": c.get("page"),
            "source": c["source"],
        })
    sb["credits"] = credits

    notes = [n for n in sb.get("notes") or [] if n.get("level") != "footage"]
    for s, why in unresolved:
        notes.append({"level": "blocking", "beat": s.get("beat"),
                      "shot": s.get("id"),
                      "note": "no footage: %s. Rewrite the beat toward "
                              "something a camera has photographed, or shoot "
                              "this beat in another style." % why})
    sb["notes"] = notes

    out = a.out or a.storyboard
    for s in shots:
        if isinstance(s.get("clip"), dict):
            s["clip"].pop("_checked", None)
    if not a.dry_run:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(sb, fh, indent=1, ensure_ascii=False)

        # The rights manager reads a flat asset register, so write one rather
        # than making it understand this style's storyboard.
        with open(os.path.join(base, "assets.json"), "w", encoding="utf-8") as fh:
            json.dump(credits, fh, indent=1, ensure_ascii=False)
        log("wrote %s and assets.json (%d clips, %d credits)"
            % (os.path.relpath(out, base), len(seen), len(credits)))

    resolved = sum(1 for s in shots if s.get("clip"))
    log("%d/%d shots have footage" % (resolved, len(shots)))
    for s, why in unresolved:
        log("  UNRESOLVED %s (%s): %s" % (s["id"], s.get("query"), why))

    raise SystemExit(1 if unresolved else 0)


if __name__ == "__main__":
    main()
