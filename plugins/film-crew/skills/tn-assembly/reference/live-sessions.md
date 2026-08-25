# Live sessions

A live sitting and a finished recording are the same footage and a completely
different job. Deciding which one you have is the first thing that happens,
before ingest, because everything downstream depends on the answer and both
mistakes are expensive: treat a live stream as a recording and the session
ends before anything is published; treat a recording as live and the loop
waits forever for a stream that already finished.

## The decision

```bash
python3 scripts/source_state.py <project>            # uses source.url
python3 scripts/source_state.py <project> --url URL  # or an explicit one
```

It writes `meta/source_state.json` and reports one of four states.

| State | Meaning | What follows |
|---|---|---|
| `live` | Still broadcasting | `live.py` — publish as it runs, keep following |
| `recorded` | Finished | `pipeline.py` — one pass, no tracking |
| `upcoming` | Scheduled, not started | Nothing to cut yet |
| `none` | No URL, and the channel has no live stream | Say "no live session yet" |

**With no URL**, `source.url` is empty, so the configured channel
(`channel.url` or `channel.handle`) is checked for a live broadcast. If there
is none, `none` is the honest answer — reporting "no live session yet" is more
useful than inventing work.

`post_live` is classified as **live**. The broadcast has stopped but YouTube is
still assembling the recording, so its duration is still moving; cutting
against a length that is still changing produces clips that do not match the
final video.

## Following a live session

```bash
python3 scripts/live.py <project> \
    --interval 900 \
    --edge-margin 300 \
    --marketing ./scripts/publish_one.py
```

`--marketing` is **an adapter you write**, called as
`<script> <project> --only <id>`, which packages and uploads that single item
and exits non-zero if it did not. `head-of-marketing` has no such script —
its stages operate per project, not per item — so this is the one piece a
live run needs supplied.

Each cycle: probe → fetch the finished part → analyse → plan → publish what is
new.

Several decisions in that loop are worth knowing about, because each one is a
cost accepted deliberately or a failure already paid for.

**Analysis re-runs over the whole session, not the new tail.** Highlight scores
are relative to the session, so a window scored against the first twenty
minutes is scored against the wrong baseline. A quiet morning would promote
material that a busy afternoon later shows to be unremarkable, and those clips
are already published by then.

**Nothing is cut near the live edge.** `--edge-margin` holds publishing a few
minutes behind the front, because the recording is still being assembled there
and a clip taken at the boundary can land on footage that shifts underneath
it. A truncated clip cannot be quietly fixed once it is public.

**The edge comes from the media on disk, not from the reported duration.** A
running broadcast reports no duration at all — yt-dlp prints `NA`, because
YouTube does not publish a length until the stream ends. Treating that as zero
makes the safe edge negative and *nothing ever becomes ready*: the loop runs
all day reporting healthy cycles and publishing nothing. `local_end()` probes
the downloaded audio instead, with the reported length only as a fallback, and
the cycle refuses to publish rather than guess when neither is available.

**Published work is tracked by span, not by plan id.** `plan.py` numbers items
by rank, and re-planning each cycle renumbers them: one new clash discovered
late shifts every lower-ranked id by one. Keying on ids would then skip the
newcomer that inherited a published id *and* re-upload the item that shifted
into a fresh one — both failures at once, one of them a duplicate public
video. `meta/live_progress.json` records the start and end of everything
touched, and a re-planned item overlapping a recorded span is recognised as
the same moment under whatever id it now carries.

**Progress is written before the upload, not after.** The one outcome this
loop must never produce is a public video it believes is unpublished, because
every later cycle would publish it again. Items move through
`rendered → uploading → published`, and an id left at `uploading` is reported
and skipped rather than blindly retried — it means a run died mid-upload and
the channel needs checking by hand.

**A retry clears its own artifacts first.** `cut.py`, `build.py` and
`shorts.py` all refuse to overwrite an existing file without a hash-bound
approval. That is right for a human re-run and fatal here: a publish that died
after cutting would hit the refusal on every subsequent cycle and could never
complete. The loop owns those files and deletes them before retrying.

**A failed stage publishes nothing.** Ingest, analysis and planning failures
used to be discarded, so a cycle whose analysis died would publish against
whatever `plan.json` was left on disk — stale candidates measured against a
newer live edge.

**One tracker per session.** `meta/live.lock` prevents a second run; two would
publish the same moments twice.

When the stream ends the loop makes one final pass with the margin removed —
the tail is only reachable once the recording has stopped moving — and exits.

## Live downloads need pinning down

A live source needs `--live-from-start`, which is *not* yt-dlp's default. Two
things break without it. The download begins at the current moment and stays
attached until the broadcast ends, so the first cycle never returns during a
sitting. And the file it eventually writes starts at t=0 where the *download*
began rather than where the *session* began, while every cut seeks in
session-absolute time — so each clip silently lands at the wrong offset by
however long the session had been running.

