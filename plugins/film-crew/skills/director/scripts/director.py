"""The director's chair: one brief in, a production plan and its state out.

    director.py --paper --topic "..." --parts 2 --shorts 3 --channel mychan
    director.py --help

This script does **not** run the crew. It decides what the crew should do, in
what order, and refuses to let a stage be called finished when the artifact it
claims to have produced is missing, stale or unverified. The work itself is
done by the other skills; the model drives them. Everything here is a side
effect — parsing, planning, hashing, gating and recording — because a pipeline
whose control flow lives in Python cannot be reasoned about by the agent that
has to recover it when a render dies at two in the morning.

The state lives in ``production.json`` next to the deliverables, so a session
that is compacted, resumed on another day, or handed to a different model can
pick the production up exactly where it was left:

    director.py status .        # what is done, what is next, what failed
    director.py next .          # the exact handoff for the next stage
    director.py advance render . --episode 1 --artifact out/ep1.mp4
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import fnmatch
import functools
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

try:                                         # POSIX advisory locking; absent on
    import fcntl                             # Windows, where the rev guard alone
except ImportError:                          # has to do
    fcntl = None

# The crew registry lives beside this file, and is imported by path so the
# director can be run from anywhere without installing anything.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crew  # noqa: E402


def installed_styles():
    """(id, tagline) for every valid installed style, for the CLI shorthands.

    Deliberately forgiving: a broken style must not stop the director from
    starting, or one bad manifest would take the whole plugin down. `doctor`
    is where a style gets told off.
    """
    if registry is None:
        return []
    out = []
    try:
        for m in registry.discover():
            sid = m.get("id")
            if isinstance(sid, str) and sid.isidentifier() or (
                    isinstance(sid, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]*",
                                                          sid or "")):
                out.append((sid, m.get("tagline") or ""))
    except Exception:                                   # pragma: no cover
        return []
    return sorted(set(out))


def _load_registry():
    """Import the style registry from whichever skill declares it.

    Which skill owns the looks is a fact in that skill's `crew.json`, not a
    path written into the director. Swap the production designer for another
    implementation and this follows it.
    """
    try:
        found = crew.load_crew().style_provider()
    except crew.CrewError:
        return None
    if not found:
        return None
    _, scripts, _ = found
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    try:
        import registry as _r
        return _r
    except ImportError:                                # pragma: no cover
        return None


registry = _load_registry()

HERE = os.path.dirname(os.path.abspath(__file__))
SKILLS = os.path.normpath(os.path.join(HERE, "..", ".."))

SCHEMA = 1
STATE = "production.json"
LOCK = ".director.lock"

DEFAULT_RUNTIME_MIN = 13.0
MAX_RUNTIME_MIN = 600.0
DEFAULT_SHORT_SEC = 40


# ---------------------------------------------------------------- the plan --

# The pipeline is not written down here. Each crew skill ships a `crew.json`
# declaring the stages it provides, what they emit and what they depend on, and
# `crew.py` assembles those into an ordered graph at startup. Installing a
# skill is therefore adding a folder, and removing one is deleting it — no edit
# to this file either way.
try:
    CREW = crew.load_crew()
except crew.CrewError as _e:
    print("director: %s" % _e, file=sys.stderr)
    raise SystemExit(2)

STAGE = CREW.stage
ORDER = CREW.order
BRIEFING = CREW.briefing

#: Stages that spend money, publish in public, or otherwise cannot be undone,
#: mapped to the stages whose artifacts they put in front of an audience. The
#: mapping is declared by the skill that owns the stage.
IRREVERSIBLE = CREW.irreversible


# --------------------------------------------------------------- utilities --


def now():
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def die(msg, code=1):
    print("director: %s" % msg, file=sys.stderr)
    raise SystemExit(code)


def say(msg=""):
    print(msg)


def slug(text, limit=48):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (s[:limit].rstrip("-") or "production")


def sha_file(path):
    """sha256 of a file, or of a directory's sorted (name, content) pairs."""
    h = hashlib.sha256()
    if os.path.isdir(path):
        for root, dirs, files in os.walk(path):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            for name in sorted(files):
                if name.startswith("."):
                    continue
                p = os.path.join(root, name)
                h.update(os.path.relpath(p, path).encode())
                with open(p, "rb") as fh:
                    for chunk in iter(lambda: fh.read(1 << 20), b""):
                        h.update(chunk)
    else:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    return h.hexdigest()


def write_atomic(path, text):
    """Write via a temp file in the *same directory*, then rename.

    Same directory matters: ``os.replace`` is only atomic within a filesystem,
    and ``/tmp`` is frequently a different one.
    """
    d = os.path.dirname(os.path.abspath(path)) or "."
    try:
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".%s." % os.path.basename(path))
    except OSError as e:
        die("cannot write %s: %s — check the directory exists and is writable"
            % (path, e.strerror or e))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException as e:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        if isinstance(e, OSError):                 # full disk, RO remount
            die("cannot write %s: %s — the previous state file is intact"
                % (path, e.strerror or e))
        raise


def toolchain():
    """A fingerprint of the tools a render depends on.

    An ffmpeg upgrade can change the output; a cache key that ignores it will
    happily call a stale render current.
    """
    out = {"python": "%d.%d" % sys.version_info[:2]}
    for b in ("ffmpeg",):
        path = shutil.which(b)
        if not path:
            out[b] = None
            continue
        try:
            r = subprocess.run([path, "-version"], capture_output=True,
                               text=True, timeout=20)
            out[b] = (r.stdout.splitlines() or [""])[0].strip()[:80]
        except (OSError, subprocess.SubprocessError):
            out[b] = "unknown"
    return out


# ------------------------------------------------------------------- state --


def state_path(root):
    return os.path.join(root, STATE)


REQUIRED_STATE = ("id", "root", "brief", "style", "episodes", "shorts",
                  "rev", "approvals")


def load(root):
    """Read the production, refusing to run on a state file we cannot trust.

    Everything here is a file a human can open and edit, so every way it can be
    wrong has to produce a sentence rather than a traceback: absent, truncated
    mid-write, hand-mangled into invalid JSON, or valid JSON that is simply not
    a production.
    """
    p = state_path(root)
    if not os.path.isfile(p):
        die("no %s in %s — run `director.py --topic ...` first"
            % (STATE, os.path.abspath(root)))
    try:
        with open(p, encoding="utf-8") as fh:
            st = json.load(fh)
    except json.JSONDecodeError as e:
        die("%s is not valid JSON (line %d, column %d: %s) — it was hand-edited "
            "or a write was interrupted; restore it or re-plan the production"
            % (p, e.lineno, e.colno, e.msg))
    except OSError as e:
        die("cannot read %s: %s" % (p, e.strerror or e))
    if not isinstance(st, dict):
        die("%s should hold a production object, found %s"
            % (p, type(st).__name__))
    if st.get("schema") != SCHEMA:
        die("%s is schema %s, this director speaks %s"
            % (p, st.get("schema"), SCHEMA))
    missing = [k for k in REQUIRED_STATE if k not in st]
    if missing:
        die("%s is missing %s — it is not a complete production"
            % (p, ", ".join(missing)))
    for k, want in (("brief", dict), ("episodes", list),
                    ("shorts", list), ("approvals", list)):
        if not isinstance(st[k], want):
            die("%s: %r should be a %s, found %s"
                % (p, k, want.__name__, type(st[k]).__name__))
    if not isinstance(st["rev"], int) or isinstance(st["rev"], bool):
        die("%s: 'rev' should be a whole number, found %r" % (p, st["rev"]))
    return st


