"""Narration synthesis with natural, prosody-aware voices.

Five providers, tried in order:

  cast    voice-booth named cast        PRIMARY — measured voices, Tamil-capable
  edge    Microsoft Edge neural voices   free, keyless, natural — the backup
  gemini  gemini-2.5-flash-preview-tts   free tier, style directed in prose
  openai  gpt-4o-mini-tts                paid, explicit `instructions` field
  say     macOS built-in                 offline fallback, prosody via [[…]]

`cast` is first and is the intended route: named characters (Valluvar, Meera,
Everett…) that have been measured for pitch, timbre separation, uneven pauses
and pitch spikes, and that speak Tamil and Tanglish as well as English. It
serves a line only when `voice` names a cast character *and* the skill's
`.venv` and built cast are present; otherwise it returns False and the chain
continues, so a machine without the 2.5 GB model still renders a film.

`edge` is the backup: free, keyless, still human-sounding, and the right answer
for a raw provider voice id like `en-GB-RyanNeural`. The two API providers are
more *directable* — you tell them how to read the line — so set `provider`
explicitly if you have a key and want a specific performance. `say` is a
formant synthesiser and will always sound synthetic; it is here so the pipeline
runs on a bare machine, not because it sounds good.

Credentials come from the environment only, and are never written to disk:

    GEMINI_API_KEY   (or GOOGLE_API_KEY)
    OPENAI_API_KEY
"""

from __future__ import annotations

import base64
import json
import math
import os
import re
import shutil
import struct
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parent.parent

# ------------------------------------------------------------------ markup ----

EMPH_RE = re.compile(r"\*([^*]+)\*")
SLNC_RE = re.compile(r"\[\[slnc\s+(\d+)\]\]")
CLAUSE_RE = re.compile(r"([.!?,;:—]+)")

# Formant synthesis is thin and hissy; roll off the shout band, add chest and a
# breath of air so the fallback at least sits in the same room as the music.
SAY_WARMTH = (
    "highpass=f=80,"
    "equalizer=f=240:t=q:w=1.1:g=2.4,"
    "equalizer=f=3100:t=q:w=1.5:g=-4.5,"
    "equalizer=f=5400:t=q:w=2.0:g=-3.0,"
    "treble=g=1.6:f=9000,"
    "aecho=0.92:0.85:16:0.055"
)

_VOICES = None


def _say_voices() -> set:
    global _VOICES
    if _VOICES is None:
        try:
            out = subprocess.run(["say", "-v", "?"], capture_output=True,
                                 text=True, check=True).stdout
            _VOICES = {ln.split()[0] for ln in out.splitlines() if ln.strip()}
        except Exception:
            _VOICES = set()
    return _VOICES


def strip_markup(text: str) -> str:
    """Plain words, for the neural providers and for word counting."""
    text = EMPH_RE.sub(r"\1", text)
    text = SLNC_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def emphasised(text: str) -> list[str]:
    return EMPH_RE.findall(text)


def word_count(text: str) -> int:
    return len(strip_markup(text).split())


# ------------------------------------------------------------------- wav ------


def _pcm_to_wav(pcm: bytes, path: str, rate: int = 24000, channels: int = 1, width: int = 2):
    n = len(pcm)
    hdr = b"RIFF" + struct.pack("<I", 36 + n) + b"WAVEfmt " + struct.pack(
        "<IHHIIHH", 16, 1, channels, rate, rate * channels * width, channels * width, width * 8
    ) + b"data" + struct.pack("<I", n)
    with open(path, "wb") as fh:
        fh.write(hdr)
        fh.write(pcm)


def _post(url: str, payload: dict, headers: dict, timeout: int = 120) -> bytes:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", **headers},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# --------------------------------------------------------------- providers ----


def _style_prompt(cfg: dict, text: str) -> str:
    """Describe the read. This is what buys natural pitch movement."""
    base = cfg.get(
        "style",
        "Read this as a warm, unhurried documentary narrator telling a bedtime "
        "story. Speak slowly and deliberately, about 105 words per minute. Let "
        "the pitch fall at the end of each sentence, and lift slightly on "
        "questions and on new information. Leave a real beat of silence at every "
        "comma and full stop.",
    )
    key = emphasised(text)
    if key:
        base += " Stress these words noticeably: " + ", ".join(f"'{k}'" for k in key) + "."
    return base


