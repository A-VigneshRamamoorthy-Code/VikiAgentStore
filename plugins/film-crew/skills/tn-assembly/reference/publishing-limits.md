# Publishing limits and verification

Hard platform limits and the verification habits that this session learned the
expensive way. All of it was established by measurement against a live,
verified channel.

## The custom thumbnail quota

**There is a daily cap on custom thumbnails, and it is not documented in the
UI until you hit it.** The verbatim dialog:

> Daily custom thumbnail limit reached — It may take up to 24 hours before you
> can create a new custom thumbnail.

Established facts, each of which cost a wrong guess first:

| Question | Answer | How it was established |
|---|---|---|
| Is it a permissions problem? | **No** | Settings › Channel › Feature eligibility showed Standard, Intermediate **and Advanced** all Enabled. |
| Does it reset at midnight? | **No — rolling 24h** | Midnight Pacific fell at 08:00 local; attempts at 09:06 and 09:38 were both refused. |
| Does the A/B Testing route avoid it? | **No** | Tested directly. "Test & compare › Thumbnail only" raises the identical dialog. |
| Does the Data API avoid it? | **No** | Returns `uploadLimitExceeded`. |
| How many applications fit? | **~17 per rolling 24h** | Counted from on-disk attach timestamps. |

Confirmed end to end: the first refusal came at 07:13 and the window released
at about 17:05 the same day — **just under ten hours** of blocked retrying for a
two-poster text correction. Budget for that, because there is no way to
shorten it.

Two non-obvious consequences:

1. **The upload wizard spends the same allowance.** A thumbnail attached during
   the initial upload is a custom-thumbnail application. Publishing nine videos
   with thumbnails spends nine of your ~17 before you have corrected anything.
2. **The cap fires on *attach*, before Save.** The dialog appears the instant
   the file is selected — it is a client-side read of known quota state, so
   nothing is transmitted. A refused attempt therefore does not appear to
   consume allowance, which is what makes patient retrying safe.

### Budget accordingly

Get the thumbnail right **before** the upload, not after. A batch of nine
videos plus one round of corrections already exceeds the daily allowance, and
a correction that misses leaves a wrong image live for a full day.

Never force the disabled Save button via DOM injection. It is an anti-abuse
control, and the channel is worth more than the hour saved.

## Verify every write from the public side

Studio showing a value does not mean the value is live. Everything below was a
real failure in this session.

- **Read back thumbnails from the CDN, not from Studio.** Studio's editor can
  show the new image while `i.ytimg.com` still serves the old one.
- **Cache-bust every thumbnail read-back.** `i.ytimg.com/vi/<id>/maxresdefault.jpg`
  served a byte-identical *pre-fix* copy for minutes after a change had already
  taken effect; the same URL with a cache-busting query parameter returned a
  different, corrected image. A correct fix therefore reads as a failure, and a
  retry loop keeps spending quota on a problem that no longer exists.

  ```bash
  curl -s -H "Cache-Control: no-cache" -o out.jpg \
       "https://i.ytimg.com/vi/$ID/maxresdefault.jpg?cb=$(date +%s)$RANDOM"
  ```

  Only `maxresdefault` was affected — `hqdefault`, `sddefault` and `oardefault`
  matched with and without the buster.
- **For text changes, look at the image.** A typo fix (கருவூர் → கரூர்) is a
  small number of pixels. A whole-image difference score of **3.21** — far
  inside a tolerance of 8.0 — was returned by a poster that still had the typo
  on it. Compare **worst-block** difference as well as global mean; the same
  poster scored 37.64 on worst-block against a limit of 15. Better still, view
  the rendered image directly before declaring a text fix done.
- **A numeric verifier is a filter for failure, not proof of success.** Across
  this session an automated "applied / verified" signal was wrong about the
  same two images three separate times, in both directions — passing a poster
  that carried the typo, and later failing one that had already been corrected.
  Stop the retry loop as soon as a human-read confirmation lands, so it cannot
  act on its own false negative and re-upload a correct image.
- **Set Related video by video id, then read it back.** Title-based matching
  silently attaches the wrong episode.

The general rule: **a write is not done until it has been confirmed from the
outside.** Studio is a cache.

## Cadence limits

Beyond thumbnails, uploading many videos in a few hours is self-defeating for
distribution reasons rather than quota ones — see `reference/distribution.md`.
Nine Shorts in one day produced one tested video and eight ignored ones.

## Channel prerequisites worth checking once

- **Phone verification** gates custom thumbnails entirely. Check
  Settings › Channel › **Feature eligibility** before diagnosing anything else;
  it is one screen and it eliminates a whole class of wrong theories.
- Linking a Short to a parent video requires the channel to be in good
  standing. Verify the link resolves publicly afterwards.