@contextlib.contextmanager
def production_lock(root):
    """Serialise the whole read-modify-write against other directors.

    The `rev` guard on its own is a time-of-check/time-of-use race: two
    processes can both read rev 4, both find it unmoved, and both write rev 5 —
    the second silently discarding the first, while both report success. An
    advisory lock held across the read *and* the write closes that window; the
    `rev` check stays behind it to catch anything that edited the file by hand
    in between.
    """
    if not os.path.isdir(root):
        yield                                # nothing to lock yet; the rev
        return                               # guard covers the first write
    if fcntl is None:
        # No flock (Windows). `expect_rev` alone is a time-of-check race: two
        # processes read the same rev, both pass, both write. Rather than
        # pretend otherwise, refuse — unless the caller has said they are the
        # only one running.
        if os.environ.get("DIRECTOR_NO_LOCK") == "1":
            yield
            return
        die("this platform has no file locking (no fcntl), so two directors "
            "running at once would silently discard each other's work.\n"
            "  If you are certain nothing else is touching %s, set "
            "DIRECTOR_NO_LOCK=1." % root)
    path = os.path.join(root, LOCK)
    try:
        fh = open(path, "a+")
    except OSError as e:
        die("cannot take the production lock at %s: %s — refusing to run "
            "unserialised, because a second director would silently discard "
            "this one's work" % (path, e.strerror or e))
    try:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            say("director: waiting for another director to finish in %s ..." % root)
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


def locked(fn):
    """Wrap a mutating command so its load/modify/save cannot interleave."""
    @functools.wraps(fn)
    def inner(args):
        with production_lock(getattr(args, "root", ".") or "."):
            return fn(args)
    return inner


def save(root, st, expect_rev=None):
    """Persist state, refusing to clobber a concurrent writer's revision."""
    p = state_path(root)
    if expect_rev is not None and os.path.isfile(p):
        with open(p, encoding="utf-8") as fh:
            current = json.load(fh).get("rev")
        if current != expect_rev:
            die("%s changed underneath this command (rev %s, expected %s) — "
                "another director is running; re-read with `status` and retry"
                % (STATE, current, expect_rev))
    st["rev"] = int(st.get("rev", 0)) + 1
    st["updated"] = now()
    write_atomic(p, json.dumps(st, indent=2) + "\n")


def blank_stage():
    return {"status": "pending", "key": None, "artifacts": [], "attempts": [],
            "note": None}


def units(st):
    """Every (kind, index, unit) the production fans out into."""
    out = [("production", 0, st)]
    for i, e in enumerate(st.get("episodes") or [], 1):
        out.append(("episode", i, e))
    for i, s in enumerate(st.get("shorts") or [], 1):
        out.append(("short", i, s))
    return out


def unit_for(st, stage, episode=None, short=None):
    """The dict holding a stage record, plus a label for messages.

    Bounds are checked explicitly rather than left to `IndexError`, because a
    negative index is *valid* Python: `--episode -1` would quietly count back
    from the end and mark a different episode done while the confirmation line
    still said "episode -1".
    """
    scope = STAGE[stage]["scope"]
    if episode is not None and short is not None:
        die("pass either --episode or --short for %r, not both" % stage)
    if scope == "production":
        # `is not None`, not truthiness: `--episode 0` is a mistake worth
        # reporting, and `0` is falsy.
        if episode is not None or short is not None:
            die("stage %r is per-production — drop --episode/--short" % stage)
        return st, "production"

    def pick(seq, n, kind):
        if n is None:
            die("stage %r is per-%s — pass --%s N" % (stage, kind, kind))
        if n < 1 or n > len(seq):
            die("this production has no %s %d — it has %d"
                % (kind, n, len(seq)))
        return seq[n - 1], "%s %d" % (kind, n)

    if scope == "short" or (scope == "deliverable" and short is not None):
        if scope == "short" and episode is not None:
            die("stage %r is per-short — use --short, not --episode" % stage)
        return pick(st.get("shorts") or [], short, "short")
    if scope == "episode" and short is not None:
        die("stage %r is per-episode — use --episode, not --short" % stage)
    return pick(st.get("episodes") or [], episode, "episode")


def rec(unit, stage):
    return unit.setdefault("stages", {}).setdefault(stage, blank_stage())


# --------------------------------------------------------------- cache keys --


def unit_kind(st, unit):
    if unit is st:
        return "production"
    return "short" if "from" in unit else "episode"


def upstreams(st, unit, stage, _seen=None):
    """`[(upstream_stage, the unit that holds it)]`, resolved across scopes.

    Three things have to be got right here, and getting them wrong in three
    separate places is how a pipeline ends up unable to finish:

    * a Short's `cut` needs the beat plan from **the episode it was cut from**,
      not from the Short, which has no board of its own;
    * `package` and `publish` are per *deliverable*, and an episode is finished
      by `render` where a Short is finished by `shoot`;
    * a stage the user explicitly skipped is **not a blocker**, but it does not
      erase what it stood on either. `--skip research` must let scripts run;
      `--skip lint` must still leave the voice booth waiting on the punched-up
      script rather than on nothing at all.
    """
    _seen = (_seen or set()) | {stage}
    out = []
    for up in _needs_of(st, unit, stage):
        if not active(st, up):
            # A skipped stage is not a blocker, but neither does it sever the
            # chain: `--skip lint` must leave `voice` waiting on `punchup`, not
            # on nothing at all. Contract the skipped node onto whatever it
            # itself depended on.
            if up not in _seen:
                out.extend(upstreams(st, unit, up, _seen))
            continue
        out.append((up, _holder(st, unit, up)))

    seen, uniq = set(), []
    for up, holder in out:
        if (up, id(holder)) not in seen:
            seen.add((up, id(holder)))
            uniq.append((up, holder))
    return uniq


def _needs_of(st, unit, stage):
    needs = STAGE[stage]["needs"]
    if isinstance(needs, dict):
        needs = needs.get(unit_kind(st, unit)) or []
    return list(needs)


def source_episode(st, unit):
    """Which episode a Short is cut from, or ``None`` if nobody has said.

    Guessing is not available here. A Short silently keyed against episode 1's
    board would validate, cache and render against the wrong film, and nothing
    downstream would look wrong enough to notice.
    """
    eps = st.get("episodes") or []
    n = (unit.get("from") or {}).get("episode")
    if n is None and len(eps) == 1:
        return eps[0]                        # only one candidate; not a guess
    if isinstance(n, int) and 1 <= n <= len(eps):
        return eps[n - 1]
    return None


def _holder(st, unit, up):
    scope = STAGE[up]["scope"]
    if scope == "production":
        return st
    if scope == "episode" and unit_kind(st, unit) == "short":
        return source_episode(st, unit)
    return unit


