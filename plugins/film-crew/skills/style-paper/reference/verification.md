# Verification

Never ship on the strength of watching it once. Each check below catches a
class of failure that is invisible in casual viewing.

---

## 1. Container and format

```bash
ffprobe -v error -show_entries format=duration -show_entries \
  stream=width,height,r_frame_rate,pix_fmt -of default=noprint_wrappers=1 out.mp4
```

Expect **1920×1080, 30 fps, `yuv420p`**. Anything else and the file will not
play everywhere — `yuv444p` in particular silently breaks on Safari and most
social platforms.

---

## 2. Loudness

```bash
ffmpeg -nostdin -i out.mp4 -af ebur128=peak=true -f null - 2>&1 | tail -12
```

Targets: **−14 LUFS integrated, true peak ≤ −1 dBFS.**

The render should already have got this right without being asked. Mastering
encodes the finished PCM with the codec that will actually deliver it, meters
the true peak that comes back, and widens the limiter's guard band until the
result is inside the target — so the figure it prints is measured, not assumed.
It has to work that way: the guard has to absorb the limiter's overshoot, AAC's
reconstruction *and* intersample peaks, and only the first of those is fixed.
The AAC term is programme-dependent, so any constant guard is one some film will
exceed. If the render printed a `!` line about a mix being too hot to limit
cleanly, believe it — the mix is the problem, not the master.

If loudness is off, **the mix is wrong — do not fix it by re-encoding.** Adjust
`mix.voice` / `mix.music` and render again. Normalising after the fact just
moves the imbalance around.

---

## 3. Clipping

`ebur128` reports true peak but not sample clipping, and a dense bed can stack
past 1.0 before mastering ever sees it:

```bash
ffmpeg -v error -i out.mp4 -f wav /tmp/chk.wav -y
python3 - <<'PY'
import wave, numpy as np
w = wave.open('/tmp/chk.wav'); n = w.getnframes()
a = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float64) / 32768
a = a.reshape(-1, w.getnchannels()).mean(axis=1)
print("clipped:", int((np.abs(a) >= 0.999).sum()), " peak:", round(float(np.abs(a).max()), 4))
PY
```

Expect **0 clipped samples**.

---

## 4. It actually moves

The most common failure of this style is a beautiful slideshow. Mean
frame-to-frame luma difference is a reliable proxy, and **the reference
measures ≈ 2.5**:

```bash
ffmpeg -v error -i out.mp4 -vf \
  "scale=320:180,format=gray,tblend=all_mode=difference,signalstats,\
metadata=print:key=lavfi.signalstats.YAVG:file=-" -an -f null /dev/null \
  | awk -F= '/YAVG/{s+=$2;n++} END{print s/n}'
```

