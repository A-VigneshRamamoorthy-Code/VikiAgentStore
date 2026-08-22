"""The style registry.

A *style* is a skill of its own that knows how to turn a style-neutral beat
plan into a finished video. It declares itself with ``provides_style`` in its
``crew.json`` and carries a ``style.json`` beside it. The registry is the only
thing that knows which styles exist: it discovers them from the installed
skills, so adding a look is installing a skill — there is no list to update,
and therefore no list to forget.

    python3 registry.py list                 # one line per style
    python3 registry.py list --json
    python3 registry.py show paper           # the full manifest, resolved
    python3 registry.py rank "the 1984 Bhopal gas disaster"
    python3 registry.py doctor paper         # are its dependencies present?

Every style ships a ``style.json`` declaring the contract in
``reference/style-contract.md``. A manifest that does not satisfy that contract
is reported as invalid and excluded rather than half-loaded, because a style
that loads but cannot render fails much later and much more confusingly.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILLS = os.path.normpath(os.path.join(HERE, "..", ".."))

STYLE_API = 1

#: Fields every manifest must carry, and the type each must have.
REQUIRED = {
    "style_api": int,
    "id": str,
    "name": str,
    "version": str,
    "aliases": list,
    "tagline": str,
    "strengths": list,
    "avoid": list,
    "aspects": list,
    "deliverables": list,
    "entrypoints": dict,
}

#: Entrypoints a style must define. ``compile`` turns a beat plan into whatever
#: private storyboard the style renders; ``render`` produces the video. The
#: others are optional but strongly encouraged.
REQUIRED_ENTRYPOINTS = ("compile", "render")


class StyleError(LookupError):
    """A style was requested that does not exist, or cannot be used."""


# --------------------------------------------------------------- discovery --


def _manifest_path(d):
    return os.path.join(d, "style.json")


def style_skills():
    """Every installed skill that declares it provides a look.

    A style used to be a folder inside this skill. It is now a skill of its
    own, so that adding one is the same act as adding any other crew member:
    drop the folder in, declare it, and the director sees it. The declaration
    is `provides_style` in the skill's own `crew.json` -- a style is not
    inferred from a stray `style.json`, because a half-finished folder would
    then silently become a shootable look.

    Returns absolute style directories, sorted, and never raises: an
    unreadable manifest here must not stop the other looks from loading.
    """
    out = []
    root = os.environ.get("FILM_CREW_SKILLS") or SKILLS
    if not os.path.isdir(root):
        return out
    for name in sorted(os.listdir(root)):
        if name.startswith((".", "_")):
            continue
        crew = os.path.join(root, name, "crew.json")
        if not os.path.isfile(crew):
            continue
        try:
            with open(crew, encoding="utf-8") as fh:
                m = json.load(fh)
            spec = (m or {}).get("provides_style")
        except (OSError, ValueError, AttributeError):
            continue
        if not isinstance(spec, dict):
            continue
        out.append(os.path.join(root, name))
    return out


def _validate(m, path):
    """Return a list of human-readable problems with a manifest."""
    problems = []
    for field, kind in REQUIRED.items():
        if field not in m:
            problems.append("missing required field %r" % field)
        elif not isinstance(m[field], kind):
            problems.append("%r must be %s, got %s"
                            % (field, kind.__name__, type(m[field]).__name__))
    if isinstance(m.get("style_api"), int) and m["style_api"] != STYLE_API:
        problems.append("style_api %s — this registry speaks %s"
                        % (m["style_api"], STYLE_API))
    ep = m.get("entrypoints")
    if isinstance(ep, dict):
        for name in REQUIRED_ENTRYPOINTS:
            if name not in ep:
                problems.append("entrypoints.%s is required" % name)
        for name, argv in ep.items():
            # argv arrays, never shell strings: a style folder is user content
            # and a string would be one quoting bug away from arbitrary
            # execution.
            if not isinstance(argv, list) or not all(isinstance(a, str) for a in argv):
                problems.append(
                    "entrypoints.%s must be a list of strings (argv), "
                    "not a shell string" % name)
                continue
            # A style folder is user content, so its scripts have to stay
            # inside it. Without this an entrypoint can name an absolute path
            # or climb out with `..`, and installing a style becomes a way of
            # running anything on the machine.
            problems.extend(_check_argv(name, argv, path))
    folder = os.path.basename(os.path.dirname(path))
    if m.get("id") and folder not in (m["id"], "style-%s" % m["id"]):
        problems.append("id %r does not match its folder %r; a style skill is "
                        "named after the id users type, optionally prefixed "
                        "'style-' (so %r or %r)"
                        % (m["id"], folder, m["id"], "style-%s" % m["id"]))
    return problems


def discover(include_invalid=False):
    """Every style on disk, sorted by id.

    Each entry gains three resolved keys the manifest does not carry: ``dir``
    (absolute path), ``problems`` (validation failures) and ``valid``.
    """
    found = []
    for d in style_skills():
        name = os.path.basename(d)
        mf = _manifest_path(d)
        if not os.path.isfile(mf):
            found.append({"id": name, "name": name, "dir": d, "valid": False,
                          "problems": ["declares provides_style in crew.json "
                                       "but has no style.json beside it"]})
            continue
        try:
            with open(mf, encoding="utf-8") as fh:
                m = json.load(fh)
        except (OSError, ValueError) as e:
            m, problems = {"id": name, "name": name}, ["unreadable style.json: %s" % e]
        else:
            # Shape first. `_validate` reads keys off the manifest, so handing
            # it a JSON array or string throws AttributeError and one malformed
            # folder takes down discovery for every other style.
            if isinstance(m, dict):
                problems = _validate(m, mf)
            else:
                m, problems = ({"id": name, "name": name},
                               ["style.json should hold an object, found %s"
                                % type(m).__name__])
        m = dict(m)
        m["dir"] = d
        m["problems"] = problems
        m["valid"] = not problems
        found.append(m)
    found.sort(key=lambda m: m.get("id") or "")
    return [m for m in found if m.get("valid") or include_invalid]


#: Which interpreters a style may launch, as a pattern so point releases
#: (`python3.12`) are accepted without listing every one. A shell, `env`, or a
#: downloaded binary is not here: the argument after the interpreter has to be
#: a script inside the style folder, and only these treat it that way.
INTERPRETER_RE = re.compile(r"^(?:python3(?:\.\d+)?|python|node|ffmpeg)$")

#: The extension each interpreter is expected to run, so a Node style cannot
#: quietly point at a shell script.
SCRIPT_SUFFIX = {"python": (".py",), "python3": (".py",),
                 "node": (".js", ".mjs", ".cjs")}

PLACEHOLDER = "{style}/"


def _interp_family(prog):
    if prog.startswith("python"):
        return "python3"
    return prog


def _contained(arg):
    """A `{style}/...` reference that cannot climb out of the style folder."""
    if not arg.startswith(PLACEHOLDER):
        return False
    rest = arg[len(PLACEHOLDER):]
    return rest and os.pardir not in rest.split("/")


#: Interpreter options that cannot introduce code from outside the style
#: folder. Everything else before the script is refused, because that is where
#: `-c`, `-m` and `--eval` live.
SAFE_INTERP_FLAGS = {
    "python3": ("-u", "-E", "-I", "-s", "-S", "-B"),
    "node": ("--max-old-space-size=", "--stack-size="),
}

#: `file:`, `concat:`, `http:` ... ffmpeg and friends happily read a path that
#: is wearing a scheme, and such a token starts with a letter rather than "/".
SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")


def _escapes(tok):
    """Does this token name something outside the style folder?"""
    if not tok:
        return False
    if PLACEHOLDER in tok:
        return not _contained(tok)
    if tok.startswith(("/", "~")):
        return True
    if tok == os.pardir or tok.startswith(os.pardir + "/"):
        return True
    # A scheme is only a way of spelling a path that does not start with "/".
    return bool(SCHEME_RE.match(tok)) and not tok.startswith("{style")


def _check_argv(name, argv, manifest_path):
    """Validate one entrypoint as ``[interpreter, script, ...arguments]``.

    Insisting on that shape is what makes the rest checkable. Scanning a flat
    list for suspicious-looking flags cannot work: `--eval=code` is one token,
    `-m pip` names no path at all, and a style's own script legitimately takes a
    `-c` of its own. Once the script is pinned to argv[1], anything before it is
    an interpreter option and is simply refused, and everything after it is the
    style's business except that paths must stay inside the folder.
    """
    out = []
    if not argv:
        return ["entrypoints.%s is empty" % name]
    prog = os.path.basename(argv[0])
    if argv[0] != prog or not INTERPRETER_RE.match(prog):
        return ["entrypoints.%s runs %r; a style may only launch python3, "
                "python, node or ffmpeg, named plainly" % (name, argv[0])]

    if prog == "ffmpeg":                       # no script; args only
        rest = argv[1:]
    else:
        if len(argv) < 2:
            return ["entrypoints.%s names %s with nothing to run"
                    % (name, prog)]
        # Skip harmless interpreter options, so a style may ask for unbuffered
        # output without having to smuggle it past this check.
        i = 1
        safe = SAFE_INTERP_FLAGS.get(_interp_family(prog), ())
        while i < len(argv) and argv[i].startswith("-") and any(
                argv[i] == f or (f.endswith("=") and argv[i].startswith(f))
                for f in safe):
            i += 1
        argv = argv[:1] + argv[i:]
        if len(argv) < 2:
            return ["entrypoints.%s names %s with nothing to run"
                    % (name, prog)]
        script = argv[1]
        if script.startswith("-"):
            return ["entrypoints.%s passes %r to %s before naming a script; "
                    "interpreter options can run code that is not in the "
                    "style folder" % (name, script, prog)]
        if not _contained(script):
            return ["entrypoints.%s runs %r, which is not a script under "
                    "{style}" % (name, script)]
        want = SCRIPT_SUFFIX.get(_interp_family(prog), ())
        if want and not script.endswith(want):
            out.append("entrypoints.%s runs %r with %s; expected one of %s"
                       % (name, script, prog, ", ".join(want)))
        # Follow the link. A `{style}/scripts/run.py` symlinked out of the
        # folder passes every string check while executing someone else's code.
        real = os.path.join(os.path.dirname(manifest_path),
                            script[len(PLACEHOLDER):])
        if os.path.exists(real):
            root = os.path.realpath(os.path.dirname(manifest_path))
            if os.path.commonpath([os.path.realpath(real), root]) != root:
                out.append("entrypoints.%s runs %r, which resolves outside the "
                           "style folder" % (name, script))
        rest = argv[2:]

    for a in rest:
        # Check the whole token and, for `--flag=value`, the value on its own:
        # `-i=file:/etc/passwd` is one argv entry and hides its path after the
        # `=` where a naive prefix check will not look.
        parts = [a] + ([a.split("=", 1)[1]] if "=" in a else [])
        for tok in parts:
            if _escapes(tok):
                out.append("entrypoints.%s refers to %r; a style may only name "
                           "paths under {style}" % (name, a))
                break
    return out


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "", str(s or "").lower())


def resolve(ref):
    """Find a style by id or alias. Case- and punctuation-insensitive."""
    want = _slug(ref)
    if not want:
        raise StyleError("no style given")
    styles = discover(include_invalid=True)

    def _take(s):
        if not s["valid"]:
            raise StyleError(
                "style %r has an invalid style.json:\n  - %s"
                % (s.get("id", ref), "\n  - ".join(s["problems"])))
        return s

    def _one(matches, how):
        """Refuse an ambiguous match rather than silently taking the first.

        Two skills can legitimately declare the same style id -- the folder
        may be either `<id>` or `style-<id>`, so `paper/` and `style-paper/`
        both validate. Whichever sorts first would otherwise win silently and
        the other style would simply never render.
        """
        if len(matches) > 1:
            raise StyleError(
                "%r %s more than one installed style (%s) — two skills "
                "declare the same style id; remove or rename one"
                % (ref, how, ", ".join(sorted(m["dir"] for m in matches))))
        return _take(matches[0]) if matches else None

    # Literal id first. `_slug` strips punctuation, so `foobar` and `foo-bar`
    # normalise to the same thing; a style asked for by its exact name must
    # never be answered with a different one.
    hit = _one([s for s in styles
                if str(s.get("id", "")).casefold() == str(ref).casefold()],
               "names")
    if hit:
        return hit

    # An id always beats an alias. Without this a folder that merely sorts
    # first can claim another style's name by listing it as an alias, and the
    # wrong style renders with no indication anything was substituted.
    hit = _one([s for s in styles if _slug(s.get("id", "")) == want], "matches")
    if hit:
        return hit
    by_alias = [s for s in styles
                if any(_slug(n) == want for n in s.get("aliases") or [])]
    if len(by_alias) > 1:
        raise StyleError(
            "%r is claimed as an alias by more than one style (%s) — "
            "ask for one by its id" % (ref, ", ".join(
                s.get("id", "?") for s in by_alias)))
    if by_alias:
        return _take(by_alias[0])
    known = ", ".join(s.get("id", "?") for s in styles) or "(none installed)"
    raise StyleError("unknown style %r — available: %s" % (ref, known))


# ----------------------------------------------------------------- ranking --

#: Topic shapes worth recognising, and the regex that betrays each one. These
#: map onto the vocabulary styles declare in ``strengths``/``avoid``, so a new
#: style becomes rankable by using words that already appear here. Anything a
#: style declares outside this vocabulary is inert rather than an error — it
#: simply never scores, which is why `list` prints the vocabulary.
NEEDS = [
    ("history",        r"\b(histor|ancient|century|centuries|war|empire|dynast|archiv)|\b1[0-9]{3}\b|\b20[0-2][0-9]\b"),
    ("investigation",  r"\b(investigat|scandal|fraud|cover.?up|leak|inquiry|corrupt|conspirac)"),
    ("journalism",     r"\b(report|news|court|trial|verdict|testimon|whistle)"),
    ("disaster",       r"\b(disaster|crash|collapse|explosion|earthquake|flood|famine|outbreak|pandemic)"),
    ("science",        r"\b(scien|physic|chemis|biolog|research|study|experiment|theor|quantum|climate)"),
    ("explainer",      r"\b(how|why|what is|explain|guide|understand|works|basics|introduction)"),
    ("business",       r"\b(compan|business|startup|market|econom|profit|revenue|industr|brand)"),
    ("essay",          r"\b(essay|reflect|personal|memoir|meaning|philosoph)"),
    ("product-demo",   r"\b(demo|tutorial|walkthrough|app|software|dashboard|feature|release|saas)"),
    ("screen-recording", r"\b(screen ?record|screencast|my app|the app|ui|interface)"),
    ("live-action",    r"\b(interview|footage|camera|on.?camera|presenter|vlog)"),
    ("comedy",         r"\b(funny|comedy|joke|meme|satir|prank)"),
    ("gaming",         r"\b(game|gaming|gameplay|speedrun|console|esports)"),
    ("text-heavy",     r"\b(quote|document|report|statist|figure|data|number|percent)"),
]

#: The closed vocabulary a style may use in ``strengths``/``avoid`` and have it
#: count. Exposed so `list` can print it and a style author can see it.
VOCABULARY = [need for need, _ in NEEDS]


def style_dir(ref):
    """The absolute folder of a style, by id or alias.

    These four helpers used to live in a `_resolve.py` that assumed every look
    sat under one `styles/` directory. Now that a look is a skill, only the
    registry knows where one lives, so asking it is the only way that stays
    true when a style is installed or removed.
    """
    return resolve(ref)["dir"]


def style_scripts(ref):
    """Where a style keeps the programs that compile and render it."""
    return os.path.join(style_dir(ref), "scripts")


def style_fonts(ref):
    """A style's bundled fonts. Raises if it ships none."""
    path = os.path.join(style_dir(ref), "fonts")
    if not os.path.isdir(path):
        raise StyleError("style %r has no fonts directory at %s" % (ref, path))
    return path


