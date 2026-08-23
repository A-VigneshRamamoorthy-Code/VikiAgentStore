#!/usr/bin/env python3
"""Generate demo samples for the gallery, one per line in a samples spec.

    python scripts/build_samples.py
    python scripts/build_samples.py --samples templates/samples.json --only karthik

Each sample's language is DETECTED from its text rather than declared, which is
what the gallery is demonstrating. Writes out/samples/<n>_<voice>.mp3 and
out/samples/manifest.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import (  # noqa: E402
    OUT, REFS, detect_lang, edge_speak, load_manifest, load_model, master,
    measure, synth,
)

SAMPLES = OUT / "samples"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=Path,
                    default=Path(__file__).resolve().parent.parent
                    / "templates" / "samples.json")
    ap.add_argument("--only", help="only samples for this voice key")
    args = ap.parse_args()

    spec = json.loads(args.samples.read_text(encoding="utf-8"))
    items = spec["samples"] if isinstance(spec, dict) else spec
    if args.only:
        items = [s for s in items if s["voice"] == args.only]
    if not items:
        sys.exit("No samples to build.")

    cast = {c["key"]: c for c in load_manifest()["characters"]}
    missing = {s["voice"] for s in items} - cast.keys()
    if missing:
        sys.exit(f"Unknown voice(s): {', '.join(sorted(missing))}. "
                 f"Build the cast first.")

    SAMPLES.mkdir(parents=True, exist_ok=True)
    print(f"{len(items)} sample(s)\n")

    out: list[dict] = []
    failures = 0
    model = None                    # loaded lazily — an all-edge set never needs it

    for i, s in enumerate(items):
        voice, text = s["voice"], s["text"]
        entry = cast[voice]
        d = detect_lang(text)
        engine = entry.get("engine") or "clone"

        key = f"{i:02d}_{voice}"
        raw = SAMPLES / f"_{key}.wav"
        final = SAMPLES / f"{key}.mp3"

        print(f"  {entry['name']:<10} {d['label']:<9} {s.get('title','')}")
        try:
            if engine == "edge":
                source = entry.get("source") or entry.get("source_voice")
                if not source:
                    raise RuntimeError("engine=edge but no source voice recorded")
                asyncio.run(edge_speak(text, source, raw, raw=True))
            else:
                if model is None:
                    model = load_model()
                synth(model, text, d["lang"], REFS / f"{voice}.wav",
                      entry["ref_text"], raw)
        except Exception as exc:                        # noqa: BLE001
            print(f"    FAIL: {exc}", file=sys.stderr)
            failures += 1
            continue

        master(raw, final, extra_denoise=(engine != "edge"))
        raw.unlink(missing_ok=True)
        m = measure(final)

        out.append({
            "file": final.name, "voice": voice, "name": entry["name"],
            "gender": entry["gender"], "title": s.get("title", ""),
            "text": text, "label": d["label"], "lang": d["lang"],
            "tamil_ratio": round(d["tamil_ratio"], 3), **m,
        })
        print(f"    {m['dur']:.1f}s  {m['f0']:.1f} Hz  "
              f"noise {m['noise_floor']:.1f} dB  gaps {m['gaps']}")

    (SAMPLES / "manifest.json").write_text(
        json.dumps({"samples": out}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"\n-> {SAMPLES / 'manifest.json'}  ({len(out)} built, {failures} failed)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
