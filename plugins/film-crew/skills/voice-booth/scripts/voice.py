#!/usr/bin/env python3
"""Turn a script into narrated audio in a named cast voice.

    python scripts/voice.py --script "வணக்கம் நண்பர்களே!" --voice meera
    python scripts/voice.py --script @episode.txt --voice everett --out ep1.mp3
    python scripts/voice.py --list

This is the skill's front door. Everything else in scripts/ exists to build,
measure or audition the voices this command speaks with.

Language is decided per sentence from the text itself, so a script that mixes
Tamil, Tanglish and English is voiced correctly throughout without any flags.
`--language` forces one language for the whole script when detection guesses
wrong — usually only needed for Tamil written in Latin letters.

Two engines sit behind `--voice`, chosen per character in the manifest and
never by the caller:

- `edge`  — speaks directly with a Microsoft neural voice. No model load, no
  reference audio, about a second per clip.
- `clone` — reproduces a specific person's timbre with OmniVoice. Loads a
  2.5 GB model once, then 45-60 s per sentence.

A script that uses only `edge` voices never loads the model at all.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import (  # noqa: E402
    AUDITION, MASTER_CHAIN, NONVERBAL_TAGS, REFS,
    detect_lang, edge_speak, load_manifest, load_model, nonverbal_hint,
    prepare_ref,
    synth, unknown_nonverbal,
)

# OmniVoice's duration estimator degrades on long inputs and the delivery
# flattens, so text is synthesized a sentence at a time and joined. The chunk
# boundaries double as natural phrase breaks.
MAX_CHUNK_CHARS = 180


def read_script(value: str) -> str:
    """Resolve --script, which takes text inline or @path to read from a file.

    The @ form exists because a real script contains quotes, newlines and
    punctuation that a shell mangles, and because Tamil text is far easier to
    keep in a UTF-8 file than to paste into a terminal.
    """
    if value.startswith("@"):
        path = Path(value[1:]).expanduser()
        if not path.exists():
            sys.exit(f"Script file not found: {path}")
        text = path.read_text(encoding="utf-8")
    else:
        text = value
    text = text.strip()
    if not text:
        sys.exit("Script is empty.")
    return text


def split_sentences(text: str) -> list[str]:
    """Split into synthesis chunks on sentence enders, including Tamil danda."""
    parts = re.split(r"(?<=[.!?।])\s+", text.strip())
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if len(p) > MAX_CHUNK_CHARS:        # long sentences drone; break at commas
            out.extend(s.strip() for s in re.split(r"(?<=,)\s+", p) if s.strip())
        else:
            out.append(p)
    return out


def find_voice(key: str) -> dict:
    """Look a character up by key or display name, case-insensitively.

    Callers reach for the name they saw in the gallery ("Divya"), not the
    manifest key ("divya"), and an exact-match-only lookup turns that into a
    confusing failure.
    """
    chars = load_manifest()["characters"]
    want = key.strip().lower()
    for c in chars:
        if c["key"].lower() == want or c["name"].lower() == want:
            return c
    names = ", ".join(c["key"] for c in chars)
    sys.exit(f"No voice '{key}'.\nAvailable: {names}\nRun --list for details.")


def warn_stray_tags(text: str) -> None:
    """Unrecognised [bracket] tags are read aloud as words.

    Nothing downstream can detect this — the audio is valid, just wrong — so
    it has to be caught before synthesis.
    """
    stray = unknown_nonverbal(text)
    if not stray:
        return
    for tag in stray:
        hint = nonverbal_hint(tag)
        print(f"  warning: {tag} will be spoken as words, not performed."
              f"{'  ' + hint if hint else ''}", file=sys.stderr)
    print(f"  supported: {', '.join('[' + t + ']' for t in NONVERBAL_TAGS)}",
          file=sys.stderr)


def join_and_master(parts: list[Path], out: Path, tmp: Path, raw: bool) -> None:
    """Concatenate chunks and apply the shared mastering chain."""
    if len(parts) == 1:
        joined = parts[0]
    else:
        listing = tmp / "list.txt"
        listing.write_text("".join(f"file '{p}'\n" for p in parts), encoding="utf-8")
        joined = tmp / "joined.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
             "-i", str(listing), "-c", "copy", str(joined)], check=True)

    out.parent.mkdir(parents=True, exist_ok=True)
    chain = [] if raw else ["-af", MASTER_CHAIN]
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(joined), *chain,
         "-ar", "44100", "-b:a", "192k", str(out)], check=True)


def narrate_edge(entry: dict, chunks: list[str], out: Path,
                 tmp: Path, raw: bool) -> None:
    """Speak every chunk with the character's Edge voice."""
    voice = entry.get("source") or entry.get("source_voice")
    if not voice:
        sys.exit(f"Voice '{entry['key']}' is engine=edge but records no source "
                 f"voice. Rebuild it with build_cast.py.")
    parts: list[Path] = []
    for i, chunk in enumerate(chunks):
        seg = tmp / f"{i:03d}.wav"
        asyncio.run(edge_speak(chunk, voice, seg, raw=True))
        parts.append(seg)
        print(f"  [{i + 1}/{len(chunks)}] {chunk[:56]}")
    join_and_master(parts, out, tmp, raw)


