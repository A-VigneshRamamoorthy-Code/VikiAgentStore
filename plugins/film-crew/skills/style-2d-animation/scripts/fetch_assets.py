#!/usr/bin/env python3
"""Guarantee this style's art assets are on disk before a render starts.

    python3 fetch_assets.py --check      # exit 1 if anything is missing/corrupt
    python3 fetch_assets.py              # fetch whatever --check would flag
    python3 fetch_assets.py --force      # re-fetch every declared source
    python3 fetch_assets.py --list       # print every known asset id by category
    python3 fetch_assets.py --require head/Afro face/Calm body/standing/WalkingColorPants

Everything this script is allowed to fetch is declared in
`../assets/manifest.json`: a URL, a sha256 to pin it against, a licence, and
the expected shape of what it unpacks into. Nothing here goes looking for
assets on its own initiative.

That manifest is trusted less than "whatever it says, do it" -- see
`BLOCKED_HOSTS` and `ALLOWED_LICENSES` below. This style's assets ship inside
a public, MIT-licensed repository, so a source has to be redistributable, not
merely usable in one project. `../assets/LICENSES.md` explains the reasoning
in prose; this file is what actually enforces it.

Exit status: 0 everything asked for is present, 1 something is missing,
corrupt, or the fetch itself failed, 2 the manifest or invocation is invalid.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
ASSETS_DIR = os.path.join(SKILL_DIR, "assets")
MANIFEST_PATH = os.path.join(ASSETS_DIR, "manifest.json")

REQUEST_TIMEOUT = 60  # seconds -- a stalled connection must not hang a render pipeline

# Hosts this fetcher refuses to download from, no matter what a manifest says.
#
# magnific.com is freepik.com under a different name: Freepik Company S.L.
# acquired Magnific in 2024 and rebranded, so the same Terms of Use govern
# both. Those terms forbid redistributing downloaded content "in ... a
# library ... for distribution" and forbid sublicensing it -- which is
# exactly what committing an asset to this public, MIT-licensed repository
# would do. The rest of this list is the same shape of restriction from
# other stock/marketplace sites: fine to use in one project, not licensed to
# repackage and ship to everyone who installs this skill. Full reasoning in
# ../assets/LICENSES.md.
BLOCKED_HOSTS = {
    "magnific.com", "www.magnific.com",
    "freepik.com", "www.freepik.com", "img.freepik.com",
    "mixkit.co", "craftwork.design", "icons8.com",
}

_FREEPIK_HOSTS = {"magnific.com", "www.magnific.com", "freepik.com", "www.freepik.com", "img.freepik.com"}

# Licences already known to permit redistribution in a public repository.
# A source declaring anything else -- or nothing -- is refused rather than
# assumed safe, because the failure mode of guessing wrong here is shipping
# someone else's content under terms that do not allow it.
ALLOWED_LICENSES = {"CC0-1.0", "MIT", "Unlicense", "PDDL-1.0", "CC-BY-4.0"}


class FetchError(Exception):
    """A source could not be downloaded, verified or extracted."""


def _report(message):
    print("fetch_assets: %s" % message, file=sys.stderr)


def _die(message, code=2):
    _report(message)
    sys.exit(code)


# --------------------------------------------------------------------------
# manifest loading and policy enforcement
# --------------------------------------------------------------------------

def _blocked_host_message(source_id, host):
    if host in _FREEPIK_HOSTS:
        return (
            "source '%s': host '%s' is Freepik (Magnific was acquired by Freepik "
            "Company S.L. in 2024 and rebranded to it). Freepik's Terms of Use SS8.1 "
            "forbid content being \"included (in whole or in part) in a database, "
            "archive or in any other media/stock product, collection, set of clips, "
            "or library, for distribution\" and forbid you to \"resell, assign, "
            "transfer or sublicense\" it -- which is exactly what committing it to "
            "this public, MIT-licensed repository would do. SS2 separately forbids "
            "using \"robots, spiders or any other mechanism\" to fetch from the site, "
            "which is what this script would be. This host is blocked unconditionally; "
            "see assets/LICENSES.md." % (source_id, host)
        )
    return (
        "source '%s': host '%s' is on this project's blocked-host list -- a "
        "stock/marketplace site whose terms do not grant redistribution rights, so "
        "its assets cannot be committed to this public, MIT-licensed repository. Use "
        "a source with an explicit redistributable licence instead; see "
        "assets/LICENSES.md." % (source_id, host)
    )


def _validate_source(source, manifest_path):
    sid = source.get("id")
    if not sid:
        _die("%s: a source is missing 'id'" % manifest_path)

    for key in ("license", "url", "sha256", "extract", "expect"):
        if key not in source:
            _die("%s: source '%s' is missing '%s'" % (manifest_path, sid, key))

    license_ = source["license"]
    if license_ not in ALLOWED_LICENSES:
        _die(
            "%s: source '%s' declares license %r, which is not on the redistribution "
            "allow-list %s. Refusing to fetch anything whose licence this tool has not "
            "been told is safe to commit to a public repository."
            % (manifest_path, sid, license_, sorted(ALLOWED_LICENSES))
        )

    url = source["url"]
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if host in BLOCKED_HOSTS:
        _die(_blocked_host_message(sid, host))
    if parsed.scheme != "https":
        _die("%s: source '%s' url must be https, got %r" % (manifest_path, sid, parsed.scheme or ""))

    if not re.fullmatch(r"[0-9a-fA-F]{64}", source["sha256"] or ""):
        _die("%s: source '%s' has no valid sha256 to verify the download against" % (manifest_path, sid))

    extract = source["extract"]
    if not isinstance(extract, dict) or not all(k in extract for k in ("tool", "subdir", "out")):
        _die("%s: source '%s' 'extract' must have tool, subdir and out" % (manifest_path, sid))

    expect = source["expect"]
    if not isinstance(expect, dict) or not expect:
        _die("%s: source '%s' 'expect' must be a non-empty category -> count map" % (manifest_path, sid))


def load_manifest(path=MANIFEST_PATH):
    if not os.path.isfile(path):
        _die("manifest not found at %s" % path)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        _die("cannot read %s: %s" % (path, exc))

    if manifest.get("schema") != 1:
        _die("%s: unsupported schema %r (expected 1)" % (path, manifest.get("schema")))

    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        _die("%s: no sources declared" % path)

    for source in sources:
        _validate_source(source, path)
    return manifest


# --------------------------------------------------------------------------
# local completeness -- the check `--check`, fetch and `--require` all share
# --------------------------------------------------------------------------

def _out_dir(source):
    return os.path.join(ASSETS_DIR, source["extract"]["out"])


def local_status(source):
    """(complete, count, problems) for one source, read straight off disk.

    Complete means: an index.json exists, every category in `expect` has
    exactly the declared count, and every id it lists really is a readable,
    parseable JSON file -- not just present in the index. The index is
    written by the same extractor that writes the files, so trusting its
    counts alone would miss a run that died halfway through.
    """
    out_dir = _out_dir(source)
    index_path = os.path.join(out_dir, "index.json")
    if not os.path.isfile(index_path):
        return False, 0, ["%s: no index.json at %s (never fetched?)" % (source["id"], index_path)]

    try:
        with open(index_path, "r", encoding="utf-8") as fh:
            index = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return False, 0, ["%s: index.json unreadable (%s)" % (source["id"], exc)]

    categories = index.get("categories") or {}
    problems = []
    count = 0
    for category, expected_n in source["expect"].items():
        ids = categories.get(category)
        if ids is None:
            problems.append("%s: category '%s' missing from index.json" % (source["id"], category))
            continue
        if len(ids) != expected_n:
            problems.append(
                "%s: category '%s' has %d assets, expected %d"
                % (source["id"], category, len(ids), expected_n)
            )
        for asset_id in ids:
            asset_path = os.path.join(out_dir, category, "%s.json" % asset_id)
            rel = os.path.relpath(asset_path, ASSETS_DIR)
            if not os.path.isfile(asset_path):
                problems.append("%s: missing file %s" % (source["id"], rel))
                continue
            try:
                with open(asset_path, "r", encoding="utf-8") as fh:
                    json.load(fh)
            except (OSError, json.JSONDecodeError) as exc:
                problems.append("%s: corrupt %s (%s)" % (source["id"], rel, exc))
            else:
                count += 1

    return (len(problems) == 0), count, problems


# --------------------------------------------------------------------------
# fetch: download, verify, extract
# --------------------------------------------------------------------------

def _safe_extract(tar, dest_dir):
    """Extract every member of an open tarfile into dest_dir, refusing
    anything that could write outside it.

    `tarfile.extractall()` is the textbook path-traversal footgun: a member
    named `../../etc/cron.d/x`, or an absolute path, is honoured exactly as
    written unless the caller checks first. Symlinks and hardlinks are
    refused outright rather than validated -- a static asset archive has no
    legitimate reason to contain one, so rejecting the whole category is
    simpler and safer than reasoning about where each link points.

    This also works around a real bug found while building this fetcher: the
    open-peeps tarball stores its directories as mode 0o666 (no execute bit),
    which extracts as unreadable/untraversable on macOS and breaks the node
    extractor's directory walk. Assigning our own fixed modes instead of the
    archive's is what fixes that, as a side effect of not trusting the
    archive's metadata at all.
    """
    dest_root = os.path.realpath(dest_dir)
    for member in tar.getmembers():
        if member.issym() or member.islnk():
            raise FetchError(
                "refusing to extract %r: symlinks/hardlinks are not permitted in an "
                "asset archive" % member.name
            )
        if not (member.isfile() or member.isdir()):
            raise FetchError("refusing to extract %r: unsupported entry type" % member.name)

        target = os.path.realpath(os.path.join(dest_root, member.name))
        if target != dest_root and not target.startswith(dest_root + os.sep):
            raise FetchError("refusing to extract %r: escapes the destination directory" % member.name)

        if member.isdir():
            os.makedirs(target, exist_ok=True)
            os.chmod(target, 0o755)
            continue

        os.makedirs(os.path.dirname(target), exist_ok=True)
        os.chmod(os.path.dirname(target), 0o755)
        src = tar.extractfile(member)
        if src is None:
            continue
        with src, open(target, "wb") as out:
            shutil.copyfileobj(src, out)
        os.chmod(target, 0o644)


def _download(url, dest_path):
    """Stream url to dest_path, returning its sha256.

    Hashed while it is written rather than after, so a several-hundred-KB
    archive never needs to sit in memory twice over just to be checked.
    """
    request = urllib.request.Request(url, headers={"User-Agent": "film-crew-fetch-assets/1"})
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response, \
                open(dest_path, "wb") as out:
            while True:
                chunk = response.read(1 << 16)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise FetchError("download of %s failed: %s" % (url, exc)) from exc
    return digest.hexdigest()


def _fetch_one(source, node_path):
    sid = source["id"]
    tool_path = os.path.join(HERE, source["extract"]["tool"])
    if not os.path.isfile(tool_path):
        raise FetchError("extractor %s not found next to fetch_assets.py" % source["extract"]["tool"])
    if node_path is None:
        raise FetchError(
            "node is required to run %s but was not found on PATH -- install Node.js "
            "and retry" % source["extract"]["tool"]
        )

    # A per-run scratch directory via tempfile, exactly as the rest of this
    # style's tooling does (see lookcheck.py's frame sampling) -- resolved
    # through the platform's own temp-dir convention, not hardcoded, and
    # always removed below whether the fetch succeeds or not.
    work_dir = tempfile.mkdtemp(prefix="fetch-assets-%s-" % sid)
    try:
        tarball_path = os.path.join(work_dir, "source.tgz")
        print("  downloading %s" % source["url"])
        digest = _download(source["url"], tarball_path)
        expected = source["sha256"].lower()
        if digest != expected:
            raise FetchError(
                "sha256 mismatch for %s: expected %s, got %s -- refusing to unpack an "
                "artifact that does not match the pinned manifest" % (sid, expected, digest)
            )
        print("  sha256 verified (%s)" % digest)

        extract_root = os.path.join(work_dir, "extracted")
        os.makedirs(extract_root)
        with tarfile.open(tarball_path, "r:*") as tar:
            _safe_extract(tar, extract_root)

        build_dir = os.path.join(extract_root, source["extract"]["subdir"])
        if not os.path.isdir(build_dir):
            raise FetchError(
                "%s: expected %s inside the archive, did not find it"
                % (sid, source["extract"]["subdir"])
            )

        out_dir = _out_dir(source)
        # A previous partial run must not leave files behind that happen to
        # satisfy the completeness check by accident; start from empty.
        shutil.rmtree(out_dir, ignore_errors=True)
        os.makedirs(os.path.dirname(out_dir), exist_ok=True)

        result = subprocess.run(
            [node_path, tool_path, build_dir, out_dir],
            capture_output=True, text=True,
        )
        for line in result.stdout.splitlines():
            print("  %s" % line)
        if result.returncode != 0:
            detail = result.stderr.strip()
            raise FetchError(
                "%s: extractor exited %d%s" % (sid, result.returncode, (": " + detail) if detail else "")
            )
    except FetchError:
        raise
    except Exception as exc:
        # Anything not already raised as a FetchError above -- a malformed
        # archive, a permissions error, tarfile choking on truncated input --
        # still needs to come out as a clean, reported failure rather than a
        # traceback, since this runs ahead of a render pipeline that only
        # checks the exit code.
        raise FetchError("%s: unexpected failure (%s)" % (sid, exc)) from exc
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_check(manifest):
    ok_all = True
    for source in manifest["sources"]:
        ok, count, problems = local_status(source)
        if ok:
            print("%s: ok -- %d assets (license %s)" % (source["id"], count, source["license"]))
        else:
            ok_all = False
            print("%s: INCOMPLETE" % source["id"])
            for problem in problems:
                print("  - %s" % problem)
    return 0 if ok_all else 1


def cmd_list(manifest):
    for source in manifest["sources"]:
        print("%s (%s) -- %s" % (source["id"], source["license"], source["homepage"]))
        index_path = os.path.join(_out_dir(source), "index.json")
        if not os.path.isfile(index_path):
            print("  not fetched yet -- run: python3 fetch_assets.py")
            continue
        with open(index_path, "r", encoding="utf-8") as fh:
            categories = (json.load(fh).get("categories")) or {}
        for category in sorted(categories):
            ids = categories[category]
            print("  %s (%d): %s" % (category, len(ids), ", ".join(ids)))
    return 0


def _suggest_sources():
    """Printed whenever something is missing: where to go next."""
    _report("")
    _report("Art can be obtained from:")
    for name, url, kinds, _terms, _v in BROWSE_SOURCES:
        _report("  %-18s %s  (%s)" % (name, url, kinds))
    _report("")
    _report("Downloads from blocked hosts go in assets/local/ (gitignored),")
    _report("never in assets/packs/. Run --sources for the full picture.")


def cmd_require(manifest, requirements):
    catalogue = {}
    for source in manifest["sources"]:
        out_dir = _out_dir(source)
        index_path = os.path.join(out_dir, "index.json")
        if not os.path.isfile(index_path):
            continue
        with open(index_path, "r", encoding="utf-8") as fh:
            categories = (json.load(fh).get("categories")) or {}
        for category, ids in categories.items():
            present = catalogue.setdefault(category, set())
            for asset_id in ids:
                if os.path.isfile(os.path.join(out_dir, category, "%s.json" % asset_id)):
                    present.add(asset_id)

    missing = []
    for ref in requirements:
        if "/" not in ref:
            missing.append("%s (expected CATEGORY/ID, e.g. head/Afro)" % ref)
            continue
        category, asset_id = ref.rsplit("/", 1)
        if asset_id not in catalogue.get(category, ()):
            missing.append(ref)

    if missing:
        _report("missing required asset(s):")
        for ref in missing:
            print("  - %s" % ref, file=sys.stderr)
        return 1
    print("ok: %d required asset(s) present" % len(requirements))
    return 0


def cmd_fetch(manifest, force):
    node_path = shutil.which("node")
    ok_all = True
    for source in manifest["sources"]:
        sid = source["id"]
        ok, count, _ = local_status(source)
        if ok and not force:
            print("%s: already present (%d assets) -- skipping (--force to re-fetch)" % (sid, count))
            continue

        print("%s: fetching" % sid)
        try:
            _fetch_one(source, node_path)
        except FetchError as exc:
            ok_all = False
            _report("%s: FAILED -- %s" % (sid, exc))
            continue

        ok, count, problems = local_status(source)
        if ok:
            print("%s: ok -- %d assets" % (sid, count))
        else:
            ok_all = False
            _report("%s: still incomplete after fetching:" % sid)
            for problem in problems:
                print("  - %s" % problem, file=sys.stderr)
    return 0 if ok_all else 1


# --------------------------------------------------------------------------

# Where a human can legitimately get more art. These are NOT fetched -- the
# blocked ones cannot be, by design -- they are printed so that a missing
# asset ends in a URL rather than a shrug. See ../assets/SOURCES.md.
BROWSE_SOURCES = [
    (
        "Magnific / Freepik",
        "https://www.magnific.com/search?ai=excluded&format=search"
        "&last_filter=selection&last_value=1&query=2d+character&selection=1",
        "characters, backgrounds, buildings, vehicles, props",
        "download yourself; NOT redistributable, so drop into assets/local/",
        False,
    ),
    (
        "Open Peeps",
        "https://openpeeps.com",
        "heads, faces, hair, bodies",
        "CC0-1.0 -- already vendored in assets/packs/open-peeps",
        True,
    ),
    (
        "Humaaans",
        "https://humaaans.com",
        "heads, hair, bodies, legs, shoes",
        "CC0-1.0 -- already vendored in assets/packs/humaaans",
        True,
    ),
    (
        "unDraw",
        "https://undraw.co",
        "scenes, props, backgrounds",
        "MIT -- redistributable, but not currently vendored",
        False,
    ),
]

LOCAL_DIR = os.path.join(ASSETS_DIR, "local")


def cmd_sources():
    """Print every place art can come from, and on what terms."""
    def _show(group, want):
        print("%s\n" % group)
        for name, url, kinds, terms, vendored in BROWSE_SOURCES:
            if vendored is not want:
                continue
            print("  %-18s %s" % (name, url))
            print("  %-18s %s\n  %-18s %s\n" % ("", kinds, "", terms))

    _show("Vendored and ready to use:", True)
    _show("Download yourself, then drop into assets/local/:", False)

    print("assets/local/ is gitignored in full, so art you download stays yours")
    print("and is never redistributed by this repository.")
    print("\nFull reasoning: assets/SOURCES.md")
    return 0


def build_parser():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--check", action="store_true", help="verify only; fetch nothing")
    ap.add_argument("--force", action="store_true", help="re-fetch every source, even if present")
    ap.add_argument("--list", action="store_true", help="print every known asset id by category")
    ap.add_argument(
        "--sources", action="store_true",
        help="print where more art can be obtained, and on what licence terms",
    )
    ap.add_argument(
        "--require", nargs="+", metavar="CATEGORY/ID",
        help="exit non-zero naming any of these assets that are absent",
    )
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.sources:
        return cmd_sources()

    manifest = load_manifest()

    if args.list:
        return cmd_list(manifest)
    if args.require:
        return cmd_require(manifest, args.require)
    if args.check:
        return cmd_check(manifest)
    return cmd_fetch(manifest, force=args.force)


if __name__ == "__main__":
    sys.exit(main())
