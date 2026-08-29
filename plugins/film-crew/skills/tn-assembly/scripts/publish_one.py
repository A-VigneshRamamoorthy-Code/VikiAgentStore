#!/usr/bin/env python3
"""Package, gate and upload exactly one item. The adapter `live.py` asks for.

`live.py --marketing <script>` calls this as `<script> <project> --only <id>`
and treats a non-zero exit as "not published". Until now the skill documented
that contract and shipped nothing that satisfied it, so the quick start named
a file that did not exist and every live run had to have an uploader written
for it before anything could reach a channel. That is the single largest
reason a measured session took two and a half hours to publish its first
video: the cutting was finished long before an uploader existed to carry it.

The automation itself already existed in the sibling `publisher` skill. What
was missing was the per-item glue -- resume, gating, stage order, visibility
-- which is all this file is.

    python3 publish_one.py <project> --only sh07

Exit status is 0 only if the item is live.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILLS = os.path.dirname(os.path.dirname(HERE))
PUBLISHER = os.path.join(SKILLS, "publisher", "scripts", "upload.py")
GATE = os.path.join(HERE, "publishgate.py")

# A Studio stage drives a real browser through an upload wizard; minutes is
# normal, hanging forever is not.
STAGE_TIMEOUT = 3600


def say(m):
    print(f"publish_one: {m}", flush=True)


def item_dir(project, item_id):
    d = os.path.join(project, "publish", item_id)
    if not os.path.isdir(d):
        raise SystemExit(f"no packaged directory for {item_id}: {d}\n"
                         "Run the head-of-marketing packaging stage first.")
    return d


def title_of(pdir):
    try:
        meta = json.load(open(os.path.join(pdir, "meta",
                                           "youtube_metadata.json")))
    except (OSError, ValueError):
        return ""
    return (meta.get("title") or "").strip()


def generic_labels(project):
    """Labels the planner gave to more than one window.

    The planner names every window with one session-wide string until the
    packaging stage replaces it with a real subject. Any label shared by two
    or more planned items is therefore a fallback, not a title -- which is
    how it is recognised here without hardcoding a phrase, or a language.

    This is a second line of defence, not the first. `publishgate.py` refuses
    generic titles too, but it only sees the directories it is handed, and a
    per-item adapter hands it exactly one -- so its duplicate check cannot
    fire on the first offender. That gap is how an episode and a Short went
    out carrying the whole sitting's name.
    """
    try:
        plan = json.load(open(os.path.join(project, "meta", "plan.json")))
    except (OSError, ValueError):
        return set()
    seen, dupes = set(), set()
    for group in ("episodes", "shorts"):
        for it in plan.get(group, []):
            lab = (it.get("label") or "").strip()
            if not lab:
                continue
            if lab in seen:
                dupes.add(lab)
            seen.add(lab)
    return dupes


def refuse_generic(pdir, generic):
    mine = title_of(pdir)
    head = mine.split("|")[0].strip()
    if head and head in generic:
        raise SystemExit(
            f"refusing {os.path.basename(pdir)}: its title is still the "
            f"planner's shared label ({head!r}). The retitling stage has not "
            "given this item a subject of its own.")


def gate(pdir):
    p = subprocess.run([sys.executable, GATE, pdir],
                       capture_output=True, text=True)
    if p.returncode != 0:
        out = ((p.stdout or "") + (p.stderr or "")).strip()
        raise SystemExit(f"refused by publishgate:\n{out}")


def stage(name, pdir, extra=None):
    """Run one publisher stage, surfacing the tail of its output on failure."""
    cmd = [sys.executable, PUBLISHER, name, pdir] + (extra or [])
    p = subprocess.run(cmd, cwd=os.path.dirname(PUBLISHER),
                       capture_output=True, text=True, timeout=STAGE_TIMEOUT)
    out = (p.stdout or "") + (p.stderr or "")
    if p.returncode != 0:
        tail = " / ".join(l.strip() for l in out.strip().splitlines()[-4:])
        raise RuntimeError(f"{name} failed rc={p.returncode}: {tail}")
    return out


def video_id(pdir):
    """The id of an already-finished upload, or None.

    upload_result.json is written only once the wizard completes, so its
    presence doubles as the marker that the upload stage need not run again.
    """
    try:
        res = json.load(open(os.path.join(pdir, "meta",
                                          "upload_result.json")))
    except (OSError, ValueError):
        return None
    vid = str(res.get("video_id") or "").strip()
    if not vid:
        m = re.search(r"(?:v=|youtu\.be/|/shorts/)([\w-]{11})",
                      str(res.get("link", "")))
        vid = m.group(1) if m else ""
    return vid or None


def privacy_of(project, override=None):
    """Visibility for this item.

    Defaults to `publish.privacy` in project.json, which the example ships as
    `private` -- rule 5 is that nothing goes public without a human deciding
    it should. Publishing straight to public is a per-project choice, made in
    the config, not a default of this script.
    """
    if override:
        return override
    try:
        cfg = json.load(open(os.path.join(project, "project.json")))
        return (cfg.get("publish", {}).get("privacy") or "private").strip()
    except (OSError, ValueError):
        return "private"


def chan_of(pdir):
    try:
        c = json.load(open(os.path.join(pdir, "meta", "channel.json")))
    except (OSError, ValueError):
        return "UNPINNED"
    return f"{c.get('name', '?')} ({c.get('channel_id', '?')})"


def pin_channel(project, pdir):
    """Give the package the channel id Studio has to be opened on.

    `upload.py` pins Studio to `/channel/<id>` so an upload can never land on
    a lookalike brand account, and it reads that id from the *package's*
    `meta/channel.json`. Only the publisher's `login` and `switch` subcommands
    ever write that file, and `login` skips the write when it times out --
    which still leaves a perfectly usable signed-in browser profile. The
    result is a package with no pin, an unpinned Studio that resolves to the
    account's default identity, and "Oops, something went wrong" instead of
    the upload dialog. A whole sitting was lost to this: the recorders, the
    cutting and the rendering were all healthy and nothing could upload.

    Resolve it once per project with:

        python3 <publisher>/scripts/upload.py switch <project>/publish/<id>

    then copy the result into every package.
    """
    dst = os.path.join(pdir, "meta", "channel.json")
    if os.path.exists(dst):
        return
    src = os.path.join(project, "meta", "channel.json")
    if not os.path.exists(src):
        raise SystemExit(
            "no meta/channel.json -- Studio would be opened unpinned and "
            "answer \"Oops, something went wrong\" instead of the upload "
            "dialog. Resolve the channel once with:\n"
            f"  python3 {PUBLISHER} switch {pdir}\n"
            f"then copy it to {src} so every later item inherits it.")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)
    say(f"pinned Studio to {json.load(open(src)).get('name', '?')}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("project")
    ap.add_argument("--only", required=True, help="the item id to publish")
    ap.add_argument("--privacy", default=None,
                    choices=["public", "unlisted", "private"],
                    help="overrides publish.privacy from project.json")
    ap.add_argument("--dry-run", action="store_true",
                    help="run the checks and report what would happen, "
                         "without touching the channel")
    a = ap.parse_args()

    if not os.path.exists(PUBLISHER):
        raise SystemExit(f"publisher skill not found at {PUBLISHER}")

    pdir = item_dir(a.project, a.only)
    kind = "episode" if a.only.startswith("ep") else "short"

    # Nothing reaches a channel without a real, distinct title and a thumbnail
    # whose text survives the crop the platform actually serves.
    refuse_generic(pdir, generic_labels(a.project))
    gate(pdir)

    # Before the dry-run branch, so the pre-flight check catches a missing
    # channel pin while there is still time to resolve it.
    pin_channel(a.project, pdir)

    done = video_id(pdir)

    # Verify the wiring before a sitting starts, when there is time to fix it.
    if a.dry_run:
        thumb = os.path.exists(os.path.join(pdir, "out", "thumbnail.jpg"))
        say(f"{a.only}: fit to publish ({kind})")
        say(f"  title:     {title_of(pdir)}")
        say(f"  thumbnail: {'yes' if thumb else 'MISSING'}")
        say(f"  channel:   {chan_of(pdir)}")
        say(f"  privacy:   {privacy_of(a.project, a.privacy)}")
        say(f"  action:    {'resume at publish (already ' + done + ')' if done else 'upload'}")
        return 0

    # Resume rather than restart. Re-running a failed publish used to send the
    # item back through the whole wizard, which put a second copy of an
    # already-public video on the channel.
    if done:
        say(f"{a.only}: already uploaded as {done} — resuming at publish")
        # An item held back for a generic title and released after retitling
        # went up under the old one. `publish` only changes visibility, so
        # without this the corrected title would never reach YouTube.
        try:
            stage("edit", pdir)
            say(f"{a.only}: pushed the current title and description")
        except Exception as e:
            say(f"{a.only}: metadata sync failed ({e})")
    else:
        say(f"{a.only}: uploading ({kind})")
        stage("upload", pdir)

    if os.path.exists(os.path.join(pdir, "out", "thumbnail.jpg")):
        try:
            stage("thumbnail", pdir)
        except Exception as e:
            # A missing custom thumbnail is a worse video, not a broken one,
            # and the daily cap makes failures here routine late in a session.
            say(f"{a.only}: thumbnail skipped ({e})")

    stage("publish", pdir, ["--privacy", privacy_of(a.project, a.privacy)])

    vid = video_id(pdir)
    if not vid:
        raise SystemExit(f"{a.only}: published but no video id was captured")
    say(f"{a.only}: live -> https://youtu.be/{vid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