def cache_key(st, unit, stage):
    """What this stage's output depends on.

    Upstream artifact hashes, the stage's slice of the brief, the style and its
    version, and the toolchain. If any of those move, the key moves, and the
    stage is stale no matter what its status says.

    Upstream *keys* are folded in as well as upstream artifact hashes, so that a
    change propagates through a stage that emits no artifacts of its own. Hashes
    alone cannot do this: `lint` has no file to notice had changed, so without
    the upstream key a re-linted episode would resurrect the stale voice, board
    and render sitting behind it.
    """
    parts = {
        "stage": stage,
        "brief": {k: st["brief"].get(k) for k in
                  ("topic", "runtime_min", "language", "aspect", "seed")},
        "style": "%s@%s" % (st["style"].get("id"), st["style"].get("version")),
        "tools": st.get("tools") or {},
        "upstream": {},
    }
    if stage in ("cut", "shoot"):
        parts["from"] = unit.get("from")
    for up, source in upstreams(st, unit, stage):
        if source is None:
            parts["upstream"][up] = "unassigned"
            continue
        r = (source.get("stages") or {}).get(up) or {}
        parts["upstream"][up] = {
            "artifacts": sorted(a.get("sha256", "") for a in r.get("artifacts") or []),
            "key": r.get("key"),
        }
    return hashlib.sha256(
        json.dumps(parts, sort_keys=True).encode()).hexdigest()[:16]


def rel_to_root(st, p):
    """Record an artifact path relative to the production, symlinks and all.

    `os.path.abspath` resolves the cwd but not the argument, and on macOS the
    cwd of a shell sitting in /tmp reports as /private/tmp. Mixing the two
    yields `../../private/tmp/...`, which then fails to resolve back through the
    /tmp symlink and makes a stage that really is finished look `missing`.
    Resolve both ends the same way, and keep an outside-the-production artifact
    absolute rather than describing it as a pile of `..`.
    """
    real = os.path.realpath(p)
    root = os.path.realpath(st["root"])
    rel = os.path.relpath(real, root)
    return real if rel.startswith(os.pardir) else rel


def stage_state(st, unit, stage, _seen=None):
    """The *effective* status, which is not always the recorded one.

    A stage is only `done` if it is *still* done: its cache key must match, its
    artifacts must exist and still hash to what was recorded, and every stage it
    depends on must itself be effectively done. That last clause is what makes a
    rewrite propagate through a stage that emits nothing of its own.
    """
    if not active(st, stage):
        return "skipped"
    r = rec(unit, stage)
    if r["status"] != "done":
        return r["status"]
    if r.get("key") != cache_key(st, unit, stage):
        return "stale"
    for a in r.get("artifacts") or []:
        p = a["path"] if os.path.isabs(a["path"]) else os.path.join(st["root"], a["path"])
        if not os.path.exists(p):
            return "missing"
        if a.get("sha256") and sha_file(p) != a["sha256"]:
            return "changed"

    _seen = _seen or set()
    if (id(unit), stage) in _seen:           # the stage table is a DAG; if a
        return "stale"                       # bad edit makes a cycle, fail closed
    _seen = _seen | {(id(unit), stage)}
    for up, source in upstreams(st, unit, stage):
        if source is None:
            return "blocked"
        if stage_state(st, source, up, _seen) not in ("done", "skipped"):
            return "stale"
    return "done"


def ready(st, unit, stage):
    """Is every upstream stage genuinely done?  Returns a list of blockers."""
    blockers = []
    for up, source in upstreams(st, unit, stage):
        if source is None:
            blockers.append(
                "this Short has no source episode, so %r cannot be resolved — "
                "set it with `--from-episode N`" % up)
            continue
        s = stage_state(st, source, up)
        if s not in ("done", "skipped"):
            blockers.append("%s is %s" % (up, s))
    return blockers


# --------------------------------------------------------------- the brief --


def parse_runtime(text):
    """`13m`, `8:30`, `480s`, `13` → minutes as a float."""
    t = str(text).strip().lower()
    m = re.fullmatch(r"(\d+):(\d{1,2})", t)
    if m:
        return int(m.group(1)) + int(m.group(2)) / 60.0
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(m|min|mins|minutes)?", t)
    if m:
        return float(m.group(1))
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(s|sec|secs|seconds)", t)
    if m:
        return float(m.group(1)) / 60.0
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(h|hr|hrs|hours)", t)
    if m:
        return float(m.group(1)) * 60.0
    raise ValueError("cannot read %r as a runtime — try 13m, 8:30 or 480s" % text)


def choose_style(args, topic):
    """Explicit flag, else the ranker, else refuse.

    The ranker is allowed to *suggest*; it is only allowed to *decide* when it
    is not a close call, because topic words say very little about how a subject
    should look.
    """
    if registry is None:
        die("cannot import the style registry from %s — is the "
            "production-designer skill installed alongside this one?" % REGISTRY)
    if args.style:
        s = registry.resolve(args.style)
        return s, {"how": "explicit", "score": None}

    scored = registry.rank(topic)
    if not scored:
        die("no styles are installed under %s" % registry.STYLES)
    (top, hit, s) = scored[0]
    runner = scored[1][0] if len(scored) > 1 else None
    if top <= 0:
        die("no style suits this topic (best was %s at %+d).\n"
            "  Pick one explicitly: --style <id>. Available:\n    %s"
            % (s.get("id"), top,
               "\n    ".join("%-12s %s" % (x.get("id"), x.get("tagline", ""))
                             for _, _, x in scored)))
    if runner is not None and top - runner < 3:
        die("two styles score within one need of each other (%s %+d, %s %+d).\n"
            "  That is too close to guess — pass --style <id>."
            % (s.get("id"), top, scored[1][2].get("id"), runner))
    return s, {"how": "ranked", "score": top, "matched": hit}


