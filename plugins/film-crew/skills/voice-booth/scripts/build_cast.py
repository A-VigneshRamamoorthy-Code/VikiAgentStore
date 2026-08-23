#!/usr/bin/env python3
"""Build a named cast of voice characters from a JSON definition.

    python scripts/build_cast.py --characters templates/characters.json
    python scripts/build_cast.py --characters templates/characters.json --validate
    python scripts/build_cast.py --characters templates/characters.json --only karthik
    python scripts/build_cast.py --characters templates/characters.json --only imogen,divya --tries 5

Pipeline per character:
    reference (Edge voice or your own file)
      -> denoise + normalise
      -> clone with OmniVoice
      -> master to -16 LUFS
      -> measure (duration, F0, noise floor, gaps)

Writes out/cast/<key>.mp3 and out/cast/manifest.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import (  # noqa: E402
    AUDITION, CAST, F0_RANGE, MIN_F0_SEPARATION, REFS, ROOT,
    check, edge_reference, edge_speak, load_model, master, measure, median_f0,
    prepare_ref, profile_similarity, synth, voice_profile,
)
from qa import qa  # noqa: E402

REQUIRED = {"key", "name", "lang", "gender"}

# One generation is a lottery: OmniVoice samples, so the same reference and text
# can land 15% off the source pitch on one run and 1% off on the next. Measured
# across two identical builds of the same cast, F0 drift ranged 0.9-3.8% on one
# and 6.5-15.2% on the other. Generating a few candidates and keeping the closest
# is the difference between "sounds like them" and "sounds related".
#
# 3 is the default compromise; --tries 5 reliably brought stubborn voices under
# the 5% acceptance threshold, at ~45-60s per extra candidate.
DEFAULT_TRIES = 3

# Weight on each pitch spike when ranking candidates. Spikes are the defect a
# listener notices first — a single yelped syllable reads as "robotic" even when
# pitch and timbre are otherwise a good match. 0.02 per spike makes one spike
# cost about as much as 2% pitch drift, so a clean-but-slightly-off candidate
# beats an accurate one that squeaks, without letting spike count override a
# genuinely wrong voice.
SPIKE_WEIGHT = 0.02


def candidate_score(clip: Path, m: dict, ref_profile, ref_f0: float) -> float:
    """How far a candidate strays from its reference. Lower is better.

    Combines pitch drift, timbre distance and pitch-spike count. The first two
    are roughly 0-0.2 so neither dominates. Pitch alone is not enough — a
    candidate can hit the right median F0 with the wrong voice entirely, and a
    candidate can match both and still spike on one syllable.
    """
    drift = abs(m["f0"] - ref_f0) / ref_f0 if ref_f0 else 0.0
    timbre = 0.0
    if ref_profile is not None:
        try:
            timbre = 1.0 - profile_similarity(voice_profile(clip), ref_profile)
        except Exception:                              # noqa: BLE001
            timbre = 0.0
    spikes = 0
    try:
        spikes = len(qa(clip)["spikes"])
    except Exception:                                  # noqa: BLE001
        spikes = 0
    return drift + timbre + SPIKE_WEIGHT * spikes


def validate(chars: list[dict]) -> list[str]:
    """Structural validation — catches mistakes before a 10-minute build."""
    errors = []
    seen = set()

    for i, c in enumerate(chars):
        where = f"character[{i}]"
        missing = REQUIRED - c.keys()
        if missing:
            errors.append(f"{where}: missing {', '.join(sorted(missing))}")
            continue

        where = f"{where} ({c['key']})"
        if c["key"] in seen:
            errors.append(f"{where}: duplicate key")
        seen.add(c["key"])

        if c["gender"] not in F0_RANGE:
            errors.append(f"{where}: gender must be male or female")
        if c["lang"] not in AUDITION:
            errors.append(f"{where}: no audition line for lang '{c['lang']}' "
                          f"— add one to AUDITION in core.py")

        engine = c.get("engine") or "clone"
        if engine not in ("clone", "edge"):
            errors.append(f"{where}: engine must be 'clone' or 'edge'")
        if engine == "edge":
            if not c.get("source_voice"):
                errors.append(f"{where}: engine 'edge' needs source_voice "
                              f"(an Edge voice name)")
            if c.get("ref_audio"):
                errors.append(f"{where}: engine 'edge' speaks directly and "
                              f"cannot use ref_audio — drop it, or set "
                              f"engine to 'clone'")
        elif not c.get("source_voice") and not c.get("ref_audio"):
            errors.append(f"{where}: needs source_voice (an Edge voice) "
                          f"or ref_audio (your own clip)")

        if c.get("ref_audio") and not c.get("ref_text"):
            errors.append(f"{where}: ref_audio requires ref_text "
                          f"(the exact transcript)")
        trim = c.get("ref_trim")
        if trim is not None:
            if (not isinstance(trim, (list, tuple)) or len(trim) != 2
                    or not all(isinstance(v, (int, float)) for v in trim)):
                errors.append(f"{where}: ref_trim must be [start, end] in seconds")
            elif trim[1] <= trim[0]:
                errors.append(f"{where}: ref_trim end must be after start")

    return errors


def portable_source(ref: str) -> str:
    """Describe a reference the way the manifest should record it.

    `ref_audio` is resolved to an absolute path before building, which is right
    for opening the file and wrong for the manifest: that file is committed, so
    an absolute path bakes one machine's home directory into the repo. Record it
    relative to the skill instead, matching the form `characters.json` uses.

    Nothing reads this field as a path — `check_separation` compares two of them
    and the gallery takes the basename — so relative is purely a portability
    win. Edge voices arrive here as a voice *name* rather than a path and are
    returned untouched.
    """
    if not ref or not os.path.isabs(ref):
        return ref
    try:
        return os.path.relpath(ref, ROOT)
    except ValueError:
        # Windows: no relative path exists across volumes.
        return ref


def check_separation(manifest: list[dict]) -> tuple[list[str], list[str]]:
    """Flag same-gender voices that may be hard to tell apart.

    Pitch separation only *decides* the question for voices derived from the
    same reference, because then pitch is the only thing that differs. Voices
    from different recordings also differ in accent, timbre and pace — a 184 Hz
    American and a 195 Hz British female are 11 Hz apart and obviously
    distinct — so for those it is reported as a note, not a failure.
    """
    errors, notes = [], []
    for i, a in enumerate(manifest):
        for b in manifest[i + 1:]:
            if a["gender"] != b["gender"]:
                continue
            gap = abs(a["f0"] - b["f0"])
            if gap >= MIN_F0_SEPARATION:
                continue
            pair = f"{a['name']} ({a['f0']} Hz) and {b['name']} ({b['f0']} Hz)"
            if a.get("source") == b.get("source"):
                errors.append(f"{pair} share a reference and are only {gap:.1f} Hz "
                              f"apart — they will sound like the same person. "
                              f"Shift one further or use another source.")
            else:
                notes.append(f"{pair} are {gap:.1f} Hz apart, but come from "
                             f"different references — check by ear that accent "
                             f"and delivery keep them distinct.")
    return errors, notes


async def build_reference(c: dict, dest: Path) -> str:
    """Produce the reference clip for one character; returns its transcript."""
    if c.get("ref_audio"):
        src = Path(c["ref_audio"]).expanduser()
        trim = c.get("ref_trim")
        prepare_ref(src, dest, denoise=c.get("denoise", True),
                    trim=(tuple(trim) if trim else None))
        return c["ref_text"]

    line = AUDITION[c["lang"]]
    raw = dest.with_suffix(".raw.wav")
    await edge_reference(line, c["source_voice"], raw,
                         pitch=c.get("pitch", "+0Hz"),
                         rate=c.get("rate", "+0%"))
    # Edge output is already clean; denoising it only risks dulling sibilants.
    prepare_ref(raw, dest, denoise=False, quiet=True)
    raw.unlink(missing_ok=True)
    return line


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--characters", type=Path, required=True)
    ap.add_argument("--validate", action="store_true",
                    help="check the definitions and exit without generating")
    ap.add_argument("--only", help="build only these characters "
                                   "(comma-separated keys)")
    ap.add_argument("--tries", type=int, default=DEFAULT_TRIES,
                    help=f"candidates per character, best match kept "
                         f"(default {DEFAULT_TRIES}; 1 disables)")
    args = ap.parse_args()

    if not args.characters.exists():
        sys.exit(f"Not found: {args.characters}")

    data = json.loads(args.characters.read_text(encoding="utf-8"))
    chars = data["characters"] if isinstance(data, dict) else data

    # A relative ref_audio is resolved against the characters file, not the
    # working directory, so a cast definition stays valid wherever it is run
    # from and whoever cloned the repo.
    base = args.characters.resolve().parent
    for c in chars:
        ref = c.get("ref_audio")
        if ref:
            p = Path(ref).expanduser()
            c["ref_audio"] = str(p if p.is_absolute() else (base / p).resolve())

    errors = validate(chars)
    if errors:
        print("Definition errors:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"{len(chars)} character(s) defined — all valid.")
    if args.validate:
        return 0

    if args.only:
        wanted = {k.strip() for k in args.only.split(",") if k.strip()}
        unknown = wanted - {c["key"] for c in chars}
        if unknown:
            sys.exit(f"No character with key: {', '.join(sorted(unknown))}")
        chars = [c for c in chars if c["key"] in wanted]

    CAST.mkdir(parents=True, exist_ok=True)
    REFS.mkdir(parents=True, exist_ok=True)

    edge_chars = [c for c in chars if (c.get("engine") or "clone") == "edge"]
    clone_chars = [c for c in chars if (c.get("engine") or "clone") != "edge"]

    manifest: list[dict] = []
    failures: list[str] = []

    # Edge characters speak directly, so they need no reference and no model.
    # Doing them first means a cast of only Edge voices never loads OmniVoice.
    if edge_chars:
        print(f"\nRendering {len(edge_chars)} Edge voice(s) directly...")
        for c in edge_chars:
            final = CAST / f"{c['key']}.mp3"
            try:
                await edge_speak(AUDITION[c["lang"]], c["source_voice"], final,
                                 pitch=c.get("pitch", "+0Hz"),
                                 rate=c.get("rate", "+0%"))
            except Exception as exc:                   # noqa: BLE001
                print(f"  FAIL {c['key']}: {exc}", file=sys.stderr)
                failures.append(c["key"])
                continue
            m = measure(final)
            problems = check(m, c["gender"])
            manifest.append({
                "key": c["key"], "name": c["name"], "lang": c["lang"],
                "gender": c["gender"], "persona": c.get("persona", ""),
                "engine": "edge", "source": c["source_voice"],
                "ref_text": "", "instruct": "None",
                # An Edge voice *is* its own source, so there is nothing for it
                # to drift from. Recording 0.0 keeps the manifest shape uniform.
                "ref_f0": m["f0"], "drift_pct": 0.0,
                **m,
            })
            print(f"  {c['name']:<12} {m['f0']:6.1f} Hz  {m['dur']:5.1f}s  "
                  f"noise {m['noise_floor']:6.1f} dB  gaps {m['gaps']}"
                  f"{'  <-- FAILS' if problems else ''}")
            for p in problems:
                print(f"      ! {p}")
                failures.append(f"{c['key']}: {p}")

    chars = clone_chars
    if not chars:
        return finish(manifest, failures, args)

    print("\nBuilding references...")
    ref_texts: dict[str, str] = {}
    for c in chars:
        print(f"  {c['name']} ({c['key']})")
        ref_texts[c["key"]] = await build_reference(c, REFS / f"{c['key']}.wav")

    print("\nLoading OmniVoice (first run downloads ~2.5 GB)...")
    model = load_model()

    print("\nCloning voices...")
    for c in chars:
        key = c["key"]
        ref_clip = REFS / f"{key}.wav"
        final = CAST / f"{key}.mp3"

        try:
            ref_profile = voice_profile(ref_clip)
            ref_f0 = median_f0(ref_clip)["median"]
        except Exception:                              # noqa: BLE001
            ref_profile, ref_f0 = None, 0.0

        best = None
        for attempt in range(args.tries):
            raw = CAST / f"_{key}_{attempt}.wav"
            cand = CAST / f"_{key}_{attempt}.mp3"
            try:
                synth(model, AUDITION[c["lang"]], c["lang"],
                      ref_clip, ref_texts[key], raw,
                      instruct=c.get("instruct", "None"))
            except Exception as exc:                   # noqa: BLE001
                print(f"  FAIL {key} (try {attempt + 1}): {exc}", file=sys.stderr)
                raw.unlink(missing_ok=True)
                continue
            master(raw, cand, extra_denoise=bool(c.get("ref_audio")))
            raw.unlink(missing_ok=True)

            m = measure(cand)
            score = candidate_score(cand, m, ref_profile, ref_f0)
            # Reject candidates that fail acceptance outright, unless every
            # attempt failed — a flawed voice still beats no voice to inspect.
            rank = (bool(check(m, c["gender"])), score)
            if best is None or rank < best[0]:
                if best is not None:
                    best[1].unlink(missing_ok=True)
                best = (rank, cand, m, score)
            else:
                cand.unlink(missing_ok=True)

        if best is None:
            failures.append(key)
            continue

        _rank, cand, m, score = best
        cand.replace(final)

        problems = check(m, c["gender"])
        entry = {
            "key": key, "name": c["name"], "lang": c["lang"],
            "gender": c["gender"], "persona": c.get("persona", ""),
            "engine": "clone",
            "source": portable_source(c.get("source_voice") or c.get("ref_audio")),
            "ref_text": ref_texts[key],
            "instruct": c.get("instruct", "None"),
            "ref_f0": ref_f0,
            "drift_pct": (round(abs(m["f0"] - ref_f0) / ref_f0 * 100, 1)
                          if ref_f0 else None),
            **m,
        }
        manifest.append(entry)

        flag = "  <-- FAILS" if problems else ""
        drift = f"  drift {entry['drift_pct']:>4.1f}%" if entry["drift_pct"] is not None else ""
        pick = f"  (best of {args.tries})" if args.tries > 1 else ""
        print(f"  {c['name']:<12} {m['f0']:6.1f} Hz  {m['dur']:5.1f}s  "
              f"noise {m['noise_floor']:6.1f} dB  gaps {m['gaps']}{drift}{flag}{pick}")
        for p in problems:
            print(f"      ! {p}")
            failures.append(f"{key}: {p}")

    return finish(manifest, failures, args)


def finish(manifest: list[dict], failures: list[str], args) -> int:
    """Merge, write and validate the manifest. Shared by both engines."""
    manifest.sort(key=lambda e: (e["lang"], e["gender"], e["f0"]))
    manifest_path = CAST / "manifest.json"

    # --only must not discard characters built by earlier runs.
    if args.only and manifest_path.exists():
        rebuilt = {e["key"] for e in manifest}
        previous = [e for e in json.loads(manifest_path.read_text(encoding="utf-8"))["characters"]
                    if e["key"] not in rebuilt]
        manifest = sorted(manifest + previous,
                          key=lambda e: (e["lang"], e["gender"], e["f0"]))

    manifest_path.write_text(json.dumps(
        {"audition": AUDITION, "characters": manifest}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    sep_errors, sep_notes = check_separation(manifest)
    for e in sep_errors:
        print(f"\n  ! {e}")
        failures.append(e)
    for n in sep_notes:
        print(f"\n  note: {n}")

    print(f"\n-> {manifest_path}")
    print(f"   {len(manifest)} voice(s) built, {len(failures)} problem(s)")
    if failures:
        print("\nNot done yet — see reference/troubleshooting.md")
        return 1

    print("\nAll checks passed. Review with: .venv/bin/python scripts/serve.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