def list_styles():
    """Every usable style id, sorted."""
    return sorted(m["id"] for m in discover())


def infer_needs(text):
    """The topic shapes a piece of free text exhibits, in declaration order."""
    t = (text or "").lower()
    return [need for need, pattern in NEEDS if re.search(pattern, t)]


def rank(text, styles=None):
    """Score every style against a topic. Returns ``[(score, matched, style)]``.

    A style scores +3 for each need it lists as a strength and −4 for each need
    it lists under ``avoid``. The penalty is heavier than the reward on purpose:
    a style that is merely acceptable costs a viewer, and one that is actively
    wrong costs the video.

    This is a tie-breaker, not a decision. It reads topic *words*, which say
    little about how a subject should look; when the top two scores are close
    the caller should ask rather than guess.
    """
    needs = infer_needs(text)
    out = []
    for s in (discover() if styles is None else styles):
        strengths = {str(x).lower() for x in s.get("strengths") or []}
        avoid = {str(x).lower() for x in s.get("avoid") or []}
        hit = [n for n in needs if n in strengths]
        clash = [n for n in needs if n in avoid]
        out.append((3 * len(hit) - 4 * len(clash), hit, s))
    out.sort(key=lambda r: (-r[0], r[2].get("id", "")))
    return out


# ------------------------------------------------------------------ doctor --