def build(args):
    """Create a production directory and its state file."""
    topic = args.topic
    if not topic and args.source:
        topic = "adaptation of %s" % os.path.basename(args.source)
    if not topic:
        die("nothing to make — pass --topic \"...\" or --source <file|url>\n"
            "  Try: director.py --help")

    style, how = choose_style(args, topic)

    if args.aspect and args.aspect not in (style.get("aspects") or []):
        die("style %r renders %s, not %s — pick another style or drop --aspect"
            % (style["id"], "/".join(style.get("aspects") or ["?"]), args.aspect))

    if args.parts < 1:
        die("--parts %d makes no sense — a production has at least one part"
            % args.parts)
    if args.shorts < 0:
        die("--shorts %d makes no sense — pass 0 for none" % args.shorts)
    parts = args.parts
    if args.only and args.skip:
        both = sorted(set(args.only) & set(args.skip))
        if both:
            die("%s is in both --only and --skip; decide which"
                % ", ".join(both))

    # Publishing is gated on approving everything that goes out, and that set
    # is derived from the stages that produce it. A plan that publishes without
    # them cannot be approved at all — better to say so now than to let someone
    # drive a whole production into a gate that can never open.
    def planned(name):
        if args.only:
            return name in args.only
        return not (args.skip and name in args.skip)

    if args.publish and planned("publish"):
        producers = ["package"]
        if parts >= 1:
            producers.append("render")
        if args.shorts:
            producers.append("shoot")
        need = [n for n in producers if not planned(n)]
        if need:
            names = " and ".join(need)
            die("this plan publishes but leaves out %s.\n"
                "  Publishing requires approving every file that goes out, and "
                "%s %s what goes out — without %s there is nothing to approve, "
                "so `advance publish` could never run.\n"
                "  Either keep %s, or drop publish."
                % (names, names, "produces" if len(need) == 1 else "produce",
                   "it" if len(need) == 1 else "them", names))
    # A brief key that no installed stage consumes cannot be honoured. Said
    # here rather than discovered later as a pipeline that quietly stops short.
    for key, asked in (("publish", bool(args.publish)),
                       ("channel", bool(args.channel))):
        if asked and not CREW.consumers(key):
            die("nothing installed can %s. No crew skill declares a stage "
                "that depends on %r, so this production would plan straight "
                "past it.\n  Installed: %s"
                % (key, key, ", ".join(sorted(CREW.skills))))

    runtime = args.runtime
    if runtime is None:
        runtime = DEFAULT_RUNTIME_MIN
        runtime_source = "default"
    else:
        runtime_source = "given"
    if not 1 <= runtime <= MAX_RUNTIME_MIN:
        die("--runtime %g min is outside 1..%d — that is not a runtime, it is "
            "a typo" % (runtime, MAX_RUNTIME_MIN))

    root = os.path.realpath(args.out or slug(topic))
    if os.path.exists(state_path(root)) and not args.force:
        die("%s already holds a production — use --force to start it over, or "
            "`director.py status %s` to see where it got to" % (root, root))
    # Checked again below while holding the lock. This early copy only exists
    # so the common mistake is reported before the whole brief is validated.

    st = {
        "schema": SCHEMA,
        "rev": 0,
        "id": slug(topic),
        "root": root,
        "created": now(),
        "updated": now(),
        "brief": {
            "topic": topic,
            "source": args.source,
            "parts": parts,
            "runtime_min": runtime,
            "runtime_source": runtime_source,
            "shorts": args.shorts,
            "short_seconds": args.short_seconds,
            "aspect": args.aspect or (style.get("aspects") or ["16:9"])[0],
            "language": args.language,
            "voice": args.voice,
            "seed": args.seed,
            "channel": args.channel,
            "privacy": args.privacy,
            "publish": bool(args.publish),
        },
        "style": {"id": style["id"], "name": style.get("name"),
                  "version": style.get("version"), "dir": style["dir"], **how},
        "tools": toolchain(),
        "stages": {},
        "episodes": [{"n": i + 1, "title": None, "stages": {}}
                     for i in range(parts)],
        "shorts": [{"n": i + 1, "from": {"episode": None, "hook": None},
                    "stages": {}} for i in range(args.shorts)],
        "approvals": [],
        "only": args.only,
        "skip": args.skip,
        "unverified": (bool(args.skip and "research" in args.skip)
                       or bool(args.only and "research" not in args.only)),
    }
    if args.dry_run:
        say(render_plan(st))
        say("\n(--dry-run: nothing written)")
        return 0
    os.makedirs(root, exist_ok=True)

    # Replanning over an existing production is a write like any other. Without
    # the lock, `--force` can land in the middle of an `advance` and one of the
    # two disappears.
    with production_lock(root):
        # Re-check inside the lock. Two first-time builds can both pass the
        # early check, and without this the loser silently overwrites the
        # winner instead of being told to use --force.
        if os.path.exists(state_path(root)) and not args.force:
            die("%s already holds a production — use --force to start it "
                "over, or `director.py status %s` to see where it got to"
                % (root, root))
        save(root, st)
    say(render_plan(st))
    say("\nwrote %s" % state_path(root))
    say("next:  director.py next %s" % root)
    return 0


# ------------------------------------------------------------------ output --


def active(st, stage):
    if st.get("only"):
        return stage in st["only"]
    return stage not in (st.get("skip") or [])


def render_plan(st):
    b, s = st["brief"], st["style"]
    L = []
    L.append("PRODUCTION  %s" % st["id"])
    L.append("  topic     %s" % b["topic"])
    L.append("  style     %s (%s)%s" % (
        s["id"], s.get("name"),
        "" if s.get("how") == "explicit"
        else "  [chosen by rank %+d: %s]" % (s.get("score") or 0,
                                             ", ".join(s.get("matched") or []) or "—")))
    L.append("  shape     %d x %.0f min%s%s" % (
        b["parts"], b["runtime_min"],
        " + %d Shorts" % b["shorts"] if b["shorts"] else "",
        "   (runtime defaulted — pass --runtime to set it)"
        if b.get("runtime_source") == "default" else ""))
    L.append("  aspect    %s   language %s   seed %s"
             % (b["aspect"], b["language"], b["seed"]))
    L.append("  channel   %s" % (b["channel"] or "(none — will not publish)"))
    if st.get("unverified"):
        L.append("  WARNING   research skipped: nothing in this production is "
                 "fact-checked and packaging must not claim it is")
    L.append("")
    L.append("PLAN")
    for kind, i, unit in units(st):
        stages = [n for n in ORDER
                  if STAGE[n]["scope"] == kind
                  or (STAGE[n]["scope"] == "deliverable" and kind in ("episode", "short"))]
        stages = [n for n in stages if wanted(st, n)]
        if not stages:
            continue
        label = "production" if kind == "production" else "%s %d" % (kind, i)
        L.append("  %-12s %s" % (label, " -> ".join(
            "%s%s" % (n, "" if stage_state(st, unit, n) == "pending"
                      else "[%s]" % stage_state(st, unit, n))
            for n in stages)))
    return "\n".join(L)


def cmd_status(args):
    st = load(args.root)
    if args.json:
        out = {"id": st["id"], "style": st["style"]["id"],
               "unverified": bool(st.get("unverified")), "units": []}
        for kind, i, unit in units(st):
            # The same filter the printed plan uses. Reporting `publish` as
            # pending on a production that will never publish — or listing a
            # deliverable stage against the production unit, which holds no
            # deliverable — makes the JSON disagree with the plan beside it.
            out["units"].append({
                "kind": kind, "n": i,
                "stages": {n: stage_state(st, unit, n)
                           for n in ORDER
                           if (STAGE[n]["scope"] == kind
                               or (STAGE[n]["scope"] == "deliverable"
                                   and kind in ("episode", "short")))
                           and wanted(st, n)}})
        print(json.dumps(out, indent=2))
        return 0
    say(render_plan(st))
    fails = []
    for kind, i, unit in units(st):
        for n, r in (unit.get("stages") or {}).items():
            if stage_state(st, unit, n) in ("failed", "blocked"):
                fails.append("  %-12s %-9s %s" % (
                    "production" if kind == "production" else "%s %d" % (kind, i),
                    n, r.get("note") or (r["attempts"][-1].get("note")
                                         if r.get("attempts") else "")))
    if fails:
        say("\nFAILED")
        say("\n".join(fails))
    return 0


