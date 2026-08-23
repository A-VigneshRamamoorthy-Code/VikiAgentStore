#!/usr/bin/env python3
"""Shared core for voice-booth: audio prep, cloning, mastering, measurement.

Every hard-won constant in here was set by measurement, not taste. The comments
explain what breaks if you change them.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
REFS = OUT / "refs"
CAST = OUT / "cast"

MODEL_ID = "mlx-community/OmniVoice-bfloat16"

# Longest reference we will pass to the model. Longer clips are trimmed, but the
# caller is warned because ref_text must still describe what is in the audio.
#
# This MUST NOT exceed OmniVoice's own `ref_audio_max_duration_s`, which defaults
# to 10.0 s (see omnivoice.py). A larger value here is silently harmful: the clip
# passes our checks at, say, 12 s, the model reads only the first 10 s, and the
# tail of ref_text then describes audio the model never heard — the same
# misalignment that makes a clone rush and slur.
REF_MAX_S = 10.0

# Broadband hiss in a reference is baked into the cloned voice, so it is removed
# before the model ever sees it. Denoising the OUTPUT cannot undo this.
#
# Measured on a real noisy reference: noise floor -50.3 -> -68.7 dB, while the
# 300-3000 Hz speech bands were untouched (34.80 -> 34.82 and 24.21 -> 24.29 dB).
# nr=30 buys ~1.6 dB more but costs 9.6 dB at 6-12 kHz, dulling sibilants.
REF_DENOISE = "afftdn=nr=20:nf=-45:tn=1"

# The compressor below lifts quiet passages, and any residual hiss with them.
# Only applied on the clone path; Edge-sourced references are already clean.
OUTPUT_DENOISE = "afftdn=nr=12:nf=-50:tn=1"

MASTER_CHAIN = (
    "highpass=f=80,"                                    # rumble
    "equalizer=f=2800:t=q:w=1.5:g=2.0,"                 # presence/intelligibility
    "acompressor=threshold=-20dB:ratio=3:attack=6:release=160,"
    "silenceremove=start_periods=1:start_silence=0.1:start_threshold=-45dB:"
    "stop_periods=-1:stop_silence=0.4:stop_threshold=-45dB,"
    "loudnorm=I=-16:TP=-1.5:LRA=11"                     # broadcast loudness
)

# Same line for every character in a language — that is what makes them
# comparable. Tamil is deliberately COLLOQUIAL, not literary: written Tamil
# sounds like a legal notice being read aloud. See reference/tamil-naturalness.md
AUDITION = {
    "ta": ("வணக்கம் நண்பர்களே! இன்னைக்கு நான் சொல்ல போற விஷயம் கொஞ்சம் "
           "special-ஆ இருக்கும். தமிழ்ல ஒரு அழகான கதை. கேட்க தயாரா?"),
    "en": ("Hello everyone. What I want to share with you today is a little "
           "different. It is a beautiful story. Are you ready to hear it?"),
}

# Standard adult speaking-voice ranges. Deliberately wide: these exist to catch
# gender inversion (a "male" clone coming back at 355 Hz), not to enforce a
# house style. Real references legitimately sit near the edges — a deep American
# male measured 106 Hz and a bright Tamil female 256 Hz, both entirely correct.
F0_RANGE = {"male": (85, 180), "female": (165, 265)}

# Two voices derived from the SAME reference differ only in pitch, so they blur
# together below this gap. Voices from different recordings differ in accent,
# timbre and pace as well, so the gap alone does not decide — see
# check_separation() in build_cast.py.
MIN_F0_SEPARATION = 25.0

# Octave folding for the pitch tracker (`f0_track`). A frame further than this
# from the clip's median is folded by octaves until it is inside. The value sits
# between the largest real artefact seen (~9 st) and a true octave error (12 st),
# so genuine spikes survive and tracker glitches do not.
_OCTAVE_FOLD_ST = 10.0


# --------------------------------------------------------------------------
# language detection
# --------------------------------------------------------------------------

_TAMIL_CHAR = re.compile(r"[\u0B80-\u0BFF]")
_LATIN_CHAR = re.compile(r"[A-Za-z]")
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")

# Tamil written in Latin script. Split by ambiguity, because a single marker is
# only trustworthy if it cannot also be an ordinary English word or a name.
#
# Strong: no English meaning, so one occurrence is enough.
_ROMAN_TAMIL_STRONG = {
    "vanakkam", "nanbargale", "nanba", "neenga", "neengal", "avanga", "naanga",
    "namma", "unga", "ungal", "eppadi", "epdi", "ippo", "innaiku", "innaikku",
    "romba", "konjam", "irukku", "irukken", "irukeen", "irukkeenga", "irukkinga",
    "iruntha", "irundhu", "pannu", "panren", "pannunga", "panniten", "solren",
    "sollunga", "sonnen", "poren", "ponen", "vandhu", "vanthu", "vaanga", "varen",
    "theriyum", "theriyala", "mudiyala", "venum", "vendam", "kekka", "yaaru",
    "vishayam", "kadhai", "kathai", "thambi", "semma", "aana", "ennoda",
}

# Weak: also plausible English words or names ("Ava", "Anna", "naan" bread,
# "sari" the garment). Only counted when two or more appear together.
_ROMAN_TAMIL_WEAK = {
    "naan", "nee", "ava", "avan", "enna", "illa", "illai", "seri", "sari",
    "adhu", "idhu", "ithu", "athu", "enga", "amma", "appa", "akka", "paaru",
    "mattum", "sollu", "poga",
}

# English function words. These have no counterpart in romanised Tamil, so two
# or more of them mean the sentence is English even if it happens to contain
# words like "naan" or "sari" that are also Tamil.
_ENGLISH_STOPWORDS = {
    "the", "and", "with", "that", "this", "was", "were", "have", "has", "had",
    "for", "from", "they", "their", "there", "which", "would", "could", "should",
    "about", "into", "than", "then", "been", "being", "are", "our", "your",
}


def detect_lang(text: str) -> dict:
    """Decide which language to synthesize `text` in.

    Returns {"lang", "label", "tamil_ratio", "hint"} where `lang` is the code
    passed to the model ("ta"/"en") and `label` is what to show a human
    ("tamil" / "tanglish" / "english").

    Three real cases:

    - **tamil**    — Tamil script, no English words mixed in.
    - **tanglish** — the common register in Tamil media: Tamil script with
      English words dropped in ("special-ஆ இருக்கும்"). Synthesized as Tamil;
      the model handles the script switch.
    - **english**  — Latin script with no Tamil markers.

    Tamil written *in Latin script* ("vanakkam nanbargale") is reported as
    tanglish with a `hint`, because the Tamil G2P expects Tamil script.
    """
    ta = len(_TAMIL_CHAR.findall(text))
    la = len(_LATIN_CHAR.findall(text))

    if ta + la == 0:
        return {"lang": "en", "label": "english", "tamil_ratio": 0.0, "hint": None}

    ratio = ta / (ta + la)
    # Single stray letters (the "-a" in "special-ஆ") are not English words.
    latin_words = [w.lower() for w in _WORD.findall(text) if len(w) > 1]

    if ta and not latin_words:
        return {"lang": "ta", "label": "tamil", "tamil_ratio": ratio, "hint": None}

    if ratio >= 0.15:
        return {"lang": "ta", "label": "tanglish", "tamil_ratio": ratio, "hint": None}

    strong = sum(1 for w in latin_words if w in _ROMAN_TAMIL_STRONG)
    weak = sum(1 for w in latin_words if w in _ROMAN_TAMIL_WEAK)
    english = sum(1 for w in latin_words if w in _ENGLISH_STOPWORDS)

    if strong >= 1 or (weak >= 2 and english < 2):
        return {
            "lang": "ta" if ratio > 0 else "en",
            "label": "tanglish",
            "tamil_ratio": ratio,
            "hint": "Tamil written in Latin script — the Tamil G2P expects Tamil "
                    "script, so this is voiced with English phonetics. Write it "
                    "in Tamil script for accurate pronunciation.",
        }

    return {"lang": "en", "label": "english", "tamil_ratio": ratio, "hint": None}


# --------------------------------------------------------------------------
# shell helpers
# --------------------------------------------------------------------------

def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def duration_of(path: Path) -> float:
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "csv=p=0", str(path)])
    return float(out.stdout.strip())


# --------------------------------------------------------------------------
# reference preparation
# --------------------------------------------------------------------------

def prepare_ref(src: Path, dest: Path, denoise: bool = True,
                quiet: bool = False,
                trim: tuple[float, float] | None = None) -> float:
    """Convert any audio into the mono 24 kHz clip OmniVoice wants.

    A clean, dry 4-10 s clip of continuous speech works best; OmniVoice reads at
    most 10 s. Background music, a second speaker or heavy reverb all get cloned
    along with the voice, and a short clean clip beats a long dirty one.

    The clip is NOT blindly truncated: ref_text has to match what is actually in
    the audio, so cutting mid-word silently corrupts the clone. Over-long input
    is trimmed and the caller is warned.

    `trim` is an explicit (start, end) window in seconds, used to cut a reference
    down to its usable part - dropping a stray English brand name, a second
    speaker or a cough. Whatever is cut away must also be cut from ref_text.
    """
    if not src.exists():
        sys.exit(f"Reference audio not found: {src}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    dur = duration_of(src)

    cut: list[str] = []
    if trim:
        start, end = trim
        cut = ["-ss", str(start), "-t", str(max(0.0, end - start))]
        dur = max(0.0, end - start)
        if not quiet:
            print(f"    trimmed to {start:.2f}-{end:.2f}s ({dur:.1f}s)")
    if dur > REF_MAX_S:
        cut += ["-t", str(REF_MAX_S)]
        if not quiet:
            print(f"    reference is {dur:.1f}s — trimming to {REF_MAX_S:.0f}s. "
                  f"Ensure ref_text covers only that part.")

    chain = [REF_DENOISE] if denoise else []
    chain.append("silenceremove=start_periods=1:start_silence=0.1:"
                 "start_threshold=-45dB:stop_periods=-1:stop_silence=0.3:"
                 "stop_threshold=-45dB")

    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), *cut,
         "-af", ",".join(chain), "-ac", "1", "-ar", "24000", str(dest)])

    kept = duration_of(dest)
    if not quiet:
        tag = " · denoised" if denoise else ""
        print(f"    reference: {kept:.1f}s mono 24 kHz{tag}")
    # 4-5 s clean clips clone very well here (the best voice in the shipped cast
    # uses 3.98 s), so only genuinely tiny clips are worth warning about.
    if kept < 3:
        print("    warning: very short reference — clone quality will suffer.")
    return kept


async def edge_reference(text: str, voice: str, dest: Path,
                         pitch: str = "+0Hz", rate: str = "+0%") -> None:
    """Render a reference clip with a free Edge neural voice.

    Pitch/rate shifting here is how you get more characters than you have source
    voices: the clone inherits whatever timbre the reference has, so a shifted
    reference yields a new but internally consistent voice.

    **Keep any shift small — well inside +/-20 Hz — and verify the result.**
    Edge's `pitch` is not an offset on the measured median, and the error runs
    the wrong way: `-40Hz` on `ta-IN-PallaviNeural` moved her median from
    262.3 Hz to 181.8 Hz, an **80 Hz** drop that a listener immediately called
    unnatural. Always re-measure with `median_f0` after setting `pitch`; do not
    assume the number you asked for is the number you got.

    Prefer a different source voice over a large shift. `engine="edge"` avoids
    the question entirely by shipping the voice as-is.
    """
    import edge_tts

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_mp3 = dest.with_suffix(".src.mp3")
    await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(str(tmp_mp3))
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp_mp3),
         "-ac", "1", "-ar", "24000", str(dest)])
    tmp_mp3.unlink(missing_ok=True)


async def edge_speak(text: str, voice: str, dest: Path,
                     pitch: str = "+0Hz", rate: str = "+0%",
                     raw: bool = False) -> None:
    """Speak `text` directly with an Edge voice — no cloning in the path.

    This is the `engine="edge"` route, and for Tamil it is the better one.
    Cloning a native `ta-IN` Edge voice through OmniVoice measurably degrades
    it: the raw voice carries 0-1 pitch spikes where its own clone carries 2-3,
    and a listener comparing them picked the raw voice unprompted.

    It is also ~50x faster — no 2.5 GB model, no 15 s load, no 45-60 s per
    clip — and needs no reference audio or transcript.

    The trade is that you get the voices Microsoft ships and nothing else. Use
    `engine="clone"` when the voice has to be a *specific* person.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".edge.wav")
    await edge_reference(text, voice, tmp, pitch=pitch, rate=rate)
    if raw:
        tmp.replace(dest)
        return
    master(tmp, dest)
    tmp.unlink(missing_ok=True)


# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------

def load_model():
    """Load OmniVoice once and reuse it.

    Use mlx-audio's own loader — its post_load_hook wires up both the text
    tokenizer and the HiggsAudio codec tokenizer. Hand-rolling this fails: the
    module README references a `{path}/tokenizer` subdir that does not exist
    (text tokenizer is at the repo root, audio tokenizer under audio_tokenizer/).

    The `mlx_audio.tts.generate` CLI reloads the model on every invocation,
    ~15 s of pure overhead per clip. Always loop inside one process instead.
    """
    from mlx_audio.tts.utils import load_model as _load
    return _load(model_path=MODEL_ID)


def synth(model, text: str, lang: str, ref_audio: Path | None, ref_text: str,
          dest: Path, instruct: str = "None") -> float:
    """Synthesize one chunk, cloning `ref_audio` when given.

    duration_s MUST stay None. Passing a number forces a fixed canvas the model
    stretches or pads to fill, producing fragmented audio with dead gaps. The
    built-in RuleDurationEstimator derives length from the text correctly.
    (Measured: a hardcoded 13.0 s produced eight clips all exactly 13.000 s,
    each riddled with silence. duration_s=None gave 9.0-9.1 s and zero gaps.)

    `ref_audio=None` selects the model's own "smart voice" instead of cloning.
    It gives up identity control but keeps the model's native prosody, which is
    noticeably more natural in Tamil than a clone.

    `instruct` is a free-text style direction the model conditions on
    (`<|instruct_start|>…<|instruct_end|>`). "None" is the model's own default
    and means unconditioned — it is a literal sentinel string, not a null.

    **Measured: instruct makes Tamil worse, and without a reference it collapses
    entirely.** Round-trip intelligibility on the same Tamil line: clone 86.7%,
    clone+instruct 85.6%, no-ref 88.2%, no-ref+instruct **0.0%** — the model
    degenerated into "நான் நான் நான்…" at 400 Hz. This checkpoint does not
    appear to be instruction-tuned. Steer style with the reference clip and the
    wording of the text instead.
    """
    import numpy as np
    from mlx_audio.audio_io import write as audio_write

    if instruct != "None":
        print("  warning: instruct measurably degrades this checkpoint "
              "(0% intelligibility with no reference) — see core.synth docstring",
              file=sys.stderr)

    kwargs = dict(
        text=text, language=lang, duration_s=None, instruct=instruct,
        tokenizer=model.audio_tokenizer,
        text_tokenizer=model.text_tokenizer)
    if ref_audio is not None:
        kwargs.update(ref_audio=str(ref_audio), ref_text=ref_text)

    result = next(model.generate(**kwargs))

    dest.parent.mkdir(parents=True, exist_ok=True)
    audio = np.array(result.audio)
    audio_write(str(dest), audio, result.sample_rate)
    return len(audio) / result.sample_rate