def gemini(text: str, out_wav: str, cfg: dict) -> bool:
    api = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api:
        return False
    model = cfg.get("model", "gemini-2.5-flash-preview-tts")
    voice = cfg.get("gemini_voice", cfg.get("voice", "Achernar"))
    prompt = f"{_style_prompt(cfg, text)}\n\n{strip_markup(text)}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}
            },
        },
    }
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={api}")
    try:
        raw = json.loads(_post(url, payload, {}))
        part = raw["candidates"][0]["content"]["parts"][0]["inlineData"]
        pcm = base64.b64decode(part["data"])
        rate = 24000
        m = re.search(r"rate=(\d+)", part.get("mimeType", ""))
        if m:
            rate = int(m.group(1))
        _pcm_to_wav(pcm, out_wav, rate=rate)
        return True
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError) as e:
        print(f"  ! gemini tts failed ({e}); falling back", flush=True)
        return False


def openai(text: str, out_wav: str, cfg: dict) -> bool:
    api = os.environ.get("OPENAI_API_KEY")
    if not api:
        return False
    payload = {
        "model": cfg.get("model", "gpt-4o-mini-tts"),
        "voice": cfg.get("openai_voice", "ballad"),
        "input": strip_markup(text),
        "instructions": _style_prompt(cfg, text),
        "response_format": "wav",
    }
    try:
        data = _post("https://api.openai.com/v1/audio/speech", payload,
                     {"Authorization": f"Bearer {api}"})
        with open(out_wav, "wb") as fh:
            fh.write(data)
        return True
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError) as e:
        print(f"  ! openai tts failed ({e}); falling back", flush=True)
        return False


def _contour(text: str, pbas: float, rate: int) -> str:
    """Give `say` an intonation contour instead of a flat readout.

    The formant synth is monotone by default: it holds one pitch for a whole
    sentence, which is most of what makes it sound robotic. Splitting the line
    into clauses and moving the pitch baseline across them — up on the way in,
    down into a full stop, up into a question — restores the shape a person
    actually uses, and costs nothing.
    """
    parts = [p for p in CLAUSE_RE.split(text) if p and p.strip()]
    if not parts:
        return text
    clauses, buf = [], ""
    for p in parts:
        if CLAUSE_RE.fullmatch(p):
            clauses.append((buf.strip(), p.strip()))
            buf = ""
        else:
            buf += p
    if buf.strip():
        clauses.append((buf.strip(), ""))
    clauses = [c for c in clauses if c[0]]
    if not clauses:
        return text

    out = []
    n = len(clauses)
    for i, (body, punct) in enumerate(clauses):
        u = i / max(1, n - 1)
        # lift into the line, then settle out of it
        lift = 4.5 * math.sin(math.pi * min(1.0, u * 1.15))
        if punct in ("?",):
            lift += 7.0
        elif punct in (".", "!") or (i == n - 1 and not punct):
            lift -= 5.0
        elif punct == ",":
            lift += 1.5
        pitch = max(20.0, pbas + lift)
        # emphasised words get a stress accent and a touch more time
        body = EMPH_RE.sub(
            lambda m: f"[[emph +]][[pbas {pitch + 7:.0f}]][[rate {int(rate * 0.9)}]]"
                      f"{m.group(1)}"
                      f"[[rate {rate}]][[pbas {pitch:.0f}]][[emph -]]",
            body)
        out.append(f"[[pbas {pitch:.0f}]]{body}{punct}")
        if punct in (".", "!", "?"):
            out.append("[[slnc 210]]")
        elif punct in (",", ";", ":"):
            out.append("[[slnc 110]]")
    return " ".join(out)


