#!/usr/bin/env bash
# Set up the voice-booth environment.
#
# Python 3.12 specifically: 3.13/3.14 break much of the TTS ecosystem (missing
# cp313/cp314 wheels, packages pinning numpy<=1.26.4). Failing loudly here is
# better than a half-installed venv that errors deep inside a generation run.
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

echo "voice-booth setup"
echo "  root: $ROOT"

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "ERROR: requires Apple Silicon (macOS arm64) — MLX has no other backend." >&2
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ERROR: ffmpeg not found. Install with: brew install ffmpeg" >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv not found. Install with: brew install uv" >&2
  echo "       (or: curl -LsSf https://astral.sh/uv/install.sh | sh)" >&2
  exit 1
fi

if [[ ! -d .venv ]]; then
  echo "  creating .venv (Python 3.12)..."
  uv venv --python 3.12 .venv
fi

PY_VER="$(.venv/bin/python -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
if [[ "$PY_VER" != "3.12" ]]; then
  echo "ERROR: .venv is Python $PY_VER, need 3.12. Delete .venv and re-run." >&2
  exit 1
fi

echo "  installing dependencies..."
uv pip install --python .venv/bin/python \
  mlx-audio edge-tts numpy soundfile mlx-whisper

echo
echo "Verifying..."
.venv/bin/python - <<'PY'
import importlib, sys
missing = []
for mod in ("mlx_audio", "edge_tts", "numpy", "mlx_whisper"):
    try:
        importlib.import_module(mod)
        print(f"  ok   {mod}")
    except Exception as exc:
        missing.append(mod)
        print(f"  FAIL {mod}: {exc}")
sys.exit(1 if missing else 0)
PY

echo
echo "Done. Next:"
echo "  1. edit templates/characters.json"
echo "  2. .venv/bin/python scripts/build_cast.py --characters templates/characters.json"
echo
echo "First build downloads ~2.5 GB of model weights."
