"""Find the sibling skill that owns `publish.json`.

`config.py` describes the project layout and the approval protocol, and both
belong to the **publisher** — it is the skill that reads `publish.json` and
refuses to upload unapproved bytes. Marketing still needs the same view of
where things live, so rather than keeping a second copy that can drift, it
borrows the original.

The location is looked up through the crew registry, so the publisher can be
replaced or moved without editing every script here. Importing this module is
enough::

    import _shared  # noqa: F401
    from config import Publish
"""

import os
import sys

SKILLS = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def _from_registry():
    """Ask the crew registry which skill provides `config`."""
    d = os.path.join(SKILLS, "director", "scripts")
    if d not in sys.path:
        sys.path.insert(0, d)
    try:
        import crew
        reg = crew.load_crew(SKILLS)
    except Exception:
        return None
    for sid, s in sorted(reg.skills.items()):
        lib = (s.get("lib") or {})
        if "config" in lib:
            return os.path.join(os.path.dirname(s["path"]),
                                os.path.dirname(lib["config"]))
    return None


def _fallback():
    """If the registry cannot be read, the conventional location still works."""
    p = os.path.join(SKILLS, "publisher", "scripts")
    return p if os.path.isfile(os.path.join(p, "config.py")) else None


path = _from_registry() or _fallback()
if path and path not in sys.path:
    sys.path.insert(0, path)
elif not path:                                          # pragma: no cover
    raise ImportError(
        "cannot find the skill that provides config.py. The publisher skill "
        "owns it; install it, or run this from a complete film-crew plugin.")
