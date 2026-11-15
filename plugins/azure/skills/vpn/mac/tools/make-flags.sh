#!/bin/bash
# Regenerates the flat circular flag PNGs drawn by FlagBadge (Sources/AvenVPN/Flags.swift)
# into Assets/Flags/<CC>.png, 132 px (the largest badge, 44 pt, at 3x).
# Source: HatScripts/circle-flags (MIT, Assets/Flags/LICENSE.md).
# Only the ISO codes the app can show are fetched: every country in Countries.swift plus every
# RegionChoice in Config.swift. Needs rsvg-convert (brew install librsvg); Pillow optional.
set -euo pipefail
MAC="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$MAC/Sources/AvenVPN"
OUT="$MAC/Assets/Flags"
BASE="https://raw.githubusercontent.com/HatScripts/circle-flags/gh-pages"

codes=$( { grep -oE '^ +\("[A-Z]{2}"' "$SRC/Countries.swift" | grep -oE '[A-Z]{2}'
           grep -oE 'country: "[A-Z]{2}"' "$SRC/Config.swift" | grep -oE '[A-Z]{2}'; } | sort -u)

mkdir -p "$OUT"
curl -sfL "$BASE/LICENSE.md" -o "$OUT/LICENSE.md"
rm -f "$OUT"/*.png
for c in $codes; do
  lc=$(echo "$c" | tr 'A-Z' 'a-z')
  svg=$(curl -sfL "$BASE/flags/$lc.svg") || { echo "missing upstream flag: $c" >&2; continue; }
  # Some upstream files are git symlinks (their body is just the target, e.g. "no.svg").
  case "$svg" in "<"*) ;; *) svg=$(curl -sfL "$BASE/flags/$svg") ;; esac
  printf '%s' "$svg" | rsvg-convert -w 132 -h 132 -o "$OUT/$c.png"
done

# Lossless re-encode (drops metadata, max zlib), keeping the anti-aliased edge intact.
python3 - "$OUT" <<'PY' 2>/dev/null || true
import sys, glob
from PIL import Image
for p in glob.glob(sys.argv[1] + "/*.png"):
    Image.open(p).save(p, optimize=True)
PY
echo "$(ls "$OUT"/*.png | wc -l | tr -d ' ') flags, $(du -sh "$OUT" | cut -f1)"
