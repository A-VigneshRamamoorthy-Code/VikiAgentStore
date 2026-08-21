"""Project configuration and shared paths.

Everything downstream reads its settings from one `project.json` so the same
pipeline can serve any channel, any session and any VIP. Nothing in this skill
may hardcode a URL, a channel handle or a person's name.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)

DEFAULTS = {
    "source": {"url": "", "session_date": "", "note": ""},
    "channel": {"handle": "", "name": "", "channel_id": ""},
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
        "match_threshold": 0.45,
        "review_threshold": 0.38,
    },
    "video": {"width": 1920, "height": 1080, "fps": 30},
    "shorts": {"width": 1080, "height": 1920, "fps": 30,
               "min_len": 20, "max_len": 58},
    "longform": {"min_clip": 34, "max_clip": 95,
                 "min_clips": 4, "max_clips": 8,
                 "target_runtime": 480},
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

    def __init__(self, root):
        self.root = os.path.abspath(root)
        path = os.path.join(self.root, "project.json")
        raw = json.load(open(path)) if os.path.exists(path) else {}
        self.cfg = _merge(DEFAULTS, raw)
        for d in ("src", "meta", "work", "clips", "out", "out/shorts",
                  "brand", "meta/frames"):
            os.makedirs(os.path.join(self.root, d), exist_ok=True)

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

    def load(self, name, default=None):
        path = self.p("meta", name if name.endswith(".json")
                      else f"{name}.json")
        if not os.path.exists(path):
            return default
        return json.load(open(path))

    def save(self, name, data):
        path = self.p("meta", name if name.endswith(".json")
                      else f"{name}.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return path


def publish_scripts():
    """Locate the sibling youtube-publish skill.

    Packaging, thumbnails, SEO and upload deliberately live in that skill so
    any project can reuse them. Resolving it by relative path keeps the two
    skills independently installable while still composing.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    cand = os.path.normpath(
        os.path.join(here, "..", "..", "youtube-publish", "scripts"))
    if not os.path.isdir(cand):
        raise SystemExit(
            "the youtube-publish skill is required for packaging and upload "
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
