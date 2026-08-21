"""Publishing configuration shared by the youtube-publish scripts.

A "publish project" is any directory containing a `publish.json`. Nothing here
knows about assemblies, politics or any particular channel -- it describes a
video and the channel it is going to, so the same code publishes a documentary,
a product demo or an assembly digest.

    {
      "channel":  {"handle": "politainment", "name": "Politainment"},
      "brand":    {"wordmark": "POLITAINMENT", "crimson": [206,22,30]},
      "video":    "out/episode_1080p.mp4",
      "thumbnail":"out/thumbnail.jpg",
      "privacy":  "private"
    }
"""
import json
import os
import time

DEFAULTS = {
    "channel": {"handle": "", "name": "", "channel_id": ""},
    "brand": {
        "wordmark": "",
        "crimson": [206, 22, 30],
        "gold": [255, 205, 60],
        "ink": [8, 10, 18],
        "paper": [247, 245, 240],
    },
    "video": "out/episode_1080p.mp4",
    "thumbnail": "out/thumbnail.jpg",
    "metadata": "meta/youtube_metadata.json",
    "privacy": "private",
    "category_id": "25",
    "made_for_kids": False,
    "language": {"primary": "en", "secondary": ""},
}

# YouTube's hard limits. Exceeding any of them fails the upload, and the tag
# cap in particular fails *silently* in the Studio UI as "Cannot save until
# errors are resolved".
LIMITS = {"title": 100, "description": 5000, "tags_total": 500,
          "thumbnail_bytes": 2 * 1024 * 1024}


def _merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(
            base.get(k), dict) else v
    return out


class Publish:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        path = os.path.join(self.root, "publish.json")
        raw = json.load(open(path)) if os.path.exists(path) else {}
        self.cfg = _merge(DEFAULTS, raw)

    def p(self, *parts):
        return os.path.join(self.root, *parts)

    def get(self, *keys, default=None):
        cur = self.cfg
        for k in keys:
            if not isinstance(cur, dict) or k not in cur:
                return default
            cur = cur[k]
        return cur

    def rgb(self, name):
        return tuple(self.get("brand", name, default=[0, 0, 0]))

    @property
    def video(self):
        return self.p(self.cfg["video"])

    @property
    def thumbnail(self):
        return self.p(self.cfg["thumbnail"])

    @property
    def metafile(self):
        """The one file the uploader reads.

        Any generator that writes metadata somewhere else will upload stale
        text with no error at all -- a failure mode that has already shipped a
        wrong title once. Keep this the single source of truth.
        """
        return self.p(self.cfg["metadata"])

    @property
    def profile(self):
        """Persistent Chrome profile holding the signed-in YouTube session."""
        return self.p(".chrome-profile")

    def load_meta(self):
        return json.load(open(self.metafile))


def check_limits(meta):
    """Validate metadata against YouTube's caps. Returns a list of problems."""
    problems = []
    t = meta.get("title", "")
    d = meta.get("description", "")
    tags = meta.get("tags", [])
    tag_len = sum(len(x) for x in tags) + max(0, len(tags) - 1)
    if len(t) > LIMITS["title"]:
        problems.append(f"title {len(t)}/{LIMITS['title']}")
    if not t.strip():
        problems.append("title is empty")
    if len(d) > LIMITS["description"]:
        problems.append(f"description {len(d)}/{LIMITS['description']}")
    if tag_len > LIMITS["tags_total"]:
        problems.append(f"tags {tag_len}/{LIMITS['tags_total']} chars")
    return problems


def say(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)
