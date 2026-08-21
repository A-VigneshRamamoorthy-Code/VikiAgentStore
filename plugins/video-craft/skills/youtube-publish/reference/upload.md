# Upload: driving YouTube Studio

Every item here cost a failed run. They are listed roughly in the order you hit
them.

## Why not the Data API

The Data API needs a Google Cloud OAuth app that is either published or lists
the uploader as a test user. For a personal channel that flow is a wall: the
consent screen reports "OAuth configuration is incomplete", Publish stays
disabled, and saving a test user silently does nothing. Creating an "external"
app just to post to your own channel is also the wrong shape of solution.

Driving `studio.youtube.com` in a browser that is already signed in sidesteps
the app entirely. That is the supported path here.

## The persistent profile

Launch Chrome with a persistent user-data directory (`<project>/.chrome-profile`)
so the session survives between runs. Sign in once, interactively.

**Never SIGKILL the browser.** Always `ctx.close()`. Killing it mid-write
corrupts the profile and the next run lands on a signed-out page.

## Channel selection

A Google login usually owns several brand accounts, and lookalike names are
common — `Politainment`, `Politainment Re-defined`, `Politainment Gamer`. Studio
opens whichever was active last.

- Match the handle **exactly**. Substring matching picks the wrong channel,
  because every one of those contains `politainment` as a prefix.
- The channel switcher rows are `ytd-account-item-renderer` elements, **not**
  `<a>` tags.
- Assert the active channel before uploading *and* before editing. Uploading a
  finished episode to the wrong channel is not fixable by editing.

## Opening the upload dialog

Go straight to `https://studio.youtube.com/channel/<id>/videos/upload?d=ud`.
Hunting for the Create button is fragile — its Polymer id changes between
Studio revisions.

## Overlays eat clicks

Polymer backdrops and the cookie bar sit transparently over the page and
swallow clicks that appear to land correctly:

```
tp-yt-iron-overlay-backdrop
.glue-cookie-notification-bar
[id^=glue-cookie-notification-bar]
tp-yt-paper-dialog-scrollable + .backdrop
```

Remove them before **every** click, not once at the start — they reappear.

## Title and description are contenteditable

They are `contenteditable` divs, not inputs. `fill()` does not work; focus the
box, select all, then type. Studio pre-seeds the title from the filename, so a
box that looks populated is not evidence your text was applied.

## Tags are chips — the expensive one

Tags render as removable chips. Consequences:

- `Cmd+A` then `Backspace` in the tag box does **nothing**.
- New tags therefore **append** to the existing ones. A fresh 17-tag set added
  to an existing 22-tag set produced 554 characters against the 500 cap, and
  Studio refused to save with *"Cannot save until errors are resolved"* — a
  message that never mentions tags.
- Worse, the last surviving old chip **fuses** with the first new tag into one
  corrupt entry.

Clear them properly: click the clear-all button if present, then delete each
remaining chip individually, then press Backspace to catch any stragglers.
Assert `0 chip(s) remaining` before typing.

## The edit page URL

Editing an existing video is:

```
https://studio.youtube.com/video/<videoId>/edit
```

**Not** under `/channel/<channelId>/...`. The channel-prefixed form returns
"Oops, something went wrong".

Use `edit` rather than re-uploading whenever only metadata changed — it saves
transferring hundreds of megabytes.

## Verifying what actually went live

Studio's visibility field reads "Pending" until processing finishes, so it
proves nothing. Check from outside the session:

- An anonymous fetch of the watch URL returning `LOGIN_REQUIRED` confirms it is
  private.
- The oEmbed endpoint returning 403 confirms the same.
- Confirm resolution and duration with `ffprobe` against the source you
  uploaded, not against Studio's display.

## The silent metadata bug

The uploader reads exactly one file: `meta/youtube_metadata.json`.

A generator that writes `meta/youtube.json` instead does not fail. The upload
succeeds using whatever stale file was there before, and the only symptom is a
log line reporting a character count that does not match what you just
generated. **Always compare the reported title/description/tag counts against
the generator's output.** If they differ, the wrong file was read.
