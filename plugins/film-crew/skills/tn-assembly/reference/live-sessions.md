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

`--marketing` is a per-item adapter, called as
`<script> <project> --only <id>`, which packages and uploads that single item
and exits non-zero if it did not. **`scripts/publish_one.py` is that adapter
and it ships with this skill** — `head-of-marketing` has none, because its
stages operate per project rather than per item. This paragraph used to read
"an adapter you write", and that sentence alone cost two separate sittings
their opening hour: check `publish_one.py` before writing any upload glue.

Its first job each item is to copy `meta/channel.json` into the package, which
is what keeps Studio pinned to the right channel (rule 25). If the project has
no such file yet, it stops with the `upload.py switch` command needed to make
one rather than letting the upload fail at the dialog.

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

**Clearing artifacts means *every* path an item writes to.** The sweep above
originally walked `clips/`, `out/` and `out/shorts/` and matched on filename
prefix, which misses the four places the colliding files actually live:
`clips/shorts/<id>.mp4`, and the per-item *directories* `clips/<ep>/`,
`out/<ep>/` and `publish/<id>/`. A directory cannot be removed by a filename
sweep, so the refusal came back on every cycle for exactly the items the
function existed to rescue — six consecutive no-op cycles in one sitting, with
the loop reporting healthy cycles throughout. `publish/<id>/` is the same trap
seen from the other end: a half-built package keeps its title and thumbnail
missing, so the pre-flight gate refuses the item before packaging ever gets a
chance to fill them in.

**A failed publish must not burn the moment.** A packaging or upload failure
used to leave the item at `rendered`, and `rendered` is skipped for the rest
of the sitting — so one transient Studio error cost that moment permanently.
Because progress is matched by *overlap*, a burnt **episode** span is far
worse than a burnt Short: an episode covering 00:30–06:12 overlaps every
later episode, so a single failure silently ends long-form for the whole
session. Only an editorial hold is remembered now; anything else drops its
record and is retried next cycle.

**An editorial hold is a decision, not a fault, and it is matched by span.**
The adapter records a refusal in `meta/held.json`, which is the one failure
worth remembering — re-cutting the same unnameable minute every fifteen
minutes is pure waste. But `plan.py` reuses ids across re-plans, so the entry
has to carry the span it was written for; keyed on the id alone, a later
`sh06` covering completely different footage inherits the earlier verdict and
is never published.

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

### When the source refuses sections at all

Some live streams will not serve `--download-sections`. The manifest is live
DASH and yt-dlp declines to seek within it, so every per-clip fetch fails and
the cutting stage produces nothing — while `source_state.py` correctly says
`live` and the loop looks healthy. A whole sitting can be lost to this, and
rebuilding a recorder mid-broadcast costs more than the session is worth.

**Check this before the first cycle**, not after:

```bash
yt-dlp -f <fmt> --live-from-start --download-sections '*0-30' \
       -o /tmp/probe.%(ext)s <url> && echo "sections OK"
```

If it fails, switch to recording continuously and cutting locally:

1. Start a background `yt-dlp --live-from-start` recorder per stream (video
   and audio) writing to one growing file. Leave it running for the sitting.
2. Each pass, **snapshot** the growing file (copy it) and treat the snapshot
   as the source, so the cutter never reads a file being appended to.
3. Cut with `ffmpeg -ss` against the snapshot instead of re-fetching.

Two consequences worth planning for. The snapshot lags the recording, and the
recording can lag the broadcast when YouTube throttles fragment delivery — so
the last pass sees less material than exists, and passes must keep running
until one finds nothing new rather than stopping when the broadcast ends.
And a continuous recorder plus per-pass snapshots is the dominant consumer of
disk: budget roughly **6 GB/hour** and prune rendered video for permanently
held items when free space runs low.

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
3. **There was no uploader to run in the first place.** The skill documented
   `--marketing` as an adapter *you supply* while its own quick start invoked
   a `publish_one.py` that did not exist, so the opening minutes of a live
   sitting went into writing upload glue instead of publishing. A later run
   repeated this from scratch. `scripts/publish_one.py` now ships — check it
   before writing anything that drives Studio.

The rules that follow:

- **Nothing that only improves a video may block the first one.** Transcription,
  quote mining and title polish run *after* the first publish, and their output
  is applied to the live video afterwards.
- **The opening cycle publishes a Short, not an episode.** `live.py` reorders
  for this automatically. A Short renders in about 30 seconds against nearly
  five minutes for an episode, and on a cold channel it is also the only format
  that gets seen (`reference/distribution.md`). The first Short's link to its
  long-form is backfilled once the episode exists.
- **Check the uploader is alive every cycle**, and restart it if not — and
  check there is exactly one. A supervisor that restarts a dead uploader will
  happily run a second alongside a manually started one, and two uploaders
  claiming the same queue publish the same video twice.
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

- **An unpinned Studio.** The most expensive failure recorded so far: five
  hours of a live sitting captured, cut and rendered, and nothing published,
  because the package carried no `meta/channel.json`. The publisher's `login`
  had timed out before writing it while still leaving a working signed-in
  profile, so every check short of an actual upload looked healthy. The
  symptom is a generic YouTube **"Oops, something went wrong."** page
  screenshotted to `publish/<id>/meta/yt_0_no_dialog.png` and an
  `upload dialog did not open` error, neither of which names the cause. See
  rule 25.
- **A login that "worked" against the wrong account.** `upload.py login`
  waits for any tab showing `studio.youtube.com/channel/UC…` and records
  whatever it lands on without checking it is the intended channel; the
  account here also owns two decoys (`Politainment Re-defined`,
  `Politainment Gamer`). Always confirm with `channels` or `recon`
  afterwards. Chrome must not be holding the profile when either runs.
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