def wanted(st, stage):
    """Is this stage part of *this* production at all?

    Beyond `--only`/`--skip`, a stage can declare in its `crew.json` what the
    brief must contain for it to apply — packaging needs somewhere to go, and
    publishing additionally needs to have been asked for. That condition
    belongs to the skill that owns the stage, not to this file, so a new skill
    can gate itself without the director learning its name.
    """
    if not active(st, stage):
        return False
    return CREW.wanted(st["brief"], stage)


def pending(st):
    """The stages that could run right now, in pipeline order."""
    out = []
    for name in ORDER:
        for kind, i, unit in units(st):
            scope = STAGE[name]["scope"]
            if scope == "production" and kind != "production":
                continue
            if scope == "episode" and kind != "episode":
                continue
            if scope == "short" and kind != "short":
                continue
            if scope == "deliverable" and kind == "production":
                continue
            if not wanted(st, name):
                continue
            if stage_state(st, unit, name) in ("done",):
                continue
            out.append((name, kind, i, unit))
    return out


def cmd_next(args):
    st = load(args.root)
    todo = pending(st)
    if not todo:
        say("nothing left — every active stage is done.")
        say("run `director.py report %s` for the wrap report." % args.root)
        return 0

    shown = 0
    for name, kind, i, unit in todo:
        blockers = ready(st, unit, name)
        if blockers and not args.all:
            continue
        label = "production" if kind == "production" else "%s %d" % (kind, i)
        info = STAGE[name]
        say("=" * 68)
        say("STAGE   %s   (%s)" % (name, label))
        say("CREW    %s" % info["crew"])
        say("WHY     %s" % BRIEFING[name])
        if info["emits"]:
            say("EMITS   %s" % ", ".join(info["emits"]))
        if blockers:
            say("BLOCKED %s" % "; ".join(blockers))
        if name in IRREVERSIBLE:
            say("GATE    irreversible — needs `director.py approve %s %s%s "
                "--artifact <file>` first"
                % (name, args.root,
                   "" if kind == "production" else " --%s %d" % (kind, i)))
        if st.get("unverified") and name == "package":
            say("GATE    research was skipped — metadata may not claim sourcing")
        st_state = stage_state(st, unit, name)
        if st_state in ("stale", "missing", "changed"):
            say("NOTE    previously done but now %s — an upstream artifact moved"
                % st_state)
        say("RECORD  director.py advance %s %s%s --artifact <path>"
            % (name, args.root,
               "" if kind == "production" else " --%s %d" % (kind, i)))
        shown += 1
        if not args.all:
            break
    if not shown:
        say("every remaining stage is blocked. `director.py status %s` shows why."
            % args.root)
        return 1
    return 0


def going_out(st, unit, stage):
    """The artifacts an irreversible stage is about to act on.

    Not the ones the caller chose to name. `advance publish --artifact
    README.md` would otherwise satisfy a gate that was supposed to be guarding
    a finished film: the caller both proposes what is approved and reports what
    happened, so the approval says nothing. Deriving the set from the recorded
    upstream work makes the question "is *this cut* cleared to go out?", which
    is the only question worth asking.
    """
    out, seen = [], set()

    # `publish.json` is what the uploader actually reads — it names the video,
    # the thumbnail and the metadata file independently of anything recorded
    # here. Approving only the director's own records would leave the uploader
    # free to attach a different video and a thumbnail that was never in the
    # bundle at all, which is the whole gate defeated.
    if stage == "publish":
        for key, path in publish_targets(st, unit).items():
            if not os.path.exists(path):
                continue
            rel = rel_to_root(st, path)
            seen.add(rel)
            out.append(("publish.json:%s" % key,
                        {"path": rel, "sha256": sha_file(path)}))

        # A Short's title, description and tags live in the batch spec, not in
        # `publish.json`. Leaving it out would approve the picture and let the
        # words be rewritten afterwards, so the uploader now insists on it —
        # and would refuse every Short if the director did not put it here.
        if unit_kind(st, unit) == "short":
            spec = os.path.join(st["root"], SHORTS_SPEC)
            if os.path.exists(spec) and SHORTS_SPEC not in seen:
                seen.add(SHORTS_SPEC)
                out.append(("shorts_publish.json",
                            {"path": SHORTS_SPEC, "sha256": sha_file(spec)}))

    for up in IRREVERSIBLE.get(stage, ()):
        for a in (rec(unit, up).get("artifacts") or []):
            if a.get("path") not in seen:
                seen.add(a.get("path"))
                out.append((up, a))
    return out


#: What `publish.json` calls each thing the uploader attaches.
PUBLISH_KEYS = ("video", "thumbnail", "metadata")

#: Where the Shorts batch keeps the text it will publish. Approving a Short
#: has to cover this file, not only the video.
SHORTS_SPEC = "meta/shorts_publish.json"


def publish_targets(st, unit):
    """The files `head-of-marketing`'s uploader will attach for this unit.

    Read here rather than imported, so the director does not depend on the
    marketing skill being installed. An absent or unreadable file simply means
    "nothing declared" — the recorded artifacts are then the whole bundle.

    A `publish.json` describes **one** upload, while a production has many
    units. It is therefore only treated as this unit's when the video it names
    is this unit's own render or shoot. Otherwise it is describing a different
    upload, and dragging its thumbnail into this bundle would ask for approval
    of a file that has nothing to do with this cut. Nothing is lost by
    ignoring it: the uploader verifies `publish.lock.json` before attaching
    anything, so a `publish.json` pointing somewhere unapproved is refused
    there.
    """
    try:
        with open(os.path.join(st["root"], "publish.json"),
                  encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError):
        return {}
    if not isinstance(cfg, dict):
        return {}
    out = {}
    for k in PUBLISH_KEYS:
        v = cfg.get(k)
        if isinstance(v, str) and v:
            out[k] = os.path.join(st["root"], v)
    video = out.get("video")
    mine = {a.get("path") for up in ("render", "shoot")
            for a in (rec(unit, up).get("artifacts") or [])}
    if not video or rel_to_root(st, video) not in mine:
        return {}
    return out


# ---------------------------------------------------------------- mutation --