def doctor(style):
    """Check a style's declared dependencies. Never raises; reports."""
    req = style.get("requires") or {}
    report = {"style": style.get("id"), "ok": True, "bin": {}, "python": {},
              "missing": []}

    for b in req.get("bin") or []:
        found = shutil.which(b)
        report["bin"][b] = found or False
        if not found:
            report["ok"] = False

    mods = req.get("python") or []
    if mods:
        probe = ("import importlib.util,json,sys;"
                 "print(json.dumps({m: importlib.util.find_spec(m) is not None "
                 "for m in sys.argv[1:]}))")
        try:
            out = subprocess.run([sys.executable, "-c", probe] + list(mods),
                                 capture_output=True, text=True, timeout=60)
            got = json.loads(out.stdout or "{}")
        except (OSError, ValueError, subprocess.SubprocessError):
            got = {m: False for m in mods}
        report["python"] = got
        if not all(got.values()):
            report["ok"] = False

    # Every entrypoint, not only the required two, and every `{style}` path in
    # it — not only the ones ending in `.py`. A Node style whose `.mjs` is
    # missing used to report `ok: true` and fail at render time instead.
    for name, argv in sorted((style.get("entrypoints") or {}).items()):
        for a in argv if isinstance(argv, list) else []:
            if not isinstance(a, str) or not a.startswith(PLACEHOLDER):
                continue
            path = a.replace("{style}", style.get("dir", ""))
            if not os.path.exists(path):
                report["missing"].append("%s (entrypoints.%s)" % (path, name))
                report["ok"] = False
    return report


