#!/usr/bin/env python3
"""The crew registry: who is on this production, and what each of them does.

The pipeline used to be a table inside `director.py`. That made every change a
code change — adding a skill meant editing the director, and removing one meant
finding every place its stage name was mentioned. This module replaces the
table with **discovery**: each crew skill ships a `crew.json` declaring the
stages it provides, and the director asks this registry what to run rather than
knowing in advance.

The practical consequence is that a crew skill is installed by existing and
uninstalled by being deleted. Nothing else has to be told.

    from crew import load_crew
    reg = load_crew()
    reg.order                  # stage ids, dependency-sorted
    reg.stage["render"]        # {'id', 'crew', 'scope', 'emits', 'needs', ...}
    reg.wanted(brief, "publish")

Run it directly to inspect what is installed::

    python3 crew.py list
    python3 crew.py doctor
    python3 crew.py graph
"""

import json
import os
import sys

CREW_API = 1
MANIFEST = "crew.json"

#: Where a unit's work is recorded. `deliverable` means "an episode or a
#: Short", which is how packaging and publishing see the world.
SCOPES = ("production", "episode", "short", "deliverable")

#: A stage declaration's shape. Anything else in the file is ignored, so a
#: newer skill can carry fields this director does not understand yet.
REQUIRED = {"stage": str, "scope": str, "order": int, "emits": list,
            "briefing": str}


class CrewError(Exception):
    """A manifest is malformed. Always names the file."""


def skills_dir():
    """The `skills/` folder this script lives under.

    This file is `skills/director/scripts/crew.py`, so the folder holding
    every crew skill is three levels up. `FILM_CREW_SKILLS` overrides it, which
    is what the tests use to build a registry out of a scratch directory.
    """
    env = os.environ.get("FILM_CREW_SKILLS")
    if env:
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(here))


def discover(root=None):
    """Every `crew.json` under `skills/`, in a stable order."""
    root = root or skills_dir()
    out = []
    try:
        names = sorted(os.listdir(root))
    except OSError as e:
        raise CrewError("cannot read %s: %s" % (root, e))
    for name in names:
        p = os.path.join(root, name, MANIFEST)
        if os.path.isfile(p):
            out.append(p)
    return out


def _read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            m = json.load(fh)
    except (OSError, ValueError) as e:
        raise CrewError("%s: %s" % (path, e))
    if not isinstance(m, dict):
        raise CrewError("%s: not an object" % path)
    if m.get("crew_api") != CREW_API:
        raise CrewError("%s: crew_api %r, expected %d — this director cannot "
                        "read it" % (path, m.get("crew_api"), CREW_API))
    sid = m.get("id")
    if not isinstance(sid, str) or not sid:
        raise CrewError("%s: no id" % path)
    want = os.path.basename(os.path.dirname(path))
    if sid != want:
        raise CrewError("%s: declares id %r but lives in %r. The id is how the "
                        "director names the skill in a handoff, so it has to "
                        "be the folder." % (path, sid, want))
    if not isinstance(m.get("provides"), list):
        raise CrewError("%s: 'provides' must be a list of stages" % path)
    return m