def master(src: Path, dest: Path, extra_denoise: bool = False) -> None:
    chain = f"{OUTPUT_DENOISE},{MASTER_CHAIN}" if extra_denoise else MASTER_CHAIN
    dest.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
         "-af", chain, "-ar", "44100", "-b:a", "192k", str(dest)])


# --------------------------------------------------------------------------
# measurement
# --------------------------------------------------------------------------

def _pcm(path: Path, sr: int = 16000):
    import numpy as np
    tmp = OUT / "_measure.wav"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(path),
         "-ac", "1", "-ar", str(sr), str(tmp)])
    with wave.open(str(tmp)) as w:
        data = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(float)
    tmp.unlink(missing_ok=True)
    return data


def median_f0(path: Path, lo: int = 70, hi: int = 400) -> dict:
    """Median fundamental frequency by autocorrelation over voiced frames.

    Used to check a clone actually inherited the source timbre, and that
    same-gender characters are far enough apart to be distinguishable.
    """
    import numpy as np

    sr = 16000
    sig = _pcm(path, sr)
    frame, hop = int(0.04 * sr), int(0.02 * sr)
    lo_lag, hi_lag = sr // hi, sr // lo
    vals = []

    for i in range(0, max(0, len(sig) - frame), hop):
        seg = sig[i:i + frame]
        if np.sqrt(np.mean(seg ** 2)) < 300:        # skip silence
            continue
        seg = seg - seg.mean()
        ac = np.correlate(seg, seg, "full")[frame - 1:]
        if ac[0] <= 0:
            continue
        ac /= ac[0]
        window = ac[lo_lag:hi_lag]
        if not len(window):
            continue
        lag = int(np.argmax(window)) + lo_lag
        if ac[lag] > 0.3:                            # voiced only
            vals.append(sr / lag)

    if not vals:
        return {"n": 0, "median": 0.0, "p10": 0.0, "p90": 0.0}
    a = np.array(vals)
    return {"n": len(a), "median": round(float(np.median(a)), 1),
            "p10": round(float(np.percentile(a, 10)), 1),
            "p90": round(float(np.percentile(a, 90)), 1)}


