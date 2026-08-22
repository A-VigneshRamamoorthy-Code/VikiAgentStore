"""Publishing configuration shared by the head-of-marketing scripts.

A "publish project" is any directory containing a `publish.json`. Nothing here
knows about assemblies, politics or any particular channel -- it describes a
video and the channel it is going to, so the same code publishes a documentary,
a product demo or an assembly digest.

    {
      "channel":  {"handle": "politainment", "name": "Politainment"},
      "brand":    {"wordmark": "POLITAINMENT", "crimson": [206,22,30]},
      "video":    "out/episode_1080p.mp4",
      "thumbnail":"out/thumbnail.jpg",
      "captions":"meta/captions.srt",
      "privacy":  "private"
    }
"""
import hashlib
import json
import os
import shutil
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
    # Our own caption file. Left empty the platform falls back to speech
    # recognition, which mis-hears exactly the proper nouns the film was
    # researched to get right -- so this is a default, not an option.
    "captions": "meta/captions.srt",
    "privacy": "private",
    "category_id": "25",
    "made_for_kids": False,
    "language": {"primary": "en", "secondary": ""},
    # Signed-in Chrome profile. Relative paths resolve inside the project, so
    # the default keeps each project self-contained. Point several projects at
    # one absolute path to share a single sign-in -- a profile is ~700 MB and
    # signing in again per video is pure friction. Only one project may drive
    # a given profile at a time.
    "profile": ".chrome-profile",
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


PUBLISH_LOCK = "publish.lock.json"

#: Bumped whenever the lock format changes meaning. An uploader that does not
#: recognise the schema refuses rather than reading the fields it happens to
#: know -- an old reader silently ignoring a new restriction is exactly the
#: failure this file exists to prevent.
LOCK_SCHEMA = 2

#: How wide a visibility is. Narrowing is always fine; widening needs approval.
RANK = {"private": 0, "unlisted": 1, "public": 2}


def norm(rel):
    """Compare declared paths, not the strings people happen to type.

    `./out/v.mp4` and `out/v.mp4` are the same file, and refusing an upload
    over a leading dot-slash would teach operators that the approval gate is
    noise to be worked around.
    """
    if not rel:
        return rel
    return os.path.normpath(rel).replace(os.sep, "/")


def handle_of(channel):
    """The bare channel handle, from either shape it is stored in.

    `publish.json` carries a channel *object* (`{handle, name, channel_id}`)
    while the director records the *string* the operator typed after
    `--publish`. Comparing those two directly is always unequal, which turns
    the approval gate into a permanent refusal — and an operator who cannot
    ever publish learns to delete the lock file, disabling the gate for real.
    Both sides collapse to the handle instead.
    """
    if isinstance(channel, dict):
        channel = channel.get("handle") or channel.get("name") or ""
    return (channel or "").strip().lstrip("@").lower()


def sha256_file(path, _chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(_chunk), b""):
            h.update(b)
    return h.hexdigest()