@locked
def cmd_advance(args):
    st = load(args.root)
    rev = st["rev"]
    stage = args.stage
    if stage not in STAGE:
        die("unknown stage %r — one of: %s" % (stage, ", ".join(ORDER)))
    unit, label = unit_for(st, stage, args.episode, args.short)

    if getattr(args, "from_episode", None) is not None:
        if unit_kind(st, unit) != "short":
            die("--from-episode describes where a Short was cut from; %s is "
                "not a Short" % label)
        n, eps = args.from_episode, st.get("episodes") or []
        if not 1 <= n <= len(eps):
            die("this production has no episode %d — it has %d" % (n, len(eps)))
        unit.setdefault("from", {})["episode"] = n
    if getattr(args, "from_hook", None):
        if unit_kind(st, unit) != "short":
            die("--from-hook describes a Short's source; %s is not a Short"
                % label)
        unit.setdefault("from", {})["hook"] = args.from_hook

    if unit_kind(st, unit) == "short" and source_episode(st, unit) is None:
        die("%s has no source episode. A Short cut against the wrong film "
            "would validate and render without ever looking wrong, so this is "
            "not guessed:\n  director.py advance %s %s --short %d "
            "--from-episode N ..."
            % (label, stage, args.root, args.short or 0))
    r = rec(unit, stage)

    if args.fail is not None:
        r["status"] = "failed"
        r["note"] = args.fail
        r["attempts"].append({"at": now(), "ok": False, "note": args.fail})
        save(args.root, st, expect_rev=rev)
        say("%s / %s: failed — %s" % (label, stage, args.fail))
        say("downstream stages are blocked until it is redone.")
        return 0

    blockers = ready(st, unit, stage)
    if blockers and not args.force:
        die("%s / %s is not ready: %s\n"
            "  Fix upstream first, or pass --force if you know better."
            % (label, stage, "; ".join(blockers)))

    if stage == "publish" and not st["brief"].get("publish"):
        # Gating only the *plan* on consent would be theatre: the plan says
        # "will not publish" while `advance publish` uploads anyway. Consent is
        # checked where the irreversible thing actually happens.
        if not getattr(args, "allow_publish", False):
            die("this production was not set up to publish — %s.\n"
                "  Approving files is not the same as deciding to release "
                "them.\n"
                "  Either re-plan with --publish <channel>, or say so here:\n"
                "    director.py advance publish %s %s --allow-publish "
                "--artifact <file>"
                % ("no channel is set" if not st["brief"].get("channel")
                   else "the channel %r was recorded for the metadata only"
                        % st["brief"]["channel"],
                   args.root, scope_flag(args)))
        if not st["brief"].get("channel"):
            die("--allow-publish still needs somewhere to publish to; re-plan "
                "with --publish <channel>")
        st["brief"]["publish"] = True
        st["brief"]["publish_authorised_at"] = now()
        say("release authorised at the command line, not in the plan.")

    if stage in IRREVERSIBLE:
        bundle = going_out(st, unit, stage)
        if not bundle:
            die("%s / %s has nothing to act on — the work it would send out is "
                "not recorded yet." % (label, stage))
        approved = {a["sha256"] for a in st["approvals"]
                    if a["scope"] == stage and a.get("unit") == label}
        missing = [a for _, a in bundle if a.get("sha256") not in approved]
        if missing:
            die("%s / %s is irreversible, and %d of the %d file(s) it would "
                "send out %s not approved:\n    %s\n"
                "  Approval covers exact bytes, one unit, and the whole "
                "bundle — naming a different file at `advance` does not "
                "stand in for it. Approve what is going out:\n"
                "    director.py approve %s %s %s --artifact %s"
                % (label, stage, len(missing), len(bundle),
                   "is" if len(missing) == 1 else "are",
                   "\n    ".join(a["path"] for a in missing),
                   stage, args.root, scope_flag(args),
                   " ".join(a["path"] for a in missing)))

    arts = []
    for p in args.artifact or []:
        if not os.path.exists(p):
            die("artifact %r does not exist — a stage is not done until its "
                "output is on disk" % p)
        arts.append({
            "path": rel_to_root(st, p),
            "sha256": sha_file(p),
            "bytes": (os.path.getsize(p) if os.path.isfile(p)
                      else sum(os.path.getsize(os.path.join(d, f))
                               for d, _, fs in os.walk(p) for f in fs)),
        })
    odd = [a["path"] for a in arts
           if not looks_emitted(stage, a["path"],
                                os.path.join(st["root"], a["path"]))]
    if odd and not args.force:
        die("%s emits %s; recorded %s instead.\n"
            "  Downstream stages hash these by name, so the wrong file here "
            "propagates quietly. Pass --force if the layout really differs."
            % (stage, ", ".join(STAGE[stage]["emits"]),
               ", ".join(repr(o) for o in odd)))
    if STAGE[stage]["emits"] and not arts and not args.force:
        die("%s must emit %s — pass --artifact <path>, or --force if this "
            "stage genuinely produced nothing"
            % (stage, ", ".join(STAGE[stage]["emits"])))

    r["status"] = "done"
    r["artifacts"] = arts
    r["key"] = cache_key(st, unit, stage)
    r["note"] = args.note
    r["attempts"].append({"at": now(), "ok": True, "note": args.note})
    save(args.root, st, expect_rev=rev)
    say("%s / %s: done%s" % (label, stage,
                             "  (%s)" % ", ".join(a["path"] for a in arts) if arts else ""))
    nxt = pending(st)
    if nxt:
        n, kind, i, _ = nxt[0]
        say("next: %s (%s)" % (n, "production" if kind == "production"
                               else "%s %d" % (kind, i)))
    return 0


def looks_emitted(stage, relpath, fullpath=None):
    """Does a recorded artifact resemble what the stage said it would emit?

    Only a resemblance: `emits` names shapes ("*.mp4", "vo/"), and a production
    is free to put them anywhere under the root. Enough to catch a genuine
    mix-up — recording the storyboard as the render — without dictating layout.

    A trailing slash in `emits` means a directory, and is checked as one: a
    *file* called `vo` is not a folder of narration, and a *directory* called
    `movie.mp4` is not a render. Matching on the name alone would accept both.
    """
    want = STAGE[stage]["emits"]
    if not want:
        return True
    base = os.path.basename(relpath.rstrip("/")) or relpath
    for w in want:
        wants_dir = w.endswith("/")
        w = w.rstrip("/")
        named = (fnmatch.fnmatch(base, w) or fnmatch.fnmatch(relpath, w)
                 or ("/" in w and relpath.endswith(w))
                 or ("*" not in w and os.path.basename(w) == base))
        if not named:
            continue
        if fullpath and os.path.exists(fullpath):
            if wants_dir != os.path.isdir(fullpath):
                continue
        return True
    return False


def scope_flag(args):
    """Re-render whichever of --episode/--short the caller used."""
    if getattr(args, "short", None):
        return "--short %d" % args.short
    if getattr(args, "episode", None):
        return "--episode %d" % args.episode
    return ""


