#!/usr/bin/env bash
# Stage a self-contained render payload for `azc offload`.
#
# `style-2d-animation/scripts/audio.py` loads `style-paper`'s audio engine by
# explicit relative path (`../../style-paper/scripts`), deliberately, so that a
# fix to the shared mixer reaches both styles. That means a payload containing
# only this style renders silently on a bare machine -- the classic offload
# failure the compute skill warns about, in its cross-skill form. So the
# sibling goes up too, with the directory layout preserved exactly.
set -euo pipefail

SKILL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CREW="$(cd "$SKILL/.." && pwd)"
STAGE="${1:?usage: stage-render.sh <staging-dir>}"

rm -rf "$STAGE"
mkdir -p "$STAGE/skills/style-2d-animation" "$STAGE/skills/style-paper/scripts" "$STAGE/out"

# --exclude keeps scratch, caches and rendered video out of the upload: the
# payload is shipped over the wire on every run, and a stale mp4 in examples/
# would be uploaded only to be overwritten.
rsync -a \
  --exclude '.peak-scratch' --exclude '__pycache__' --exclude '*.pyc' \
  --exclude '.DS_Store' --exclude 'vo' --exclude '*.mp4' \
  "$SKILL"/ "$STAGE/skills/style-2d-animation/"

rsync -a --exclude '__pycache__' --exclude '*.pyc' \
  "$CREW/style-paper/scripts"/ "$STAGE/skills/style-paper/scripts/"

echo "staged -> $STAGE"
du -sh "$STAGE" | sed 's/^/  /'
