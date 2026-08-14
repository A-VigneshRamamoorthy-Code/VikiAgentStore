# The demo video

The single most common reason a scope request bounces. Google's rejection wording
is generic, so it is easy to fix the wrong thing.

---

## What they actually ask for

The rejection email lists criteria. Read it literally — each is a separate pass/fail:

> **In-App Functionality:** Demonstrate the full operational functionality of every
> requested scope.
>
> **Source Account Impact:** For write or delete permissions, show the changes
> triggered in the app reflected in the user's Google account.
>
> **Consent Screen:** The OAuth consent flow and permission screen must be displayed
> with all requested scopes fully expanded and readable — if the scopes are obscured,
> click "Show all services."
>
> **Scope Matching:** The scopes requested by your app or manifest must exactly match
> the scopes configured and submitted for verification in the Google Cloud Console.

The phrase that trips people up is **"the maximum extent of the user facing features
using the scope(s)"**. A video that only shows sign-in succeeding will be rejected.
They want to see what you *do* with the data after the grant.

---

## The shot list

Aim for 2–5 minutes. Longer is not better; reviewers skim.

| # | Shot | Why it is there |
|---|------|-----------------|
| 1 | App with **no account connected** | Establishes the before state |
| 2 | The sign-in entry point being tapped | Shows the grant is user-initiated |
| 3 | Account chooser | Proves a real account, not a mock |
| 4 | **Consent screen, scopes readable** | Explicit criterion. Expand anything collapsed |
| 5 | The moment the scope is **ticked / granted** | The reviewer looks for this exact frame |
| 6 | App returns, showing **connected** state | The grant took effect |
| 7 | **The feature the scope exists for**, in use | The "maximum extent" criterion |
| 8 | More surfaces over that data | Breadth — search, lists, detail views |
| 9 | Disconnect / sign-out control | Shows revocability |
| 10 | Closing card: client ID, project ID, scopes | Makes "Scope Matching" trivially checkable |

Shot 10 is optional but disproportionately effective — it lets the reviewer confirm
scope matching without leaving the video.

**If you request a write or delete scope**, shot 8 must include the Google account
itself (Drive/Gmail in a browser) showing the change the app made. Read-only
integrations cannot show this; say so explicitly in your reply instead:

> The integration is strictly read-only — it never creates, renames, moves or deletes
> anything — so there is no write behaviour to reflect in the source account.

---

## Hard rules

- **The "unverified app" warning screen is expected.** Google says it "must be shown
  in the video". Do not try to hide it or record on an allow-listed account.
- **Do not deploy unverified scopes to production traffic** to record. Use a staging
  build, a hidden test route, or a separate project. Google warns this consumes your
  unverified user quota and disrupts users.
- **Host it where the reviewer can watch it.** Unlisted YouTube is accepted and normal.
  Verify it opens in a logged-out browser before sending — a private video reads as
  a non-response and costs you a full review cycle.
- **No copyrighted material.** If your app displays media, use CC-licensed content and
  put the attribution on screen. A card at the end is enough.
- **Language.** Record in English or provide English subtitles.

---

## Use a real account with real-looking data

An empty account demonstrates nothing. Populate a demo account with enough content
that the feature looks like it does for a user, and **use that same account for every
future submission** — it saves re-recording. Never record your personal account: the
video goes to a third party and often ends up publicly linked.

Screen recordings leak more than you think. Check every frame for:

- phone numbers during 2-step verification,
- notification banners,
- other accounts in the account chooser,
- your real name where you did not intend it.

---

## Recording and assembly gotchas

Hard-won, mostly platform-agnostic.

**Simulator/emulator recordings are variable-frame-rate.** `xcrun simctl io recordVideo`
writes a frame only when the screen changes. A fast input-side seek
(`ffmpeg -ss X -i src`) lands in a frame gap and decodes as **several seconds of
blank video**. Use an output-side seek, which decodes from zero and is frame accurate:

```bash
ffmpeg -i src.mp4 -ss 90 -t 12 -vf fps=30 clip.mp4     # correct
ffmpeg -ss 90 -i src.mp4 -t 12 clip.mp4                # may be blank
```

Because the whole file decodes each time, batch every clip into one invocation with
multiple outputs rather than one ffmpeg call per clip.

**A consequence:** any timestamp you read off a contact sheet built with fast seeks is
wrong. Build the contact sheet with accurate seeks or every clip boundary drifts.

**Trim, don't time-stretch.** Speeding footage to fill a narration slot looks like
fast-forward. Take `min(clip, narration)` and pad with `tpad=stop_mode=clone` — which
means each clip must *end* on a frame you are happy to freeze.

**`atempo` off a lossy source can silently under-speed.** Applying `atempo=2.0`
directly to an AAC stream can yield ~1.77×, leaving audio minutes out of sync with
video that halved correctly. Decode to PCM first, then speed:

```bash
ffmpeg -i in.mp4 -map 0:a -c:a pcm_s16le -ar 48000 a.wav
ffmpeg -i a.wav -af atempo=2.0 -c:a pcm_s16le a2x.wav
ffmpeg -i in.mp4 -i a2x.wav -filter_complex "[0:v]setpts=0.5*PTS[v]" \
       -map "[v]" -map 1:a -shortest out.mp4
```

**Always verify durations per stream afterwards** — `format=duration` can look right
while the audio stream is wrong:

```bash
ffprobe -v error -select_streams v -show_entries stream=duration,nb_frames -of default=nw=1 out.mp4
ffprobe -v error -select_streams a -show_entries stream=duration -of default=nw=1 out.mp4
ffmpeg -v error -i out.mp4 -map 0:a -f null - -stats 2>&1 | tail -1   # true decoded length
```

**Many ffmpeg builds lack `drawtext`** (no libfreetype). Render captions as PNGs and
composite with `overlay` rather than assuming `drawtext` exists.

---

## Verify before you send

Do not trust the file you think you uploaded. Download the uploaded video back and
check it — cuts get swapped, and a reply that describes footage the reviewer cannot
see is worse than no reply.

```bash
yt-dlp -o uploaded.mp4 "<url>"
ffprobe -v error -show_entries format=duration -show_entries stream=width,height uploaded.mp4
for t in 10 30 60 90 120; do ffmpeg -v error -i uploaded.mp4 -ss $t -frames:v 1 f$t.jpg -y; done
```

Then walk the frames and confirm each shot in your list is genuinely present. Check
that the video is **unlisted, not private**, and that the aspect ratio and resolution
are what you intended.

---

## Reference the video with timestamps

When you reply, give the reviewer timestamps. It converts "watch this and infer" into
"check these five moments", and it forces you to confirm each moment exists.

```
- 0:40 — consent screen, with "<exact scope description>" shown in full and ticked at 0:57.
- 1:50 — the library: N items read from the account, each badged with its source.
- 2:38 — Settings, showing the connected account and Disconnect.
```

Only claim what is on screen. A reviewer who looks for a feature you listed and cannot
find it will reject on that alone.
