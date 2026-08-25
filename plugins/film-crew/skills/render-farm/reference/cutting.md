# Cutting

Assembling shots onto a timeline, and softening the joins between them. All of
this lives in `Film.jsx`, and all of it is invisible in Studio — the failures
here only appear in an encoded file, which is why they survive so long.

---

## A shot ends where the next one starts

The obvious way to place a shot is to give Remotion its start and its length:

```jsx
// WRONG -- and it renders, and it looks fine in Studio
const from = Math.round(entry.start * fps);
const durationInFrames = Math.round((entry.end - entry.start) * fps);
```

Those two roundings are independent, and they disagree whenever a cut lands
mid-frame. `start = 62.983` rounds to frame 1889; `end - start = 1.017` rounds
to 31 frames, so the shot ends at 1920 — but the next shot's own `start` rounds
to 1921. **Frame 1920 belongs to no shot, and renders as the composition's
background colour.**

On a fifty-one shot board that opened **eleven** holes, six of which were
against a dark backdrop and read as a black flash. Derive the length from the
neighbouring cut instead and there is only one clock, so there is nothing for a
second rounding to disagree with:

```jsx
const cuts = timeline.shots.map((s) => Math.round(s.start * fps));
const ends = cuts.slice(1).concat([Math.round(last.end * fps)]);
// ...
const durationInFrames = Math.max(1, ends[i] - from);
```

Two things make this worth its own section rather than a line in a changelog:

- **Every structural check passes.** The frame count is right, the duration is
  right, the container is right, `ffprobe` is happy. The film is one frame of
  black in the middle of a scene and nothing measures it.
- **It looks deliberate.** A single frame of black slammed into a cut is a
  real technique — see the impact frames in `animation-director` — so a viewer
  reads it as intent rather than as a bug, and a reviewer describes it as "a
  flash" rather than "a dropped frame". Believe the description, then go
  looking for the hole.

### Finding one

Scan every frame's luma and look for the ones with **no variance at all**.
A real picture, however dark, has structure; a hole is one flat colour.

```bash
ffmpeg -v error -i film.mp4 -vf "scale=32:18,format=gray" -f rawvideo - \
| python3 -c "
import sys, statistics as st
N = 32*18; i = 0
while True:
    b = sys.stdin.buffer.read(N)
    if len(b) < N: break
    if st.pstdev(b) < 0.5: print('uniform frame', i, 'mean', sum(b)/N)
    i += 1
"
```

Downscaling to 32×18 first is what makes this cheap enough to run on every
delivery — a three-minute film scans in about a minute. **Expect zero.** A
deliberate impact frame will also show up, so know how many you authored.

---

## Which cuts to soften, and which to leave alone

A dissolve is not a way to be gentle. It is the answer to one specific
problem: **a cut the eye cannot read as an edit.**

That happens when two consecutive shots are on the same set at nearly the same
magnification. Nothing in the frame re-anchors, so a slow push that was
drifting one way appears to snap backwards, and the audience reads a mistake
rather than a cut. Fading the incoming shot up over the outgoing one gives
them the anchor the picture failed to.

It is the wrong answer everywhere else. Cutting from a wide of a room to a
close-up of a prop on the floor is *already* legible — the new framing is the
anchor — and cross-fading two images at twice each other's magnification just
makes both of them muddy for a third of a second.

So the rule is a conjunction, and both halves matter:

```jsx
const soft = prev && prev.set === entry.set && ratio <= SOFT_RATIO;
```

| constant | value | why |
|---|---|---|
| `DISSOLVE` | **8 frames** | long enough to read as an edit, short enough not to read as a scene transition |
| `SOFT_RATIO` | **1.35** | past this the framing change carries the cut on its own |

On the board this was calibrated against: **32 cuts dissolved, 14 stayed
hard**, and the hard ones were exactly the ins and outs of the twelve prop
inserts. That split is the signal the rule is working. If nearly everything
dissolves, the board has no framing variety; if nearly nothing does, `set` is
probably not being set consistently.

### The incoming shot leads, and its clock does not

A dissolve has to happen *before* the cut, not after it, or the new shot has
already started moving by the time it is fully visible. So the sequence is
mounted `lead` frames early — and those lead frames are not part of the shot:

```jsx
const frame = Math.max(0, useCurrentFrame() - lead);          // Shot's clock
const opacity = lead > 0 ? Math.min(1, (raw + 1) / (lead + 1)) : 1;
```

Holding the clock at 0 through the lead matters for a traced style, where the
camera and prop tracks are arrays indexed by frame: without it the shot reads
index −8 and either throws or silently renders the wrong end of the track.

Clamp the lead so it cannot swallow a neighbour — `Math.min(DISSOLVE, cuts[i]
- cuts[i-1] - 2)` — or a run of very short shots overlaps three deep.

### Verify it in the encoded file

Pull frames either side of a cut you expect to be soft. The frame *before* the
cut should show both images; the frame a few after should be clean:

```bash
for f in 452 456 460 470; do
  ffmpeg -v error -y -i film.mp4 -vf "select=eq(n\,$f)" -vframes 1 /tmp/d$f.png
done
```

A dissolve that is present in Studio and absent in the file means the sequence
is being mounted at its own `from` rather than at `from - lead`.

---

## Zoom continuity across a cut

Softening the join fixes how a cut *looks*. It does not fix a camera that
teleports.

If a shot ends at zoom 1.48 and the next shot on the same set is authored to
open at 1.12, the dissolve now cross-fades between two genuinely different
framings, which is worse than the hard cut was. Let a same-set cut **open
where the last one closed**, clamped so it cannot wander far from what the
board asked for:

- open the incoming shot at the outgoing shot's final zoom
- clamp to **±12%** of the authored framing, so the board still decides the
  shot and continuity only removes the step
- keep a per-set "last zoom" and update it on *every* shot, including ones the
  tiering pass skipped — an untiered shot that does not write its zoom back
  leaves the next cut matching a framing two shots old

The insert is the case that proves the clamp is necessary. Framing a prop to
fill ~26% of frame height sends it to 2.9–3.2× against neighbours at 1.1–1.7,
and no amount of continuity can absorb a step that size. That is what the
`SOFT_RATIO` gate is for: the insert keeps its framing, and keeps its hard cut.

---

## What this does to a motion profile

Dissolves add measurable inter-frame difference at exactly the moments the
picture was previously most static, so `dynamic_range` improves — on the
calibration board it went **1.82 → 2.63**, which took it from failing to
passing.

It does not rescue `p90` or `longest_hold_s`. Those measure the shots
themselves, and a film of held drawings will still fail them. That is a
conversation about the board, not about the joins; see
[`animation-director`](../../animation-director/SKILL.md) for when failing
them is the right answer.