def macos_say(text: str, out_wav: str, cfg: dict) -> bool:
    """Offline fallback, pushed as far as the formant synth allows.

    `say` honours inline commands, so we can give it a pitch baseline, a wider
    swing than its very flat default, a clause-by-clause intonation contour and
    per-word emphasis, then warm the result with EQ. It still will not pass for
    a human — set GEMINI_API_KEY or OPENAI_API_KEY for that.
    """
    if not shutil.which("say"):
        return False
    voice = cfg.get("say_voice", cfg.get("voice", "Samantha"))
    if voice not in _say_voices():
        voice = "Samantha" if "Samantha" in _say_voices() else voice
    rate = int(cfg.get("rate", 140))
    pbas = float(cfg.get("pitch", 44))
    pmod = float(cfg.get("pitch_range", 62))

    tuned = f"[[pmod {pmod:.0f}]][[rate {rate}]]" + _contour(text, pbas, rate)

    aiff = tempfile.mktemp(suffix=".aiff")
    try:
        subprocess.run(["say", "-v", voice, "-o", aiff, tuned],
                       check=True, capture_output=True)
        ff = shutil.which("ffmpeg") or "ffmpeg"
        subprocess.run([ff, "-y", "-loglevel", "error", "-i", aiff,
                        "-af", SAY_WARMTH, "-ar", "48000", "-ac", "1", out_wav],
                       check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"  ! say failed ({e})", flush=True)
        return False
    finally:
        if os.path.exists(aiff):
            os.remove(aiff)


def _edge_bin() -> str | None:
    """Locate the edge-tts CLI. It is a Python package, so it usually lives in
    a virtualenv rather than on PATH."""
    cand = [os.environ.get("EDGE_TTS_BIN"), shutil.which("edge-tts")]
    here = os.path.dirname(os.path.abspath(__file__))
    cand += [
        os.path.join(here, "..", "tts_env", "bin", "edge-tts"),
        os.path.join(here, "tts_env", "bin", "edge-tts"),
        os.path.expanduser("~/.cache/film-crew/tts_env/bin/edge-tts"),
    ]
    for c in cand:
        if c and os.path.exists(c) and os.access(c, os.X_OK):
            return os.path.normpath(c)
    return None


def edge(text: str, out_wav: str, cfg: dict) -> bool:
    """Microsoft Edge neural voices — free, keyless and genuinely natural.

    edge-tts has no emphasis markup and ignores SSML, so `*word*` is dropped.
    `[[slnc N]]` is honoured *exactly* rather than approximated with ellipses:
    the line is split on each pause, every span is synthesised separately and
    the spans are re-joined with precisely N ms of digital silence. That keeps
    a storyboard's beat times valid whichever provider serves it.
    """
    exe = _edge_bin()
    if not exe:
        return False
    voice = cfg.get("edge_voice", cfg.get("voice", "en-IE-EmilyNeural"))
    rate = cfg.get("edge_rate", "-15%")
    pitch = cfg.get("edge_pitch", "-5Hz")
    volume = cfg.get("edge_volume", "+0%")

    spans, tmp = SLNC_RE.split(strip_markup(text)), []
    ff = shutil.which("ffmpeg") or "ffmpeg"
    try:
        parts = []
        for i, span in enumerate(spans):
            if i % 2:                                   # capture group = pause ms
                parts.append(("gap", int(span) / 1000.0))
                continue
            span = span.strip()
            if not span:
                continue
            mp3 = tempfile.mktemp(suffix=".mp3")
            tmp.append(mp3)
            subprocess.run([exe, "--voice", voice, f"--rate={rate}",
                            f"--pitch={pitch}", f"--volume={volume}",
                            "--text", span, "--write-media", mp3],
                           check=True, capture_output=True, timeout=180)
            if os.path.getsize(mp3) < 512:
                raise RuntimeError("edge-tts returned an empty clip")
            parts.append(("audio", mp3))

        if not any(k == "audio" for k, _ in parts):
            return False

        # concat filter graph: real spans plus exact silences between them
        ins, filt, labels = [], [], []
        for n, (kind, val) in enumerate(parts):
            if kind == "audio":
                ins += ["-i", val]
                filt.append(f"[{len(ins)//2 - 1}:a]aresample=48000,aformat="
                            f"sample_fmts=s16:channel_layouts=mono[a{n}]")
            else:
                filt.append(f"anullsrc=r=48000:cl=mono,atrim=0:{val:.3f},"
                            f"aformat=sample_fmts=s16:channel_layouts=mono[a{n}]")
            labels.append(f"[a{n}]")
        graph = ";".join(filt) + ";" + "".join(labels) + \
                f"concat=n={len(parts)}:v=0:a=1[out]"
        subprocess.run([ff, "-y", "-loglevel", "error", *ins,
                        "-filter_complex", graph, "-map", "[out]",
                        "-ar", "48000", "-ac", "1", out_wav],
                       check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            FileNotFoundError, RuntimeError, ValueError) as e:
        detail = getattr(e, "stderr", b"") or b""
        if isinstance(detail, bytes):
            detail = detail.decode("utf8", "replace")
        print(f"  ! edge tts failed ({e}) {detail.strip()[:160]}; falling back",
              flush=True)
        return False
    finally:
        for f in tmp:
            if os.path.exists(f):
                os.remove(f)