def _check_stage(path, sid, s, seen):
    if not isinstance(s, dict):
        raise CrewError("%s: a stage must be an object" % path)
    for k, t in REQUIRED.items():
        if k not in s:
            raise CrewError("%s: stage %r has no %r" % (path, s.get("stage"), k))
        if not isinstance(s[k], t) or isinstance(s[k], bool):
            raise CrewError("%s: stage %r: %s must be %s"
                            % (path, s.get("stage"), k, t.__name__))
    name = s["stage"]
    if s["scope"] not in SCOPES:
        raise CrewError("%s: stage %r has scope %r; expected one of %s"
                        % (path, name, s["scope"], ", ".join(SCOPES)))
    if name in seen:
        raise CrewError("stage %r is declared by both %s and %s. A stage has "
                        "exactly one owner, or `next` cannot say who to hand "
                        "it to." % (name, seen[name], sid))
    needs = s.get("needs", [])
    if isinstance(needs, dict):
        for k, v in needs.items():
            if k not in ("episode", "short"):
                raise CrewError("%s: stage %r keys its needs on %r; a "
                                "per-deliverable stage may only distinguish "
                                "'episode' and 'short'" % (path, name, k))
            if not isinstance(v, list):
                raise CrewError("%s: stage %r: needs.%s must be a list"
                                % (path, name, k))
    elif not isinstance(needs, list):
        raise CrewError("%s: stage %r: needs must be a list or an object "
                        "keyed by deliverable kind" % (path, name))

    # `when` and `irreversible` are optional, so they were previously not
    # checked at all -- which meant a manifest with the wrong shape loaded
    # cleanly and then died later inside wanted() with a bare AttributeError
    # naming no file. Every other malformation here fails loudly; these must
    # too, or the one thing this module exists to prevent still happens.
    when = s.get("when", {})
    if not isinstance(when, dict):
        raise CrewError("%s: stage %r: `when` must be an object, not %s"
                        % (path, name, type(when).__name__))
    brief = when.get("brief", {})
    if not isinstance(brief, dict):
        raise CrewError("%s: stage %r: `when.brief` must be an object mapping "
                        "a brief field to \"truthy\", \"falsy\" or an exact "
                        "value -- got %s"
                        % (path, name, type(brief).__name__))
    for field, cond in brief.items():
        if isinstance(cond, (dict, list)):
            raise CrewError(
                "%s: stage %r: `when.brief.%s` is %s. A condition is "
                "\"truthy\", \"falsy\" or a value to match exactly; it is "
                "deliberately not an expression language."
                % (path, name, field, type(cond).__name__))
    irrev = s.get("irreversible")
    if irrev is not None:
        if not isinstance(irrev, dict):
            raise CrewError(
                "%s: stage %r: `irreversible` must be an object such as "
                "{\"covers\": [\"render\"]}, not %s"
                % (path, name, type(irrev).__name__))
        covers = irrev.get("covers")
        if not isinstance(covers, list) or not covers:
            raise CrewError(
                "%s: stage %r: `irreversible.covers` must be a non-empty list "
                "of stage names. An irreversible stage that covers nothing "
                "has nothing to approve, so its gate would never fire."
                % (path, name))
        for c in covers:
            if not isinstance(c, str):
                raise CrewError("%s: stage %r: `irreversible.covers` must "
                                "contain stage names, got %s"
                                % (path, name, type(c).__name__))
    return name


def _upstream_names(needs):
    if isinstance(needs, dict):
        out = []
        for v in needs.values():
            out.extend(v)
        return out
    return list(needs or [])


class Crew(object):
    """The assembled pipeline."""

    def __init__(self, stages, skills):
        self.stage = {s["id"]: s for s in stages}
        self.order = [s["id"] for s in stages]
        self.skills = skills

    # -- the tables director.py used to hold ------------------------------
    @property
    def briefing(self):
        return {k: v["briefing"] for k, v in self.stage.items()}

    @property
    def irreversible(self):
        """Stage -> the stages whose artifacts it puts in front of an audience.

        Declared rather than walked. "Everything upstream" would drag in the
        script and the storyboard, and approving those says nothing about the
        file that actually gets uploaded.
        """
        out = {}
        for k, v in self.stage.items():
            spec = v.get("irreversible")
            if spec:
                out[k] = tuple(spec.get("covers") or [])
        return out

    def style_provider(self):
        """The skill that owns the style registry, if one is installed.

        Declared by that skill as `provides_styles`, so the director does not
        have to know which folder the looks live in. The registry then finds
        the looks themselves — each is a skill declaring `provides_style` —
        so neither the director nor this class holds a list of styles.
        Returns ``(skill_id, registry_dir)`` or ``None``.
        """
        for sid, s in sorted(self.skills.items()):
            spec = s.get("styles")
            if not spec:
                continue
            base = os.path.dirname(s["path"])
            return (sid,
                    os.path.join(base, os.path.dirname(spec.get(
                        "registry") or "scripts/registry.py")))
        return None

    def styles(self):
        """Every installed skill that is itself a look.

        The director does not need this to run — the registry resolves styles
        on its own — but `doctor` reports it, so a style skill that fails to
        load is visible rather than merely absent.
        """
        return sorted(sid for sid, s in self.skills.items() if s.get("style"))

    def scope(self, name):
        return self.stage[name]["scope"]

    def crew_for(self, name):
        return self.stage[name]["crew"]

    def needs(self, name, kind=None):
        n = self.stage[name].get("needs") or []
        if isinstance(n, dict):
            return list(n.get(kind or "episode") or [])
        return list(n)

    def wanted(self, brief, name):
        """Is this stage part of a production with *this* brief?

        Declared by the stage as `when.brief`, so packaging knowing it needs a
        channel — and publishing knowing it additionally needs consent — is a
        fact about the marketing skill, not something the director has to be
        taught. `"truthy"` is the only test on purpose: a manifest is data, and
        anything richer would be a language with an interpreter to exploit.
        """
        cond = (self.stage[name].get("when") or {}).get("brief") or {}
        for key, test in cond.items():
            got = brief.get(key)
            if test == "truthy" and not got:
                return False
            if test == "falsy" and got:
                return False
            if test not in ("truthy", "falsy") and got != test:
                return False
        return True

    def consumers(self, key):
        """Stages whose activation depends on this brief key.

        Lets the director notice that something was *asked* for which no
        installed skill can do — without knowing what `publish` means. If
        nothing consumes the key, the request cannot be honoured by anyone
        here, and silently planning a shorter pipeline would be a lie.
        """
        return [n for n in self.order
                if key in ((self.stage[n].get("when") or {}).get("brief") or {})]

    def gate_reason(self, brief, name):
        """Why `wanted` said no — for messages that help."""
        cond = (self.stage[name].get("when") or {}).get("brief") or {}
        for key, test in cond.items():
            if test == "truthy" and not brief.get(key):
                return key
        return None