def pitch_range_st(f0: dict) -> float:
    """Expressiveness: the p10-p90 pitch spread, in semitones.

    Flat, mechanical narration keeps a narrow spread; natural speech swings.
    Semitones rather than Hz so male and female voices are comparable — 4 st is
    4 st whether the speaker sits at 110 Hz or 250 Hz.

    Measured on real references: ~5-8 st is lively natural speech, ~3-4 st is
    acceptable, below ~2.5 st reads as monotone.
    """
    import math
    lo, hi = f0.get("p10", 0.0), f0.get("p90", 0.0)
    if lo <= 0 or hi <= 0:
        return 0.0
    return round(12 * math.log2(hi / lo), 2)


# Vocalisations the model emits as sounds rather than reading aloud. Anything
# outside this set is spoken literally, so "[pause]" becomes the word "pause".
#
# This list mirrors OmniVoice's own regex exactly
# (omnivoice.py:15-17, `_NONVERBAL_PATTERN`). Its tokenizer keeps a matching tag
# as one atomic token; unmatched bracket text falls through to ordinary text
# tokenization, which is why the failure is silent rather than an error.
NONVERBAL_TAGS = (
    "laughter", "sigh", "confirmation-en",
    "question-en", "question-ah", "question-oh", "question-ei", "question-yi",
    "surprise-ah", "surprise-oh", "surprise-wa", "surprise-yo",
    "dissatisfaction-hnn",
)