def narrate_clone(entry: dict, chunks: list[str], langs: list[str], out: Path,
                  tmp: Path, raw: bool, instruct: str,
                  ref_override: Path | None = None,
                  ref_text_override: str | None = None) -> None:
    """Speak every chunk by cloning a reference.

    Normally the character's own reference from `out/refs/`; `ref_override`
    clones from an arbitrary recording instead, for auditioning a voice before
    committing it to the cast.
    """
    if ref_override is not None:
        ref = ref_override
        ref_text = ref_text_override or ""
    else:
        ref = REFS / f"{entry['key']}.wav"
        if not ref.exists():
            sys.exit(f"Reference missing: {ref}\n"
                     f"Rebuild with: scripts/build_cast.py --only {entry['key']}")
        ref_text = entry.get("ref_text") or AUDITION[entry["lang"]]
        if instruct == "None":
            instruct = entry.get("instruct", "None")

    model = load_model()
    parts: list[Path] = []
    for i, (chunk, lang) in enumerate(zip(chunks, langs)):
        seg = tmp / f"{i:03d}.wav"
        synth(model, chunk, lang, ref, ref_text, seg, instruct=instruct)
        parts.append(seg)
        print(f"  [{i + 1}/{len(chunks)}] {chunk[:56]}")
    join_and_master(parts, out, tmp, raw)


def list_voices() -> int:
    m = load_manifest()
    print(f"{'voice':<11}{'name':<11}{'lang':<6}{'sex':<4}{'engine':<8}"
          f"{'F0':>7}  persona")
    for c in sorted(m["characters"], key=lambda c: (c["lang"], c["gender"])):
        print(f"{c['key']:<11}{c['name']:<11}{c['lang']:<6}{c['gender'][:1]:<4}"
              f"{c.get('engine') or 'clone':<8}{c['f0']:7.1f}  "
              f"{c.get('persona', '')}")
    print("\nEvery voice speaks every language — the voice supplies the timbre, "
          "the script supplies the language.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Turn a script into narrated audio in a named cast voice.")
    ap.add_argument("--script", help="text to speak, or @path to read it from "
                                     "a UTF-8 file")
    ap.add_argument("--voice", help="character key or name (see --list)")
    ap.add_argument("--ref", type=Path,
                    help="clone from your own recording instead of a cast "
                         "voice. Requires --ref-text. Only use audio you have "
                         "the right to clone — see reference/consent.md")
    ap.add_argument("--ref-text", dest="ref_text",
                    help="exact transcript of --ref, word for word")
    ap.add_argument("--language", choices=["auto", "ta", "en"], default="auto",
                    help="force one language for the whole script "
                         "(default: detect per sentence)")
    ap.add_argument("--out", type=Path, default=Path("narration.mp3"),
                    help="output file (default: narration.mp3)")
    ap.add_argument("--instruct", default="None",
                    help="style direction for clone voices, e.g. \"Speak "
                         "naturally in colloquial spoken Tamil\"")
    ap.add_argument("--list", action="store_true",
                    help="show every available voice and exit")
    ap.add_argument("--raw", action="store_true",
                    help="skip mastering (loudness, de-ess, trim)")
    args = ap.parse_args()

    if args.list:
        return list_voices()
    if not args.script:
        return ap.error("--script is required (or use --list)")
    if args.voice and args.ref:
        return ap.error("use --voice or --ref, not both")
    if not (args.voice or args.ref):
        return ap.error("--voice or --ref is required (see --list)")
    if args.ref:
        if not args.ref_text:
            return ap.error("--ref-text is required with --ref: OmniVoice "
                            "aligns the reference against its transcript, and "
                            "a wrong one degrades the clone badly")
        if not args.ref.exists():
            return ap.error(f"reference not found: {args.ref}")

    text = read_script(args.script)
    entry = ({"key": "ref", "name": args.ref.name, "lang": "en",
              "engine": "clone"} if args.ref else find_voice(args.voice))
    chunks = split_sentences(text)
    warn_stray_tags(text)

    overall = detect_lang(text)
    forced = args.language if args.language != "auto" else None
    langs = [forced or detect_lang(c)["lang"] for c in chunks]

    engine = entry.get("engine") or "clone"
    print(f"{entry['name']} ({engine}): {len(chunks)} chunk(s) · "
          f"detected {overall['label']}"
          f"{' → forced ' + forced if forced else ''}")
    if overall["hint"]:
        print(f"  note: {overall['hint']}")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        if args.ref:
            print("Cloning from your reference — only use audio you may clone.")
            prepared = tmp / "ref.wav"
            prepare_ref(args.ref, prepared, denoise=True)
            narrate_clone(entry, chunks, langs, args.out, tmp, args.raw,
                          args.instruct, prepared, args.ref_text)
        elif engine == "edge":
            # Edge voices carry their language in the voice id itself, so the
            # detected language is informational only — a ta-IN voice reading
            # English still reads it with a Tamil accent, which is usually what
            # a Tanglish script wants.
            narrate_edge(entry, chunks, args.out, tmp, args.raw)
        else:
            narrate_clone(entry, chunks, langs, args.out, tmp, args.raw,
                          args.instruct)

    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
