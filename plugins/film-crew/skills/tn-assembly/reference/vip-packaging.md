# VIP packaging

When a recognisable public figure appears in a session, that fact outranks the
topic for packaging purposes. A face people know outperforms an issue headline
in a feed, and the audience searching for that person is much larger than the
audience searching for the debate.

This is a **packaging** rule, not a content rule. It changes the title,
thumbnail and Short hook. It must never change what the footage shows or what
the video claims happened.

## Configuration

Nobody is named in code. Set it in `project.json`:

```json
"vip": {
  "enabled": true,
  "name": "Name In English",
  "name_local": "பெயர்",
  "honorific": "CM",
  "ref_images": ["meta/refs/person.png"],
  "match_threshold": 0.45,
  "review_threshold": 0.38,
  "step": 3.0,
  "min_face": 42
}
```

Reference images must be clear, front-facing, and reasonably recent. One good
photo beats five poor ones.

## Detection

```bash
python3 ingest.py <project> --stage scan  # small scan copy, not the full session
python3 faces.py <project> --probe      # calibrate against the reference
python3 faces.py <project> --scan       # sweep, writes meta/vip_hits.json
```

Uses `insightface buffalo_l` with onnxruntime on CPU.

### Two performance notes that matter

`FaceAnalysis.get()` runs ArcFace recognition on **every** detected face. A wide
chamber shot contains 20–31 tiny faces, so a naive scan ran below **1.3 fps** —
hours of compute for one session. Splitting the detector from the recogniser and
filtering to faces at least 42 px wide *before* recognition took it to
**4.1 fps**.

The 42 px floor is not arbitrary: below it ArcFace has too little detail for its
similarity scores to mean anything, so those crops were producing noise that had
to be discarded anyway.

Sampling every 3 seconds loses nothing — a speaker holds the floor far longer
than that.

### Calibrating the threshold

Measured similarity on this stack:

- Same person: **≳ 0.50**
- Different people: **≲ 0.30**

The default `match_threshold` of 0.45 is deliberately conservative. Anything
between `review_threshold` and `match_threshold` should be looked at by a human
rather than trusted. **Always run `--probe` first** and confirm the reference
scores highly against a known frame of the same person; a bad reference image
produces confident nonsense.

## How it changes the plan

`plan.py` marks a segment `vip: true` when a hit falls within 20 seconds of it —
generous, because the detector samples every few seconds and a face seen just
outside the window is almost certainly in the segment. An episode containing any
such clip is marked `vip: true`.

For a VIP episode:

- **Title** leads with the person's name, in both languages.
- **Thumbnail** uses a frame in which they are clearly visible and identifiable.
- **Shorts** from that episode hook on them.
- Tags include the name, its transliterations and common misspellings.

## The rules

1. **Only if they are actually there.** Putting a face on a thumbnail when they
   do not appear is a lie, and it is the kind that loses a channel its
   standing.
2. **Only if the segment is about them.** A three-frame glimpse in a wide shot
   is not a VIP segment. Require a sustained, identifiable presence.
3. **Do not invent quotes or positions.** Their presence justifies the framing;
   it does not license claims about what they said.
4. **Verify borderline matches by eye** before publishing.
5. **A VIP flag never promotes a weak segment.** Packaging changes; editorial
   selection does not.