_BRACKET_RE = re.compile(r"\[([^\[\]]*)\]")


def unknown_nonverbal(text: str) -> list[str]:
    """Bracketed tags in `text` that the model will read out as words.

    Returns the offending tags in the order they appear, deduplicated. An empty
    list means every bracket in the text is a real vocalisation.

    Matching is **exact** — case-sensitive and whitespace-free — because
    OmniVoice's own pattern is (`omnivoice.py:14`, no `re.IGNORECASE`). So
    "[Sigh]" and "[ sigh ]" are reported, since the model would speak them
    rather than perform them. Being more lenient here would hide precisely the
    failure this function exists to catch.

    Callers should warn rather than fail: square brackets are legitimate prose
    in some scripts, and the operator may genuinely want them spoken.
    """
    seen, bad = set(), []
    for m in _BRACKET_RE.finditer(text):
        tag = m.group(1)
        if tag in NONVERBAL_TAGS or tag in seen:
            continue
        seen.add(tag)
        bad.append(m.group(0))
    return bad


def nonverbal_hint(tag: str) -> str:
    """Why `tag` was rejected, when it is nearly a real one.

    Case and stray spaces are the likely operator slips; everything else is
    simply not a tag this checkpoint knows.
    """
    inner = tag.strip("[]")
    if inner.strip().lower() in NONVERBAL_TAGS and inner not in NONVERBAL_TAGS:
        return f"did you mean [{inner.strip().lower()}]? tags are case-sensitive"
    return ""


