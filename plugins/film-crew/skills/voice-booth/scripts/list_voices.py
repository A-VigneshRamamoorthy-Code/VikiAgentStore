#!/usr/bin/env python3
"""List free Edge neural voices usable as cloning references.

    python scripts/list_voices.py --lang ta
    python scripts/list_voices.py --lang en --gender female

These need no API key and no account. Prefer distinct regional speakers over
pitch-shifted variants — they sound genuinely different, whereas a shifted
reference is the same person at another setting.
"""

from __future__ import annotations

import argparse
import asyncio


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", help="language prefix, e.g. ta, en, en-GB")
    ap.add_argument("--gender", choices=["male", "female"])
    args = ap.parse_args()

    import edge_tts

    voices = await edge_tts.list_voices()
    rows = []
    for v in voices:
        short, gender = v["ShortName"], v["Gender"].lower()
        if args.lang and not short.lower().startswith(args.lang.lower()):
            continue
        if args.gender and gender != args.gender:
            continue
        rows.append((short, gender, v.get("Locale", ""),
                     ", ".join(v.get("VoiceTag", {}).get("VoicePersonalities", []))))

    if not rows:
        print("No voices matched.")
        return 1

    rows.sort()
    print(f"{'voice':<32}{'gender':<9}{'locale':<10}personality")
    for short, gender, locale, tags in rows:
        print(f"{short:<32}{gender:<9}{locale:<10}{tags}")
    print(f"\n{len(rows)} voice(s)")

    locales = {r[2] for r in rows}
    if len(locales) > 1:
        print(f"{len(locales)} distinct locales — use these before pitch-shifting.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