def build(manifests):
    """Validate every manifest and order the stages by dependency."""
    stages, seen, skills = [], {}, {}
    for path in manifests:
        m = _read(path)
        sid = m["id"]
        skills[sid] = {"id": sid, "role": m.get("role") or sid,
                       "about": m.get("about") or "", "path": path,
                       "styles": m.get("provides_styles"),
                       "style": m.get("provides_style"),
                       "lib": m.get("provides_lib")}
        for s in m["provides"]:
            name = _check_stage(path, sid, s, seen)
            seen[name] = sid
            st = dict(s)
            st["id"] = name
            st["crew"] = sid
            stages.append(st)

    known = {s["id"] for s in stages}
    for s in stages:
        for up in _upstream_names(s.get("needs")):
            if up not in known:
                raise CrewError(
                    "stage %r (from %s) needs %r, which no installed skill "
                    "provides. Install the skill that owns it, or remove the "
                    "dependency." % (s["id"], s["crew"], up))
        for c in (s.get("irreversible") or {}).get("covers") or ():
            if c not in known:
                raise CrewError(
                    "stage %r (from %s) says it is irreversible and covers "
                    "%r, but no installed skill provides that stage. The "
                    "approval gate would then guard nothing, so this is "
                    "refused rather than silently weakened."
                    % (s["id"], s["crew"], c))
    return Crew(_toposort(stages), skills)


def _toposort(stages):
    """Dependency order, with `order` breaking ties.

    `order` alone would be enough until someone installs a skill without
    renumbering everything, so the real constraint is the dependency edge and
    `order` only decides between stages that do not constrain each other.
    """
    by_id = {s["id"]: s for s in stages}
    out, state = [], {}

    def visit(name, trail):
        mark = state.get(name)
        if mark == "done":
            return
        if mark == "open":
            cycle = " -> ".join(trail[trail.index(name):] + [name])
            raise CrewError("the stages form a cycle: %s. One of those "
                            "dependencies has to go." % cycle)
        state[name] = "open"
        for up in sorted(_upstream_names(by_id[name].get("needs")),
                         key=lambda n: (by_id[n]["order"], n)):
            visit(up, trail + [name])
        state[name] = "done"
        out.append(by_id[name])

    for s in sorted(stages, key=lambda s: (s["order"], s["id"])):
        visit(s["id"], [])
    return out


_CACHE = {}


def load_crew(root=None):
    """The registry, read once per process."""
    key = root or skills_dir()
    if key not in _CACHE:
        _CACHE[key] = build(discover(key))
    return _CACHE[key]


# ------------------------------------------------------------------- cli --


def _main(argv):
    what = argv[1] if len(argv) > 1 else "list"
    try:
        reg = load_crew()
    except CrewError as e:
        print("crew: %s" % e, file=sys.stderr)
        return 1

    if what == "list":
        for sid in sorted(reg.skills):
            s = reg.skills[sid]
            mine = [n for n in reg.order if reg.crew_for(n) == sid]
            print("  %-26s %-22s %s" % (sid, s["role"], " ".join(mine)))
        return 0

    if what == "graph":
        for n in reg.order:
            s = reg.stage[n]
            up = reg.needs(n) or ["-"]
            print("  %-10s %-26s %-11s <- %s"
                  % (n, s["crew"], s["scope"], ", ".join(up)))
        return 0

    if what == "doctor":
        bad = 0
        for sid, s in sorted(reg.skills.items()):
            if not os.path.isdir(os.path.join(skills_dir(), sid)):
                print("  MISSING  %s" % sid)
                bad += 1
        for n in reg.order:
            if not reg.stage[n].get("emits"):
                print("  note     %s emits nothing — it can only ever be "
                      "recorded as done, never verified" % n)
        print("  %d stage(s) from %d skill(s); %d problem(s)"
              % (len(reg.order), len(reg.skills), bad))
        return 1 if bad else 0

    if what == "json":
        print(json.dumps({"order": reg.order, "stages": reg.stage,
                          "skills": reg.skills}, indent=2))
        return 0

    print(__doc__.strip())
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