@locked
def cmd_approve(args):
    st = load(args.root)
    rev = st["rev"]
    if not args.artifact:
        die("approve what, exactly? pass --artifact <file> — an approval that "
            "is not bound to a file approves nothing")
    unit, label = unit_for(st, args.stage, args.episode, args.short)
    bundle = {a["sha256"]: a["path"] for _, a in going_out(st, unit, args.stage)
              if a.get("sha256")}
    if not bundle:
        die("%s / %s has nothing to approve yet — the work it would send out "
            "is not recorded. Approving a file now would attest to nothing, "
            "so it is refused rather than banked for later."
            % (label, args.stage))
    for p in args.artifact:
        if not os.path.exists(p):
            die("cannot approve %r: it does not exist" % p)
        digest = sha_file(p)
        if digest not in bundle:
            die("%r is not part of what %s / %s would send out, so approving "
                "it would clear nothing. That bundle is:\n    %s"
                % (p, label, args.stage, "\n    ".join(sorted(bundle.values()))))
        st["approvals"].append({
            "scope": args.stage,
            "unit": label,
            "path": rel_to_root(st, p),
            "sha256": digest,
            "at": now(),
            "by": os.environ.get("USER", "?"),
        })
        say("approved for %s / %s: %s" % (label, args.stage, p))
    done = {a["sha256"] for a in st["approvals"]
            if a["scope"] == args.stage and a.get("unit") == label}
    still = sorted(v for k, v in bundle.items() if k not in done)
    if still:
        say("still unapproved for %s / %s:\n    %s"
            % (label, args.stage, "\n    ".join(still)))
    # Persist the approval BEFORE writing the external authorisation. A crash
    # between the two must leave a recorded approval and no lock, never a lock
    # the state does not know about.
    save(args.root, st, expect_rev=rev)
    if not still and args.stage == "publish" and bundle:
        if not wanted(st, "publish"):
            say("not writing %s: this production was planned to stop at "
                "package, so nothing is cleared for upload. Approval says the "
                "bytes are good; it is not consent to release them. Re-plan "
                "with --publish, or pass --allow-publish when you advance."
                % PUBLISH_LOCK)
        elif not active(st, "publish"):
            say("not writing %s: publish is not part of this plan." %
                PUBLISH_LOCK)
        else:
            write_publish_lock(st, label, bundle)
            say("wrote %s — the uploader will refuse to attach anything that "
                "does not match it." % PUBLISH_LOCK)
    say("This approval covers these exact bytes. Re-render and it lapses.")
    return 0


PUBLISH_LOCK = "publish.lock.json"


def write_publish_lock(st, label, bundle):
    """Hand the uploader the exact bytes a human agreed to.

    The uploader is a separate skill driving a browser; it reads its own
    `publish.json` and would otherwise have no way to tell an approved cut from
    a re-render that happened afterwards. Writing the digests down is what lets
    it check, and what makes the approval mean something outside this process.

    A production has many units, so this is a **registry keyed by the video**
    rather than a single record: approving episode 2 must not silently revoke
    episode 1, and a batch of Shorts needs one entry each. The uploader looks
    itself up by the video its own `publish.json` names, which is what binds an
    approval to one specific cut instead of to whatever happens to be on disk.
    """
    unit = unit_by_label(st, label)
    targets = {k: rel_to_root(st, v)
               for k, v in publish_targets(st, unit).items()}
    if "video" not in targets:
        # No publish.json yet, so fall back to what this unit actually shot.
        # Without a video the uploader has no key to find this entry by, and
        # the approval would be unreachable rather than merely unused.
        for up in ("render", "shoot"):
            for a in (rec(unit, up).get("artifacts") or []):
                if a.get("path"):
                    targets["video"] = a["path"]
                    break
            if "video" in targets:
                break
    entry = {
        "production": st["id"],
        "unit": label,
        "channel": st["brief"].get("channel"),
        "privacy": st["brief"].get("privacy") or "private",
        "at": now(),
        "by": os.environ.get("USER", "?"),
        "targets": targets,
        "files": {v: k for k, v in bundle.items()},
    }
    path = os.path.join(st["root"], PUBLISH_LOCK)
    entries = []
    try:
        with open(path, encoding="utf-8") as fh:
            old = json.load(fh)
        if isinstance(old, dict) and isinstance(old.get("approvals"), list):
            entries = [e for e in old["approvals"]
                       if isinstance(e, dict)
                       and e.get("production") == st["id"]
                       and e.get("unit") != label]
    except (OSError, ValueError):
        entries = []
    entries.append(entry)
    write_atomic(path, json.dumps({
        "schema": 2,
        "production": st["id"],
        "approvals": entries,
    }, indent=2) + "\n")


def unit_by_label(st, label):
    """The reverse of the labels `unit_for` hands out."""
    for kind, i, unit in units(st):
        if (kind if kind == "production" else "%s %d" % (kind, i)) == label:
            return unit
    return None


def cmd_report(args):
    st = load(args.root)
    say(render_plan(st))
    say("")
    counts = {}
    problems, delivered = [], []
    for kind, i, unit in units(st):
        label = "production" if kind == "production" else "%s %d" % (kind, i)
        for name in ORDER:
            if not wanted(st, name):
                continue
            scope = STAGE[name]["scope"]
            if scope == "production" and kind != "production":
                continue
            if scope in ("episode", "short") and kind != scope:
                continue
            if scope == "deliverable" and kind == "production":
                continue
            s = stage_state(st, unit, name)
            counts[s] = counts.get(s, 0) + 1
            if s not in ("done", "pending"):
                problems.append("  %-12s %-9s %s  %s" % (
                    label, name, s.upper(),
                    (rec(unit, name).get("note") or "")))
        for name in ("render", "shoot"):
            for a in ((unit.get("stages") or {}).get(name) or {}).get("artifacts") or []:
                # The *effective* state, not the recorded one. A publish record
                # keeps saying "done" after a re-render, and a wrap report that
                # calls the new file published is worse than no report.
                ps = stage_state(st, unit, "publish")
                delivered.append("  %-10s %-40s %s" % (
                    label, a["path"],
                    {"done": "published",
                     "stale": "published, then re-cut — the file on disk is "
                              "NOT what went out",
                     "changed": "published, then changed — the file on disk is "
                                "NOT what went out"}.get(ps, "not published")))

    say("WRAP  " + "  ".join("%d %s" % (n, k) for k, n in sorted(counts.items())))
    if st.get("unverified"):
        say("  UNVERIFIED — research was not run; nothing here is fact-checked")
    if st["brief"].get("publish_authorised_at"):
        say("  release was authorised at the command line on %s, not in the "
            "plan" % st["brief"]["publish_authorised_at"])
    if problems:
        say("\nNEEDS ATTENTION")
        say("\n".join(problems))
    if delivered:
        say("\nDELIVERABLES")
        say("\n".join(delivered))
    if st.get("unverified"):
        say("\nNOTE  research was skipped — this production is not fact-checked, "
            "and nothing about it should be described as sourced.")
    return 0 if not problems else 1


def cmd_styles(args):
    if registry is None:
        die("style registry not importable from %s" % REGISTRY)
    return registry.main(["list"] + (["--json"] if args.json else []))


def cmd_doctor(args):
    if registry is None:
        die("style registry not importable from %s" % REGISTRY)
    ok = True
    say("toolchain")
    for k, v in toolchain().items():
        say("    %-10s %s" % (k, v if v else "NOT FOUND"))
        ok = ok and bool(v)
    say("\ncrew")
    for crew in sorted({s["crew"] for s in STAGE.values()}):
        present = os.path.isdir(os.path.join(SKILLS, crew))
        say("    %-26s %s" % (crew, "ok" if present else "MISSING from " + SKILLS))
        ok = ok and present
    say("\nstyles")
    rc = registry.main(["doctor"] + (["--json"] if args.json else []))
    return 0 if ok and rc == 0 else 1


# --------------------------------------------------------------------- cli --