# --- timbre fingerprinting -------------------------------------------------
# Mean+std MFCCs: roughly "what shape is this person's vocal tract". Used both
# to prove two characters are different people (timbre.py) and to pick the
# candidate that best matches its reference (build_cast.py).

_PROFILE_SR = 24000
_N_FFT = 1024
_HOP = 256
_N_MFCC = 20
_N_MEL = 40
# Voiced speech energy lives well inside this band; wider just adds hiss and
# MP3 cutoff artefacts to the comparison.
_FMIN, _FMAX = 50, 8000
# Frames below 5% of peak are pauses. Averaging them in makes every voice look
# alike, because silence has no timbre.
_SILENCE_REL = 0.05


def _mel_filterbank():
    import numpy as np
    to_mel = lambda f: 2595.0 * np.log10(1.0 + f / 700.0)      # noqa: E731
    to_hz = lambda m: 700.0 * (10.0 ** (m / 2595.0) - 1.0)     # noqa: E731
    points = to_hz(np.linspace(to_mel(_FMIN), to_mel(_FMAX), _N_MEL + 2))
    bins = np.floor((_N_FFT + 1) * points / _PROFILE_SR).astype(int)
    fb = np.zeros((_N_MEL, _N_FFT // 2 + 1))
    for i in range(_N_MEL):
        lo, mid, hi = bins[i], bins[i + 1], bins[i + 2]
        if mid > lo:
            fb[i, lo:mid] = (np.arange(lo, mid) - lo) / (mid - lo)
        if hi > mid:
            fb[i, mid:hi] = (hi - np.arange(mid, hi)) / (hi - mid)
    return fb


def voice_profile(path: Path):
    """Timbre fingerprint of a clip, comparable with `profile_similarity`."""
    import numpy as np
    from scipy.fftpack import dct

    raw = subprocess.run(
        ["ffmpeg", "-v", "quiet", "-i", str(path),
         "-f", "f32le", "-ac", "1", "-ar", str(_PROFILE_SR), "-"],
        capture_output=True, check=True).stdout
    y = np.frombuffer(raw, dtype=np.float32)
    if y.size < _N_FFT * 4:
        raise ValueError(f"{Path(path).name}: too short to profile")

    frames = np.lib.stride_tricks.sliding_window_view(y, _N_FFT)[::_HOP]
    rms = np.sqrt((frames ** 2).mean(1) + 1e-12)
    frames = frames[rms > rms.max() * _SILENCE_REL]
    spec = np.abs(np.fft.rfft(frames * np.hanning(_N_FFT), axis=1)) ** 2
    log_mel = np.log(spec @ _mel_filterbank().T + 1e-10)
    m = dct(log_mel, type=2, axis=1, norm="ortho")[:, :_N_MFCC]
    # Drop c0: it is loudness, which mastering normalises away anyway.
    return np.concatenate([m.mean(0)[1:], m.std(0)[1:]])


def profile_similarity(a, b) -> float:
    """Cosine similarity of two voice profiles. 1.0 = identical timbre."""
    import numpy as np
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


def f0_track(path: Path, lo: int = 70, hi: int = 400) -> list[tuple[float, float]]:
    """Per-frame `(time_s, f0_hz)` for voiced frames only.

    `median_f0` collapses this to a single number, which hides *when* the pitch
    moved. Spike detection needs the timeline: a voice that jumps an octave for
    one phoneme and comes straight back has a perfectly normal median.

    Same 40 ms / 20 ms framing and voicing test as `median_f0`, but with
    **octave folding**, which matters here and does not there. Plain
    autocorrelation regularly latches onto the half-lag peak and reports 2x the
    true pitch for a frame or two. A median absorbs that; a spike detector
    reports it as a defect. Measured on the shipped cast, the naive version
    flagged all nine voices, and the excursions sat at 320-400 Hz against a
    158 Hz median — an exact octave, and mostly one frame long.

    The frame pitch is folded toward the clip's own median until it is within
    `_OCTAVE_FOLD_ST` semitones of it. That threshold sits **above** the range
    of real artefacts (6-9 st) and **below** a true octave error (12 st), so
    genuine spikes survive folding and tracker glitches do not.

    Known limitation: a real artefact that lands within a semitone or two of an
    exact octave is folded away with the glitches. That is the deliberate
    trade — this feeds a screening tool, and a detector that flagged all nine
    clean voices would simply be ignored.

    Do not "improve" this by preferring the longest strong lag. For a periodic
    signal the autocorrelation at twice the true period is also strong, so that
    rule systematically reports *half* the pitch; it was tried, and it put
    Meera's local baseline at 119 Hz against a 238.8 Hz median.
    """
    import numpy as np

    sr = 16000
    sig = _pcm(path, sr)
    frame, hop = int(0.04 * sr), int(0.02 * sr)
    lo_lag, hi_lag = sr // hi, sr // lo
    raw: list[tuple[float, float]] = []

    for i in range(0, max(0, len(sig) - frame), hop):
        seg = sig[i:i + frame]
        if np.sqrt(np.mean(seg ** 2)) < 300:        # silence
            continue
        seg = seg - seg.mean()
        ac = np.correlate(seg, seg, "full")[frame - 1:]
        if ac[0] <= 0:
            continue
        ac /= ac[0]
        window = ac[lo_lag:hi_lag]
        if not len(window):
            continue
        lag = int(np.argmax(window)) + lo_lag
        if ac[lag] > 0.3:                            # voiced only
            raw.append((i / sr, sr / lag))

    if not raw:
        return []
    centre = float(np.median([f for _, f in raw]))
    if centre <= 0:
        return raw

    hi_r = 2.0 ** (_OCTAVE_FOLD_ST / 12.0)
    out = []
    for t, f in raw:
        for _ in range(3):                           # bounded, never spins
            if f > centre * hi_r:
                f /= 2.0
            elif f < centre / hi_r:
                f *= 2.0
            else:
                break
        out.append((t, f))
    return out


def median_filter(track: list[tuple[float, float]],
                  width: int = 5) -> list[tuple[float, float]]:
    """Smooth isolated frame errors out of an F0 track, keeping the timing.

    Octave correction removes most tracker glitches but not all. A short median
    filter kills whatever survives as a one- or two-frame outlier while leaving
    any excursion long enough to actually hear completely intact.
    """
    import numpy as np
    if len(track) < width:
        return track
    freqs = np.array([f for _, f in track])
    half = width // 2
    sm = np.array([
        float(np.median(freqs[max(0, i - half):i + half + 1]))
        for i in range(len(freqs))
    ])
    return [(t, float(s)) for (t, _), s in zip(track, sm)]


def silences(path: Path, thresh_db: int = -45,
             min_s: float = 0.12) -> list[tuple[float, float]]:
    """Silent spans as `(start_s, duration_s)`.

    `count_gaps` only counts holes at 0.5 s and above, which is the threshold for
    *degenerate* audio. Pause-rhythm analysis needs the ordinary ones too, so
    this defaults to 0.12 s — short enough to catch the breaths that make speech
    sound human, long enough to ignore stop consonants.
    """
    proc = subprocess.run(
        ["ffmpeg", "-i", str(path),
         "-af", f"silencedetect=n={thresh_db}dB:d={min_s}", "-f", "null", "/dev/null"],
        capture_output=True, text=True)
    spans, start = [], None
    for line in proc.stderr.splitlines():
        if "silence_start:" in line:
            try:
                start = float(line.split("silence_start:")[1].split()[0])
            except (IndexError, ValueError):
                start = None
        elif "silence_duration:" in line and start is not None:
            try:
                spans.append((start, float(line.split("silence_duration:")[1].split()[0])))
            except (IndexError, ValueError):
                pass
            start = None
    return spans


def noise_floor(path: Path) -> float:
    """Noise floor in dB. -inf (returned as -99.0) means perfectly clean."""
    proc = subprocess.run(
        ["ffmpeg", "-i", str(path), "-af", "astats=metadata=1:reset=0",
         "-f", "null", "/dev/null"],
        capture_output=True, text=True)
    for line in proc.stderr.splitlines():
        if "Noise floor dB" in line:
            val = line.split()[-1]
            return -99.0 if val.startswith("-inf") else round(float(val), 1)
    return 0.0


def count_gaps(path: Path, thresh_db: int = -45, min_s: float = 0.5) -> int:
    """Silent gaps inside the clip. Anything above zero means degenerate audio."""
    proc = subprocess.run(
        ["ffmpeg", "-i", str(path),
         "-af", f"silencedetect=n={thresh_db}dB:d={min_s}", "-f", "null", "/dev/null"],
        capture_output=True, text=True)
    return proc.stderr.count("silence_start")


def measure(path: Path) -> dict:
    f0 = median_f0(path)
    return {
        "dur": round(duration_of(path), 2),
        "f0": f0["median"],
        "f0_range": [f0["p10"], f0["p90"]],
        "noise_floor": noise_floor(path),
        "gaps": count_gaps(path),
    }


def check(entry: dict, gender: str) -> list[str]:
    """Return a list of acceptance-criteria failures for one measured voice."""
    problems = []
    lo, hi = F0_RANGE[gender]
    if entry["gaps"] > 0:
        problems.append(f"{entry['gaps']} silent gap(s) — check duration_s is None")
    if entry["noise_floor"] > -45:
        problems.append(f"noise floor {entry['noise_floor']} dB — denoise the reference")
    if not (lo <= entry["f0"] <= hi):
        problems.append(f"F0 {entry['f0']} Hz outside {gender} range {lo}-{hi} Hz")
    if entry["dur"] < 1.0:
        problems.append(f"only {entry['dur']}s — generation likely truncated")
    return problems


def load_manifest() -> dict:
    path = CAST / "manifest.json"
    if not path.exists():
        sys.exit("No cast yet — run: .venv/bin/python scripts/build_cast.py "
                 "--characters templates/characters.json")
    return json.loads(path.read_text(encoding="utf-8"))