def entrypoint(style, name, **subs):
    """Resolve an entrypoint to a concrete argv list.

    ``{style}`` always expands to the style directory; the caller supplies the
    rest. An unsubstituted placeholder is an error rather than a literal brace
    reaching the process.
    """
    argv = (style.get("entrypoints") or {}).get(name)
    if not argv:
        raise StyleError("style %r defines no %r entrypoint"
                         % (style.get("id"), name))
    subs = dict(subs, style=style.get("dir", ""))
    out = []
    for a in argv:
        for k, v in subs.items():
            a = a.replace("{" + k + "}", str(v))
        if re.search(r"\{[a-z_]+\}", a):
            raise StyleError(
                "%r entrypoint of %r has an unfilled placeholder in %r; "
                "supply it via entrypoint(..., name=value)"
                % (name, style.get("id"), a))
        out.append(a)
    return out


# -------------------------------------------------------------------- cli ---


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="registry.py", description="Discover and inspect video styles.")
    sub = p.add_subparsers(dest="cmd")

    ls = sub.add_parser("list", help="every installed style")
    ls.add_argument("--json", action="store_true")
    ls.add_argument("--all", action="store_true", help="include invalid manifests")

    sh = sub.add_parser("show", help="one style's resolved manifest")
    sh.add_argument("style")

    rk = sub.add_parser("rank", help="score styles against a topic")
    rk.add_argument("topic")
    rk.add_argument("--json", action="store_true")

    dr = sub.add_parser("doctor", help="check a style's dependencies")
    dr.add_argument("style", nargs="?", help="omit to check every style")
    dr.add_argument("--json", action="store_true")

    a = p.parse_args(argv)
    if not a.cmd:
        p.print_help()
        return 2

    if a.cmd == "list":
        styles = discover(include_invalid=a.all)
        if a.json:
            print(json.dumps(styles, indent=2))
            return 0
        if not styles:
            print("no skill declares `provides_style` under %s" % SKILLS)
            return 1
        width = max(len(s.get("id", "?")) for s in styles)
        for s in styles:
            flag = "" if s["valid"] else "  [INVALID]"
            print("  %-*s  %s%s" % (width, s.get("id", "?"), s.get("tagline", ""), flag))
            for prob in s["problems"]:
                print("  %-*s  ! %s" % (width, "", prob))
        print("\nranking vocabulary: %s" % ", ".join(VOCABULARY))
        return 0

    if a.cmd == "show":
        try:
            print(json.dumps(resolve(a.style), indent=2))
        except StyleError as e:
            print("error: %s" % e, file=sys.stderr)
            return 1
        return 0

    if a.cmd == "rank":
        scored = rank(a.topic)
        if a.json:
            print(json.dumps([{"id": s.get("id"), "score": sc, "matched": hit}
                              for sc, hit, s in scored], indent=2))
            return 0
        print("needs inferred: %s\n" % (", ".join(infer_needs(a.topic)) or "(none)"))
        for sc, hit, s in scored:
            print("  %+3d  %-12s %s" % (sc, s.get("id"), ", ".join(hit) or "—"))
        return 0

    if a.cmd == "doctor":
        try:
            styles = [resolve(a.style)] if a.style else discover()
        except StyleError as e:
            print("error: %s" % e, file=sys.stderr)
            return 1
        reports = [doctor(s) for s in styles]
        if a.json:
            print(json.dumps(reports, indent=2))
        else:
            for r in reports:
                print("%s: %s" % (r["style"], "ok" if r["ok"] else "PROBLEMS"))
                for b, found in r["bin"].items():
                    print("    bin %-10s %s" % (b, found or "NOT FOUND — install it"))
                for m, found in r["python"].items():
                    print("    py  %-10s %s"
                          % (m, "ok" if found else "NOT IMPORTABLE — pip install it"))
                for miss in r["missing"]:
                    print("    missing script %s" % miss)
        return 0 if all(r["ok"] for r in reports) else 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