EPILOG = """\
examples
  director.py --paper --topic "the 1984 Bhopal gas disaster" --parts 2 --shorts 3
      Two paper-style episodes on that topic, plus three vertical Shorts cut
      from the hookiest moments. Nothing is published.

  director.py --topic "how sourdough works" --runtime 8m
      One 8-minute episode. No --style, so the style is ranked from the topic
      and the command stops if the choice is a close call.

  director.py --paper --topic "..." --publish my-handle
      Same, but package and upload. `publish` still stops for an approval bound
      to the exact file.

  director.py status .            what is done, stale or failed
  director.py next .              the exact handoff for the next stage
  director.py advance render . --episode 1 --artifact out/ep1.mp4
  director.py approve publish . --episode 1 --artifact out/ep1.mp4
  director.py styles              every installed style
  director.py doctor              are the tools and styles usable?

stages
""" + "\n".join(
    "  %-9s %-26s %s" % (n, STAGE[n]["crew"], BRIEFING[n].split(".")[0])
    for n in ORDER) + """

Stages run in that order. A stage is only `done` when its artifacts exist and
still hash to what was recorded; change a script and everything downstream of it
goes stale rather than silently shipping.
"""


def parser():
    p = argparse.ArgumentParser(
        prog="director.py",
        description="Plan and track a film-crew production.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter)

    b = p.add_argument_group("the brief")
    b.add_argument("--topic", help="what the video is about")
    b.add_argument("--source", help="existing material to adapt: article, transcript, URL")
    b.add_argument("--style", metavar="ID",
                   help="which look to shoot in; omit to rank it from the topic")
    # One shorthand per installed style, generated from the registry. Adding a
    # style folder adds its flag; deleting the folder removes it. Nothing here
    # names a particular look.
    for sid, blurb in installed_styles():
        b.add_argument("--%s" % sid, dest="style", action="store_const",
                       const=sid, help="shorthand for --style %s — %s"
                       % (sid, blurb))

    s = p.add_argument_group("shape")
    s.add_argument("--parts", "--long", type=int, default=1, metavar="N",
                   help="split ONE narrative into N ordered episodes (a count, "
                        "not minutes). --long is an alias.")
    s.add_argument("--runtime", "--time", type=parse_runtime, metavar="T",
                   help="runtime per episode: 13m, 8:30, 480s (default 13m)")
    s.add_argument("--shorts", type=int, default=0, metavar="N",
                   help="cut N vertical Shorts from the hookiest moments")
    s.add_argument("--short-seconds", type=int, default=DEFAULT_SHORT_SEC,
                   metavar="S", help="target length of each Short (default 40)")
    s.add_argument("--aspect", choices=["16:9", "9:16", "1:1"],
                   help="override the style's native aspect")
    s.add_argument("--language", default="en")
    s.add_argument("--voice", help="TTS voice for the voice booth")
    s.add_argument("--seed", type=int, default=19,
                   help="determinism: same seed, same render")

    d = p.add_argument_group("distribution")
    d.add_argument("--channel", metavar="PROFILE",
                   help="the publish.json channel profile to package for")
    d.add_argument("--publish", nargs="?", const=True, default=False,
                   metavar="CHANNEL",
                   help="carry on through upload (still needs a scoped "
                        "approval). Takes an optional channel name, so "
                        "--publish my-handle is the same as "
                        "--channel my-handle --publish")
    d.add_argument("--privacy", choices=["private", "unlisted", "public"],
                   default="private")

    c = p.add_argument_group("control")
    c.add_argument("--only", nargs="+", metavar="STAGE",
                   help="run only these stages; leaving out research marks "
                        "the whole production unverified")
    c.add_argument("--skip", nargs="+", metavar="STAGE",
                   help="skip these stages; skipping research marks the whole "
                        "production unverified")
    c.add_argument("--out", metavar="DIR", help="production directory")
    c.add_argument("--dry-run", action="store_true", help="print the plan, write nothing")
    c.add_argument("--force", action="store_true", help="overwrite an existing production")

    sub = p.add_subparsers(dest="cmd")

    def with_root(sp):
        sp.add_argument("root", nargs="?", default=".", help="production directory")
        return sp

    st = with_root(sub.add_parser("status", help="what is done, stale or failed"))
    st.add_argument("--json", action="store_true")

    nx = with_root(sub.add_parser("next", help="the handoff for the next stage"))
    nx.add_argument("--all", action="store_true", help="show blocked stages too")

    ad = sub.add_parser("advance", help="record a stage as done (or failed)")
    ad.add_argument("stage", choices=ORDER)
    ad.add_argument("root", nargs="?", default=".", help="production directory")
    ad.add_argument("--episode", type=int)
    ad.add_argument("--short", type=int)
    ad.add_argument("--from-episode", type=int, metavar="N",
                    help="for a Short: which episode it is cut from")
    ad.add_argument("--from-hook", metavar="ID",
                    help="for a Short: which hook in that episode's beat plan")
    ad.add_argument("--artifact", nargs="*", help="what it produced")
    ad.add_argument("--note")
    ad.add_argument("--fail", metavar="WHY", help="record a failure instead")
    ad.add_argument("--allow-publish", action="store_true",
                    help="authorise release for a production planned without "
                         "--publish; approvals are still required")
    ad.add_argument("--force", action="store_true")

    ap = sub.add_parser("approve", help="approve an irreversible stage")
    ap.add_argument("stage", choices=sorted(IRREVERSIBLE))
    ap.add_argument("--episode", type=int)
    ap.add_argument("--short", type=int)
    ap.add_argument("root", nargs="?", default=".",
                    help="production directory")
    ap.add_argument("--artifact", nargs="+")

    with_root(sub.add_parser("report", help="the wrap report"))

    sy = sub.add_parser("styles", help="every installed style")
    sy.add_argument("--json", action="store_true")

    dc = sub.add_parser("doctor", help="check tools, crew and styles")
    dc.add_argument("--json", action="store_true")

    return p


def main(argv=None):
    p = parser()
    a = p.parse_args(argv)
    if a.cmd == "status":
        return cmd_status(a)
    if a.cmd == "next":
        return cmd_next(a)
    if a.cmd == "advance":
        return cmd_advance(a)
    if a.cmd == "approve":
        return cmd_approve(a)
    if a.cmd == "report":
        return cmd_report(a)
    if a.cmd == "styles":
        return cmd_styles(a)
    if a.cmd == "doctor":
        return cmd_doctor(a)
    if a.cmd:
        p.error("unknown command %r" % a.cmd)
    for name in (a.only or []) + (a.skip or []):
        if name not in STAGE:
            p.error("unknown stage %r in --only/--skip; one of: %s"
                    % (name, ", ".join(ORDER)))
    # `--publish my-handle` is the obvious thing to type, so accept it and
    # treat the value as the channel rather than making it a parse error.
    if isinstance(a.publish, str):
        if a.channel and a.channel != a.publish:
            p.error("--publish %s conflicts with --channel %s; name the "
                    "channel once" % (a.publish, a.channel))
        a.channel, a.publish = a.publish, True
    if a.publish and not a.channel:
        p.error("--publish needs a channel: a video has to go somewhere.\n"
                "  Either --publish my-handle, or --channel my-handle --publish")
    try:
        return build(a)
    except (registry.StyleError if registry else LookupError) as e:
        die(str(e))


if __name__ == "__main__":
    raise SystemExit(main())