Below **~1.5** the piece is a slideshow no matter how good the stills look. See
[`troubleshooting.md`](troubleshooting.md#it-reads-as-a-slideshow).

Note the metric is necessary but not sufficient: a single slow push across the
whole piece scores well and still feels frozen. The camera must *settle*
between beats, which is what `hold` is for.

### What actually moves this number

Measured on a 12-minute board film, changing nothing but the camera policy:

| Camera policy | Frames still | Score |
|---|---|---|
| Continuous unmotivated orbit | ~0 % | 1.83 |
| Hard cuts between framings, still in between | 84 % | 1.00 |
| **Eased pans, moving only when something arrives** | **64 %** | **1.77** |

The counter-intuitive row is the middle one. A **cut scores badly**: it changes
every pixel for exactly one frame out of thirty, and the mean is dominated by
the twenty-nine frozen ones. A **slow pan scores well**: the board is
high-frequency paper grain, so sliding it even a few pixels changes every pixel
in *every* frame of the move.

So the honest way to pass this check is also the one that looks best — move the
camera rarely, but when you move it, ease it. Reaching for cuts to feed the
metric makes the film jumpier *and* scores worse. Moving artwork barely
registers either; it only contributes in proportion to the element's share of
the frame.

---

## 5. The voice sits over the bed

Loudness says nothing about intelligibility. What matters is the **1–4 kHz**
band, where speech lives:

```bash
python3 - <<'PY'
import wave, numpy as np
def rd(p):
    w = wave.open(p)
    a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64) / 32768
    return a.reshape(-1, w.getnchannels()).mean(axis=1), w.getframerate()
x, sr = rd('/tmp/chk.wav')
def band(a, lo, hi):
    S = np.fft.rfft(a * np.hanning(len(a))); f = np.fft.rfftfreq(len(a), 1/sr)
    return 10*np.log10((np.abs(S[(f>=lo)&(f<hi)])**2).mean() + 1e-20)
speech = x[int(4.0*sr):int(7.5*sr)]      # a window you know is narrated
bed    = x[int(0.05*sr):int(0.80*sr)]    # a window you know is music-only
print(f"{band(speech,1000,4000) - band(bed,1000,4000):+.1f} dB @1-4k")
PY
```

Aim for **+20 dB at 1–4 kHz**, which is what the reference does. Broadband
ratio is a weaker signal — it is dominated by sub energy the ear does not use
for intelligibility.

⚠️ Pick the windows by hand and check them. A "music-only" window taken from
the lead-in is usually contaminated by the fade-in and by paper SFX, which will
make the bed look far brighter and louder than it is.

---

## 6. Reproducibility

Same storyboard, same bytes — golden rule 10. Cheapest check is to hash the bed
twice in one process:

```python
h = [hashlib.sha256(build_music(sb, 20.0, []).tobytes()).hexdigest() for _ in range(2)]
assert h[0] == h[1]
```

All five moods pass. `warm` and `tension` legitimately hash *the same as each
other* — `warm` has no branch of its own yet and falls through.

---

## Measuring honestly

Every wrong conclusion this suite has produced came from a measurement that
looked authoritative and was not. Five traps, all of which have bitten:

**Two `-i` inputs and two outputs.** `ffmpeg` maps input 0 to *both* outputs
unless you map explicitly, so "extract these two frames and diff them" silently
returns the same frame twice and a difference of zero. Extract each frame in
its **own command**.

**`scdet` / `scene_score` is a histogram score, not a difference.** It flags
motion *resuming after stillness* almost as strongly as a cut, so a film with
no cuts at all will still report a handful of hits. Use it only to find
candidate timestamps, then judge each one on a mean-absolute-frame-difference
profile of the surrounding second:

| Profile shape | Verdict |
|---|---|
| One frame high, neighbours near zero | a cut |
| A rise and fall over 10–20 frames | an eased pan |

Magnitude alone decides nothing: on grainy paper a perfectly comfortable pan
changes every pixel in every frame and scores 15–20.

**A spatial audit with no time filter is noise.** Comparing every element
against every other across a 12-minute film compared Act I artwork with Act III
captions and reported 198 "collisions" where **one** was real. Always require
that the two elements share screen time before you compare their boxes.

**Box checks cannot see the render.** They reason about resting positions and
declared extents — never parallax, `drift`, `sway`, or the true rendered width
of a string. Anything persistent, low-sitting, or near a tile edge has to be
confirmed by rendering a frame at the worst moment and *looking at the pixels*.
A destroyed credit line shipped because a clean checker report was trusted over
a screenshot.

**Never let an overlap check skip `static` elements.** They are baked into the
board before the draw list and lose every z-fight, so they are the elements
most likely to be silently destroyed — the exact opposite of safe to ignore.
A useful check compares paint order, not just boxes: art in front of a caption
is damage, art behind it is composition.

To prove a *continuous* motion like `sway` is working, isolate frames where the
camera is provably parked and diff those. If the mean never falls to zero,
nothing in the film is ever a frozen photograph.

## The motion mean is not the whole story

`motion_mean_min: 1.5` in `style.json` answers one question — *does it move?*
It cannot tell you whether the motion is *distributed*, and those are
different films.

Measured on a 37-beat test story, the undirected compile scored a mean of
1.749 and passed. Its loud beats averaged 1.802 and its quiet beats 1.785:
every beat moved by the same amount, so nothing in it was an accent. It also
produced 29 measured accents that no beat had asked for.

When a board was compiled from the same beat plan with a motion plan, the mean
*fell* to 1.282 — below this style's own floor — while the film became
dramatically better shaped, with loud beats at 1.742 against quiet beats at
1.118.

So: **treat `motion_mean_min` as a check on undirected boards only.** For a
board compiled with `--motion-plan`, judge it with
`animation-director/scripts/motionprofile.py`, which grades the distribution
instead. Failing the mean is the expected outcome of directing a film, not a
regression.

### Zoom crops captions

A push throws away the frame edge, and this style puts chips there. Measured:
a 1.32 zoom turned `KESTREL` into `ESTREL` and `NOT TO LOOK BACK` into `NOT TO
LOOK BAC` across a dozen shots. The undirected compiler never exceeds 1.10 and
is safe by accident, not by design.

`compile.py` now computes per-beat zoom headroom from the bounding box of
everything a beat owns, so a loose composition gets a hard push and a tight one
gets none. **A contact sheet is still the only proof.** A motion metric
improves right up to the moment the push starts eating words.

---

Always `--sheet` first. It costs ~17 s against 5–8 minutes for a 900-frame
render and catches every layout problem: collisions, elements outside the
camera path, chips wider than expected, backing sheets that do not cover the
travel.

```bash
python3 render.py sb.json --sheet
```
