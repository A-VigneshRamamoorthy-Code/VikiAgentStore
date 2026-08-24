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
  "distractor_images": ["meta/refs/chairA.jpg"],
  "match_threshold": 0.45,
  "review_threshold": 0.38,
  "step": 3.0,
  "min_face": 42
}
```

Reference images must be clear, front-facing, and reasonably recent. All of
them are averaged into one template, so several angles of the same person is
better than one — a single photo is brittle and can lose on an unusual head
angle. What does not help is padding the list with poor crops.

`distractor_images` is explained under [Who else is on
camera](#who-else-is-on-camera) and is worth setting before any long sweep.

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

### Who else is on camera

Those numbers describe the *typical* case, and they will eventually lie to you.
In one session the presiding officer scored **0.794** against the VIP template
— past every threshold above, and the wrong man. Nothing in the output looked
suspicious. It was caught by cropping the frame and looking at it, and it came
within one unchecked frame of publishing a video captioned with the wrong
politician's name.

The cause is structural rather than a bad threshold. With one template the only
question the scanner can answer is *how much does this face resemble him*. It
is never asked whether the face resembles somebody else more, so a recurring
non-subject has nowhere correct to land and piles up against the only template
on offer.

`distractor_images` supplies that competition. They are ordinary reference
photos of faces that appear often but are not the subject — the chair, an
anchor, whoever the camera keeps returning to — and the sweep suppresses any
hit a distractor wins. **They need no names.** Establishing "more like that man
than like the VIP" is enough to discard the hit, and an unnamed template makes
no claim that could be wrong.

Two practical points:

- **Cut them from the footage itself.** The people crowding your subject are
  usually the ones with no usable photo online. Three crops of the same face at
  well-separated timestamps work well; one does not — a single pose lost to the
  VIP's averaged template until two more were added.
- **Verify each crop by eye before enrolling it.** Grabbing the largest face at
  a timestamp is a guess about who was on screen. Two of five auto-extracted
  crops turned out to be different people, and a mislabelled distractor
  silently suppresses real hits.

`meta/vip_hits.json` then carries `alt` (the best distractor score) and
`margin` (`sim - alt`) beside `sim`. Margin is the honest signal: in the case
above genuine appearances separated at **+0.59 to +0.70** while the impostor
frames sat at **−0.70 to −0.80**, a far wider gap than the raw similarities
suggested. Crops are only written when the VIP wins, because a crop the VIP
lost is a picture of someone else and only invites the reviewer to confirm the
wrong face.

Omitting `distractor_images` keeps the old single-template behaviour, `alt` and
`margin` are simply absent.

### Similarity says who, size says whether they matter

A high score means the person is *on screen*, not that they are *speaking*. In
a 640×360 sweep the person at the microphone measures **82–89 px** across,
while someone seated in a wide shot measures **30–46 px**. That gap is a more
reliable test of who holds the floor than similarity is.

It has editorial consequences. One session put the opposition leader on camera
158 times, every one of them 30–46 px — seated on the front bench, never at the
microphone. A pipeline reading similarity alone would have built an episode
around a man who never said a word. The same measurement distinguishes a
speech from a reaction cutaway: the subject was found smiling at his desk at
82–86 px while a different member held the floor, which is a close-up, not a
speech, and not something to caption as one.

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
