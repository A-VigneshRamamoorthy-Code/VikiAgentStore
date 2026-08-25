"""Project configuration and shared paths.

Everything downstream reads its settings from one `project.json` so the same
pipeline can serve any channel, any session and any VIP. Nothing in this skill
may hardcode a URL, a channel handle or a person's name.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)

# YouTube's hard ceiling for Shorts eligibility: 180s for anything uploaded
# after 2024-10-15 (it was 60s before that). This is a platform fact, not a
# taste preference — exceeding it makes the upload long-form, not a Short.
SHORTS_HARD_MAX = 180.0

DEFAULTS = {
    "source": {"url": "", "session_date": "", "note": "",
               "format": "137+140", "channel_url": "", "live": False},
    "channel": {"handle": "", "name": "", "channel_id": "", "url": ""},
    "brand": {
        "name": "POLITAINMENT",
        "crimson": [206, 22, 30],
        "gold": [255, 205, 60],
        "ink": [8, 10, 18],
        "paper": [247, 245, 240],
    },
    "language": {"primary": "ta", "secondary": "en"},
    "vip": {
        "enabled": False,
        "name": "",
        "name_local": "",
        "honorific": "",
        "ref_images": [],
        "distractor_images": [],
        "match_threshold": 0.45,
        "review_threshold": 0.38,
        "min_margin": 0.06,
        "step": 3.0,
        "min_face": 42,
    },
    "video": {"width": 1920, "height": 1080, "fps": 30},
    "shorts": {"width": 1080, "height": 1920, "fps": 30,
               "min_len": 60, "max_len": 120,
               "max_count": 6, "cta": "",
               "framing": "fill", "focus_x": 0.5, "focus_auto": True},
    "longform": {"min_clip": 34, "max_clip": 95,
                 "min_clips": 4, "max_clips": 8,
                 "target_runtime": 480,
                 "max_episodes": 6, "keep_fraction": 0.45,
                 "min_highlight": 0.55},
    # Silence detection. Gaps shorter than `min_silence` are breaths, not
    # sentence boundaries.
    "audio": {"noise_db": -38, "min_silence": 0.30},
    "publish": {"privacy": "private", "category_id": "25",
                "made_for_kids": False},
}


def _merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(
            base.get(k), dict) else v
    return out


class Project:
    """Resolved project: settings plus the working directory layout."""

    def __init__(self, root, create_dirs=True):
        self.root = os.path.abspath(root)
        path = os.path.join(self.root, "project.json")
        self.config_error = None
        self.config_missing = not os.path.exists(path)
        raw = {}
        if not self.config_missing:
            try:
                raw = json.load(open(path))
            except Exception as e:
                self.config_error = f"{path}: {e}"
        self.raw = raw if isinstance(raw, dict) else {}
        if raw and not isinstance(raw, dict):
            self.config_error = "%s: should hold an object" % path
        self.cfg = _merge(DEFAULTS, self.raw)
        if create_dirs:
            for d in ("src", "meta", "work", "clips", "out", "out/shorts",
                      "brand", "meta/frames"):
                os.makedirs(os.path.join(self.root, d), exist_ok=True)

    def problems(self):
        """Settings that are present but the wrong shape.

        Types are taken from ``DEFAULTS`` rather than a second schema, so a new
        setting cannot be added without its type coming along. Without this a
        `"fps": "sixty"` reaches ffmpeg as an argument and fails several
        minutes into a render, with an error about the filter graph.
        """
        found = []

        def walk(want, got, path):
            for k, wv in want.items():
                if k not in got:
                    continue
                gv, where = got[k], path + [k]
                dotted = ".".join(where)
                if isinstance(wv, dict):
                    if not isinstance(gv, dict):
                        found.append("%s should be an object, found %s"
                                     % (dotted, type(gv).__name__))
                    else:
                        walk(wv, gv, where)
                elif isinstance(wv, bool):
                    if not isinstance(gv, bool):
                        found.append("%s should be true or false, found %r"
                                     % (dotted, gv))
                elif isinstance(wv, (int, float)):
                    # bool is an int in Python; "fps": true is still wrong.
                    if isinstance(gv, bool) or not isinstance(gv, (int, float)):
                        found.append("%s should be a number, found %r"
                                     % (dotted, gv))
                elif isinstance(wv, list):
                    if not isinstance(gv, list):
                        found.append("%s should be a list, found %s"
                                     % (dotted, type(gv).__name__))
                elif isinstance(wv, str):
                    if not isinstance(gv, str):
                        found.append("%s should be text, found %r"
                                     % (dotted, gv))

        walk(DEFAULTS, self.raw, [])
        w, h = self.get("video", "width"), self.get("video", "height")
        if isinstance(w, int) and isinstance(h, int) and w < h:
            found.append("video.width %d is less than video.height %d — that "
                         "is a vertical frame; shorts have their own section"
                         % (w, h))
        lo = self.get("shorts", "min_len")
        hi = self.get("shorts", "max_len")
        if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) \
                and lo > hi:
            found.append("shorts.min_len %s is greater than shorts.max_len %s"
                         % (lo, hi))
        if isinstance(hi, (int, float)) and hi > SHORTS_HARD_MAX:
            found.append("shorts.max_len %s exceeds YouTube's %.0fs Shorts "
                         "limit — anything longer is published as a normal "
                         "video and loses the Shorts feed"
                         % (hi, SHORTS_HARD_MAX))
        lo = self.get("longform", "min_clip")
        hi = self.get("longform", "max_clip")
        if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) \
                and lo > hi:
            found.append("longform.min_clip %s is greater than "
                         "longform.max_clip %s" % (lo, hi))
        return found

    def unused(self):
        """Keys in `project.json` that nothing reads.

        ``_merge`` only walks `DEFAULTS`, so a misspelled `"short"` section is
        not an error — it is silently ignored, which is worse. The setting a
        person believed they had changed simply never applies.
        """
        dead = []

        def walk(want, got, path):
            for k, gv in got.items():
                where = path + [k]
                if k not in want:
                    dead.append(".".join(where))
                elif isinstance(want[k], dict) and isinstance(gv, dict):
                    walk(want[k], gv, where)

        walk(DEFAULTS, self.raw, [])
        return dead

    # --- paths ------------------------------------------------------------
    def p(self, *parts):
        return os.path.join(self.root, *parts)

    @property
    def audio(self):
        return self.p("src", "audio.m4a")

    @property
    def scan_video(self):
        """Low-resolution copy used only for face/vision sweeps."""
        return self.p("src", "scan_360p.mp4")

    # --- settings ---------------------------------------------------------
    def __getitem__(self, key):
        return self.cfg[key]

    def get(self, *keys, default=None):
        cur = self.cfg
        for k in keys:
            if not isinstance(cur, dict) or k not in cur:
                return default
            cur = cur[k]
        return cur

    @property
    def url(self):
        u = self.get("source", "url")
        if not u:
            raise SystemExit(
                "project.json has no source.url -- set it before running")
        return u

    def rgb(self, name):
        return tuple(self.get("brand", name, default=[0, 0, 0]))

    def set(self, *keys, value):
        """Persist a setting back to project.json.

        Used by the live tracker to pin the stream URL it resolved from a
        channel: every stage runs as its own process and reads the URL from
        the file, so a discovery that stays in memory is invisible to all of
        them.
        """
        for target in (self.cfg, self.raw):
            cur = target
            for k in keys[:-1]:
                cur = cur.setdefault(k, {})
            cur[keys[-1]] = value
        atomic_write_json(os.path.join(self.root, "project.json"), self.raw)
        return value

    def load(self, name, default=None):
        path = self.p("meta", name if name.endswith(".json")
                      else f"{name}.json")
        if not os.path.exists(path):
            return default
        return json.load(open(path))

    def save(self, name, data):
        path = self.p("meta", name if name.endswith(".json")
                      else f"{name}.json")
        atomic_write_json(path, data)
        return path


def atomic_write_json(path, data):
    """Write JSON in-place without leaving a half-written manifest behind."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}"
    try:
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def sha256_file(path):
    """Content hash for cache keys and artifact-bound approvals."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_sha256(data):
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def file_fingerprint(path):
    if not path or not os.path.exists(path):
        return {"path": path, "exists": False}
    return {"path": path, "exists": True, "size": os.path.getsize(path),
            "sha256": sha256_file(path)}


def tool_fingerprint(*names):
    """Record tool versions that can change bytes or analysis output."""
    out = {}
    for name in names:
        exe = shutil.which(name)
        if not exe:
            out[name] = {"found": False}
            continue
        flag = "-version" if name in ("ffmpeg", "ffprobe") else "--version"
        r = subprocess.run([exe, flag], capture_output=True, text=True)
        first = (r.stdout or r.stderr).splitlines()
        out[name] = {"found": True, "path": exe,
                     "version": first[0] if first else ""}
    return out


def cache_key(stage, inputs=None, settings=None, tools=None):
    return stable_sha256({
        "stage": stage,
        "inputs": inputs or {},
        "settings": settings or {},
        "tools": tool_fingerprint(*(tools or ())),
    })


def outputs_exist(outputs):
    return all(os.path.exists(p) and (
        os.path.isdir(p) or os.path.getsize(p) > 0) for p in outputs)


def load_stage_cache(pr):
    return pr.load("stage_cache", default={}) or {}


def stage_is_cached(pr, stage, key, outputs):
    rec = load_stage_cache(pr).get(stage, {})
    return rec.get("key") == key and outputs_exist(outputs)


def mark_stage_cached(pr, stage, key, outputs):
    cache = load_stage_cache(pr)
    cache[stage] = {"key": key, "outputs": [
        os.path.relpath(p, pr.root) for p in outputs], "ok": True}
    pr.save("stage_cache", cache)


def parse_approvals(values=None):
    """Parse artifact approvals from args and TN_ASSEMBLY_APPROVALS."""
    approvals = {}
    raw = os.environ.get("TN_ASSEMBLY_APPROVALS")
    if raw:
        try:
            approvals.update(json.loads(raw))
        except json.JSONDecodeError:
            raise SystemExit("TN_ASSEMBLY_APPROVALS must be a JSON object")
    for v in values or []:
        if ":" not in v:
            raise SystemExit("--approve-overwrite must be path:sha256")
        path, digest = v.rsplit(":", 1)
        approvals[path] = digest.lower()
    return approvals


def approvals_env(approvals):
    env = os.environ.copy()
    if approvals:
        env["TN_ASSEMBLY_APPROVALS"] = json.dumps(
            approvals, sort_keys=True, separators=(",", ":"))
    return env


def require_overwrite_approval(path, pr, approvals):
    """Refuse to replace an existing artifact unless this exact file was okayed."""
    if not os.path.exists(path):
        return
    digest = sha256_file(path)
    rel = os.path.relpath(path, pr.root)
    keys = (rel, path)
    if any(approvals.get(k, "").lower() == digest for k in keys):
        return
    raise SystemExit(
        f"refusing to overwrite {rel} without artifact-bound approval\n"
        f"approve this exact file by re-running with:\n"
        f"  --approve-overwrite '{rel}:{digest}'")


def publish_scripts():
    """Locate the sibling head-of-marketing skill.

    Packaging, thumbnails, SEO and upload deliberately live in that skill so
    any project can reuse them. Resolving it by relative path keeps the two
    skills independently installable while still composing.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    cand = os.path.normpath(
        os.path.join(here, "..", "..", "head-of-marketing", "scripts"))
    if not os.path.isdir(cand):
        raise SystemExit(
            "the head-of-marketing skill is required for packaging and upload "
            f"but was not found at {cand}. Install it alongside tn-assembly.")
    if cand not in sys.path:
        sys.path.insert(0, cand)
    return cand


def hhmmss(s):
    s = int(s)
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def mmss(s):
    s = int(round(s))
    return f"{s // 60}:{s % 60:02d}"


def say(msg):
    import time
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)