`ingest.py --until <seconds>` bounds the fetch so the call terminates instead
of following the stream forever.

## Finding the stream when no URL is given

`source.channel_url` is the **broadcaster's** channel, not the upload
destination. They are different channels, and pointing the search at the
upload channel finds our own re-uploads of previous sittings.

A discovered URL is pinned into `project.json` as `source.url` before any
stage runs, because each stage is a separate process that reads it from the
file — a URL resolved only in memory is invisible to all of them.

## Time to first video

**Target: a video live within 15 minutes of starting.** This is the number that
decides whether a live run was worth doing, and it is the one that regressed
without anyone noticing, because a run that is busy looks like a run that is
working.

A full sitting was tracked end to end and the first video went live **2 hours
33 minutes** after the recorders started. Measured from that run's logs:

| Window | Elapsed | What was happening |
|---|---|---|
| 06:24 → 06:37 | 13 min | recorders started, first pass not yet run |
| 06:37 → 06:37 | 15 s | snapshot and analysis of 99 minutes of session |
| 06:37 → 07:16 | **39 min** | transcribing every window "to confirm what is said" |
| 07:16 → 07:27 | 11 min | cutting, building 1 episode, rendering 8 Shorts |
| 07:27 → 08:51 | **84 min** | everything rendered and packaged — no uploader running |
| 08:51 → 08:57 | 6 min | upload |

Analysis took **fifteen seconds**. The two blocks that cost two hours were both
avoidable, and neither was cutting or rendering:

1. **Confirmation ran before publishing instead of after.** Transcribing all 24
   windows to pick titles blocked every video for 39 minutes. Titles can be
   improved in place after publishing; a video cannot be un-missed.
2. **Nothing was uploading.** The worker exits when its queue drains, which
   happens constantly between passes, and for 84 minutes finished videos sat
   on disk. Whatever runs the uploader must restart it, not assume it lives.

The rules that follow:

- **Nothing that only improves a video may block the first one.** Transcription,
  quote mining and title polish run *after* the first publish, and their output
  is applied to the live video afterwards.
- **The opening cycle publishes a Short, not an episode.** `live.py` reorders
  for this automatically. A Short renders in about 30 seconds against nearly
  five minutes for an episode, and on a cold channel it is also the only format
  that gets seen (`reference/distribution.md`). The first Short's link to its
  long-form is backfilled once the episode exists.
- **Check the uploader is alive every cycle**, and restart it if not.
- **Measure it.** `live.py` prints time-to-first-video and flags it when it goes
  over target, so a regression shows up in the log rather than the next morning.

A realistic budget for the opening cycle: snapshot and analyse ~1 min, plan and
cut one Short ~1 min, one quote transcription ~3 min, render ~30 s, thumbnail
and package ~1 min, upload ~2 min. That is inside 10 minutes, and the recorders
need roughly 5 minutes of head start before there is anything worth cutting.

## Speed is the point

Without `--marketing`, items are built and left unpublished, which for a live
run defeats the exercise. The audience for a sitting arrives while it is still
sitting. A clip that would have found viewers at 11am finds very few at 7pm,
and by the following morning it is competing with every news channel that
managed to publish the same day.

That is also why search matters more here than on a normal upload. A live
session generates searches for names and phrases that did not exist an hour
earlier, and the video that is already indexed when those searches start is
the one that collects them. Package with the specific name, the specific
claim, and the words the person actually used — not a generic session title.
`reference/packaging.md` covers the handoff; the rule of thumb is that a title
a viewer could have typed into the search box beats a title that merely
describes the footage.

## Pitfalls this loop was built around

These are all things that went wrong in production, not hypotheticals.

- **A stale title card.** The build picked up an old style because the newer
  one had not been made the default. Confirm the rendered output, not the
  configuration.
- **Thumbnail text over the subject's face.** Text must sit above or below the
  face, never across it. Enforced in `head-of-marketing`'s renderer; see
  `reference/packaging.md`.
- **A Short cut into parts.** One Short is one self-contained highlight
  linking back to the long-form. "Part 1 / Part 2" splits ask a viewer in a
  scrolling feed to go and find the rest, and they do not.
- **Blurred mirrored backgrounds.** The footage should fill the vertical
  frame. See `reference/shorts.md`.
- **A Short thumbnail in a different style from its episode.** They are the
  same story and should look like it.
- **A generic title.** Use what the person actually said, and prefer the
  moment where they said it with force. A title in someone's own words
  outperforms a description of the same moment.
- **Publishing someone who never spoke.** Being on camera is not the same as
  holding the floor; `reference/vip-packaging.md` explains the face-width test
  that separates the two.