class ApprovalError(SystemExit):
    """What is on disk is not what a human approved."""


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
    def captions(self):
        """The caption file, or None when this project ships without one.

        Unlike the video and the thumbnail this may legitimately be absent --
        an older project predates the subtitler -- so it resolves to None
        rather than to a path that does not exist.
        """
        rel = self.cfg.get("captions")
        if not rel:
            return None
        full = self.p(rel)
        return full if os.path.exists(full) else None

    def verify_approved(self, action="upload"):
        """Refuse to touch a live video that a human did not sign off on.

        `publish.lock.json` is written by the director once every file in a
        unit's outgoing bundle has been approved by sha256. Without this check
        the approval covers only whatever the director happened to record,
        while this uploader independently reads `publish.json` and could
        attach a re-render, a different thumbnail, or metadata rewritten
        afterwards -- with nothing anywhere reporting a problem.

        The lock is a **registry keyed by video**, because one production has
        many units and approving episode 2 must not revoke episode 1. We look
        ourselves up by the video `publish.json` names; being absent from the
        registry is a refusal, not a pass.

        No lock file at all means the director was not driving this. That is
        allowed, and it is said out loud rather than assumed to be fine.
        """
        path = self.p(PUBLISH_LOCK)
        if not os.path.exists(path):
            return None
        try:
            lock = json.load(open(path))
        except (OSError, ValueError) as e:
            raise ApprovalError(f"{path} is unreadable ({e}); refusing to "
                                f"{action} against an approval that cannot be "
                                f"checked")
        if not isinstance(lock, dict):
            raise ApprovalError(f"{path} is not an approval manifest")
        if lock.get("schema") != LOCK_SCHEMA:
            raise ApprovalError(
                f"{path} is schema {lock.get('schema')!r}, and this uploader "
                f"only understands {LOCK_SCHEMA}. Re-approve with a matching "
                f"director rather than guessing what the older format meant.")
        entries = lock.get("approvals")
        if not isinstance(entries, list) or not entries:
            raise ApprovalError(f"{path} records no approvals")

        want_video = norm(self.cfg.get("video"))
        entry = None
        for e in entries:
            if isinstance(e, dict) and isinstance(e.get("targets"), dict) \
                    and norm(e["targets"].get("video")) == want_video:
                entry = e
                break
        if entry is None:
            approved = ", ".join(
                sorted(str(e.get("unit")) for e in entries
                       if isinstance(e, dict))) or "nothing"
            raise ApprovalError(
                f"refusing to {action} -- publish.json attaches "
                f"{self.cfg.get('video')}, which no approval covers.\n"
                f"{path} approves: {approved}.\n\n"
                f"Point publish.json at an approved cut, or approve this one:"
                f"\n  director.py approve publish <root> "
                f"--episode N | --short N")

        if not isinstance(entry.get("files"), dict):
            raise ApprovalError(f"{path}: the entry for "
                                f"{entry.get('unit')!r} has no file digests")
        want_channel = handle_of(self.cfg.get("channel"))
        got_channel = handle_of(entry.get("channel"))
        if want_channel and got_channel and got_channel != want_channel:
            raise ApprovalError(
                f"refusing to {action} -- {entry.get('unit')} was approved for "
                f"channel {got_channel!r}, but publish.json is pointed at "
                f"{want_channel!r}. Approval is per channel.")

        bad = []
        for rel, want in entry["files"].items():
            full = self.p(rel)
            if not os.path.exists(full):
                bad.append(f"{rel}: approved, but missing now")
            elif sha256_file(full) != want:
                bad.append(f"{rel}: changed since it was approved")
        # Everything this uploader will actually attach has to be covered.
        covered = {norm(r) for r in entry["files"]}
        for name in ("video", "thumbnail", "metadata", "captions"):
            if name == "captions" and not self.captions:
                continue
            rel = self.cfg.get(name)
            if rel and norm(rel) not in covered:
                bad.append(f"{rel}: publish.json attaches it as the {name}, "
                           f"but the approval for {entry.get('unit')} does "
                           f"not cover it")
        if bad:
            raise ApprovalError(
                f"refusing to {action} -- what is on disk is not what was "
                "approved:\n  - " + "\n  - ".join(bad) +
                "\n\nRe-approve the current files with the director, or "
                f"delete {PUBLISH_LOCK} to act without an approval.")
        return entry

    def snapshot(self, entry, *rels):
        """Copy verified files aside, so the bytes checked are the bytes sent.

        Verifying a hash and then handing the *path* to the browser leaves a
        window in which the file can change: the check passes, the file is
        rewritten, and the rewrite is what uploads.

        This has to be a real copy. A hardlink survives a `mv` over the
        original -- but not an in-place truncating write, which reaches the
        same inode through either name. Measured, not assumed: linking and
        then rewriting the metadata with `open(..., "w")` produced a snapshot
        containing the attacker's title.

        The copy is then re-hashed against the approval, so bytes that changed
        *while* they were being copied are caught rather than frozen in.
        Returns {rel: frozen absolute path}.
        """
        digests = (entry or {}).get("files") or {}
        out = {}
        d = self.p("meta", ".verified")
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d, exist_ok=True)
        for rel in rels:
            if not rel:
                continue
            dst = os.path.join(d, norm(rel).replace("/", "__"))
            shutil.copy2(self.p(rel), dst)
            want = digests.get(rel) or digests.get(norm(rel))
            if want and sha256_file(dst) != want:
                raise ApprovalError(
                    f"refusing to upload -- {rel} changed while it was being "
                    f"copied for upload. Something is writing to it right "
                    f"now; re-approve once it has settled.")
            out[rel] = dst
        return out

    def verify_one(self, rel, privacy=None, spec=None):
        """Approve a single file by path, for batch uploads.

        `shorts` uploads many files in one run, each its own unit with its own
        approval. `verify_approved` keys off `publish.json`, which names only
        one video, so a batch needs to ask about each file directly -- and
        must ask, or one `publish.lock.json` covering episode 1 would wave
        through a folder of unapproved Shorts.

        `spec` is the file the *title, description and tags* come from. It has
        to be covered too. Verifying only the video bytes would approve the
        picture and publish whatever text was in the spec at upload time, so
        editing `shorts_publish.json` after approval would put an unapproved
        title on a public video with nothing objecting -- the long-form path
        already refuses exactly this by requiring `metadata` in `covered`.
        """
        entries = self._entries()
        if entries is None:
            return None
        want = norm(rel)
        for e in entries:
            if norm((e.get("targets") or {}).get("video")) != want:
                continue
            for f, digest in (e.get("files") or {}).items():
                full = self.p(f)
                if not os.path.exists(full):
                    raise ApprovalError(f"refusing to upload {rel} -- {f} was "
                                        f"approved but is missing now")
                if sha256_file(full) != digest:
                    raise ApprovalError(f"refusing to upload {rel} -- {f} has "
                                        f"changed since it was approved")
            if spec:
                covered = {norm(f) for f in (e.get("files") or {})}
                if norm(spec) not in covered:
                    raise ApprovalError(
                        f"refusing to upload {rel} -- its title, description "
                        f"and tags come from {spec}, which the approval for "
                        f"{e.get('unit')!r} does not cover. The picture was "
                        f"approved; the words were not.\n\nRe-approve this "
                        f"Short with the director so the text is included:\n"
                        f"  director.py approve publish <root> --short N")
            ok = e.get("privacy") or "private"
            if privacy and privacy != ok \
                    and RANK.get(privacy, 9) > RANK.get(ok, 0):
                raise ApprovalError(
                    f"refusing to upload {rel} as {privacy} -- "
                    f"{e.get('unit')} was approved as {ok}")
            return e
        approved = ", ".join(sorted(str(e.get("unit")) for e in entries))
        raise ApprovalError(
            f"refusing to upload {rel} -- no approval covers it.\n"
            f"{PUBLISH_LOCK} approves: {approved or 'nothing'}.\n"
            f"  director.py approve publish <root> --short N")

    def _entries(self):
        """The approval list, or None when the director is not driving."""
        path = self.p(PUBLISH_LOCK)
        if not os.path.exists(path):
            return None
        try:
            lock = json.load(open(path))
        except (OSError, ValueError) as e:
            raise ApprovalError(f"{path} is unreadable ({e})")
        if not isinstance(lock, dict) or lock.get("schema") != LOCK_SCHEMA:
            raise ApprovalError(f"{path} is schema {lock.get('schema')!r}, "
                                f"not {LOCK_SCHEMA}")
        entries = lock.get("approvals")
        if not isinstance(entries, list) or not entries:
            raise ApprovalError(f"{path} records no approvals")
        return [e for e in entries if isinstance(e, dict)]

    def verify_target(self, vid, action):
        """Refuse to aim a live-video command at something never approved.

        `publish`, `edit` and `thumbnail` all take an optional video id. Left
        alone they read the id back from `meta/upload_result.json`, which is
        the video this project just uploaded -- fine. Passed explicitly, they
        will happily operate on *any* video on the channel, which would walk
        straight around every check in this file. So when an approval exists,
        an explicit id has to be the one the approval produced.
        """
        entry = self.verify_approved(action=action)
        if entry is None or vid is None:
            return entry
        try:
            res = json.load(open(self.p("meta", "upload_result.json")))
            mine = str(res.get("link", "")).rsplit("/", 1)[-1]
        except (OSError, ValueError):
            mine = ""
        if not mine:
            raise ApprovalError(
                f"refusing to {action} {vid} -- {PUBLISH_LOCK} approves "
                f"{entry.get('unit')}, but there is no upload receipt saying "
                f"which video that became. Upload through this project, or "
                f"delete {PUBLISH_LOCK} to act without an approval.")
        if vid != mine:
            raise ApprovalError(
                f"refusing to {action} {vid} -- the approval for "
                f"{entry.get('unit')} produced {mine}. Approval is bound to "
                f"one video, so pointing this at another is refused.")
        return entry

    def verify_privacy(self, privacy, vid=None):
        """Going public is a separate decision from the bytes being right."""
        entry = self.verify_target(vid, f"set visibility to {privacy}")
        if entry is None:
            return None
        approved = entry.get("privacy") or "private"
        if privacy != approved and RANK.get(privacy, 9) > RANK.get(approved, 0):
            raise ApprovalError(
                f"refusing to make {entry.get('unit')} {privacy} -- it was "
                f"approved as {approved}. Re-plan with --privacy {privacy} "
                f"and re-approve, so the decision to go wider is recorded "
                f"somewhere other than this command line.")
        return entry

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
        """Persistent Chrome profile holding the signed-in YouTube session.

        Absolute values are used as-is so a single sign-in can serve several
        video projects; relative ones stay inside the project.
        """
        return os.path.expanduser(self.cfg["profile"]) \
            if os.path.isabs(os.path.expanduser(self.cfg["profile"])) \
            else self.p(self.cfg["profile"])

    def load_meta(self, path=None):
        """Read the metadata, optionally from a frozen snapshot of it.

        `upload` passes the snapshot so the title and description that go out
        are parsed from the same bytes that were hashed, not from a file that
        may have been rewritten in between.
        """
        return json.load(open(path or self.metafile))


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