def _cast_manifest() -> dict | None:
    """The voice-booth cast manifest, or None if the cast was never built."""
    p = _SKILL_ROOT / "out" / "cast" / "manifest.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:                                   # noqa: BLE001
        return None


def cast_voices() -> list[str]:
    """Every named cast voice, lowercase. Empty if the cast is unavailable."""
    m = _cast_manifest()
    if not m:
        return []
    return [c["key"].lower() for c in m.get("characters", [])]


def cast(text: str, out_wav: str, cfg: dict) -> bool:
    """Render with a named cast voice — the primary provider.

    Returns False (rather than raising) whenever this route cannot serve the
    request, so `synth()` falls through to edge/gemini/openai/say. That is the
    whole point: the cast gives named, measured, Tamil-capable voices, and the
    older providers remain as a backup for when it is not set up, not built, or
    the requested voice is a raw provider id like `en-GB-RyanNeural`.

    It runs `voice.py` in this skill's own `.venv` rather than importing it,
    because the cast needs MLX and a 2.5 GB model that the interpreter running
    the film pipeline has no reason to carry.
    """
    voice = (cfg.get("voice") or "").strip().lower()
    if not voice or voice not in cast_voices():
        return False

    py = _SKILL_ROOT / ".venv" / "bin" / "python"
    script = _SKILL_ROOT / "scripts" / "voice.py"
    if not py.exists() or not script.exists():
        return False

    cmd = [str(py), str(script), "--script", strip_markup(text),
           "--voice", voice, "--out", out_wav]
    lang = cfg.get("language")
    if lang in ("ta", "en"):
        cmd += ["--language", lang]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    except Exception as exc:                            # noqa: BLE001
        print(f"  ! cast provider failed ({exc})", flush=True)
        return False
    if r.returncode != 0 or not os.path.exists(out_wav):
        detail = (r.stderr or r.stdout or "").strip().splitlines()
        print(f"  ! cast voice '{voice}' failed"
              f"{': ' + detail[-1] if detail else ''} — falling back", flush=True)
        return False
    return True


PROVIDERS = {"cast": cast, "edge": edge, "gemini": gemini, "openai": openai,
             "say": macos_say}
ORDER = ["cast", "edge", "gemini", "openai", "say"]


def available() -> list[str]:
    out = []
    if cast_voices() and (_SKILL_ROOT / ".venv" / "bin" / "python").exists():
        out.append("cast")
    if _edge_bin():
        out.append("edge")
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        out.append("gemini")
    if os.environ.get("OPENAI_API_KEY"):
        out.append("openai")
    if shutil.which("say"):
        out.append("say")
    return out


def synth(text: str, out_wav: str, cfg: dict | None = None) -> str:
    """Render one narration line. Returns the provider that actually served it."""
    cfg = cfg or {}
    want = cfg.get("provider", "auto")
    order = ORDER if want in ("auto", None) else [want] + [p for p in ORDER if p != want]
    for name in order:
        if PROVIDERS[name](text, out_wav, cfg):
            return name
    raise RuntimeError("no TTS provider available (need GEMINI_API_KEY, "
                       "OPENAI_API_KEY, or macOS `say`)")
