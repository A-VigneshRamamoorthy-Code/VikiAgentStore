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

Launch Chrome with a persistent user-data directory so the session survives
between runs. `publish.json`'s `profile` key sets it; it accepts an absolute
path, so **one sign-in can serve every video project** instead of one profile
per film. It defaults to `<project>/.chrome-profile`.

Only one process may hold a profile at a time. A second Playwright run against
the same directory will not queue — plan stages sequentially.

Resolve the path through `Publish.profile`, never by reading the raw JSON
value. A helper that takes `publish.json["profile"]` literally and runs from
another working directory creates a brand-new empty profile there and lands on
the Google sign-in page — which is indistinguishable from "the session
expired", and sends you looking for the wrong bug.

**Never SIGKILL the browser.** Always `ctx.close()`. Killing it mid-write
corrupts the profile and the next run lands on a signed-out page.

Note that `bash -c "python3 upload.py ..."` puts a shell between you and the
Python process: signalling the shell does not signal the child, so the
`finally: ctx.close()` never runs. Resolve the real PID
(`ps -eo pid,command | grep '[u]pload.py'`) and signal that.

## Signing in a fresh profile

`recon` only reports; it cannot authenticate. A new profile needs the `login`
stage, which opens Studio non-headless and waits for a human.

Two things that cost time here:

- **Poll every tab, not `pages[0]`.** Google frequently completes sign-in in a
  second tab, so watching only the first one reports failure after a
  successful login.
- **Verify from disk, not from the UI.** Copy `Default/Cookies` and look for
  `SID`, `SSID`, `HSID`, `APISID`, `SAPISID`, `LOGIN_INFO`. That settles "did
  they actually sign in?" in seconds, with no ambiguity about what the page is
  showing.

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

But the deep link only holds when it is the navigation that *lands*. Arriving
from the dashboard, the SPA router will bounce back to the dashboard and leave
you on a page with no picker, where waiting on `input[type=file]` times out
after a full minute. Check that the dialog is really open, and fall back to the
dashboard's own upload control.

That control has been renamed more than once. As of this writing it is
`ytcp-icon-button#upload-icon` (aria-label **Upload videos**) in the top right
of the dashboard; `#upload-videos-button` no longer exists. Match on the aria
label as well as the id — the label has outlived every id. The header
**Create** menu is the last resort, and note its aria label sits on the inner
`<button>`, not on the `ytcp-button` wrapper, so
`ytcp-button[aria-label='Create']` matches nothing.

`input[type=file]` on its own is not proof: Studio keeps a detached uploads
dialog in the DOM on other pages. Test visibility of `ytcp-uploads-file-picker`
or `ytcp-uploads-dialog`.

## The SPA router, and the one reliable way around it

Studio rewrites navigations issued inside a tab that has **already rendered
another Studio route**. Land on the dashboard, then `page.goto` the video list
or a video's edit page, and the URL is silently rewritten back to the
dashboard. Retrying in the same tab does not help — it fails identically three
times in a row, and the screenshot shows a perfectly healthy page that simply
is not the one you asked for.

**Open a new tab.** A new tab is always a first navigation, and a first
navigation always lands:

```python
tab = page.context.new_page()
tab.goto(url, wait_until="domcontentloaded")
...
tab.close()
```

`fresh_tab()` does this. Use it for anything read-only, and for the edit,
thumbnail and related-video flows. `goto_verified()` — navigate, then confirm a
marker element, retrying — remains useful where a tab must be reused, but the
fresh tab is strictly more reliable.

**Pick visible markers, not wrapper elements.** `#title-textarea` is a
zero-size custom element, so `wait_for(state="visible")` never matches it;
`#title-textarea #textbox` does. The same is true of `ytcp-video-row`: don't
wait on it, walk the shadow DOM for it and poll until the walk returns rows.

## Finding a video id after upload

The published dialog does not reliably surrender the share link. Rather than
depending on it, scrape the channel's own lists and match on title:

- Rows are `ytcp-video-row` (in a shadow root — walk `shadowRoot` recursively).
- Each row contains `a[href*='/video/<id>']` and its `innerText` carries
  duration, title and description.
- The Shorts tab is `/videos/short`; long-form is `/videos/upload`.

Open those lists with `fresh_tab`, or they bounce.

## Channel verification gates more than metadata

A brand-new channel sits in YouTube's lowest trust tier. Several things that
look like ordinary metadata are locked behind a **one-time verification**,
and all of them raise the same wizard — *"One-time verification needed"*,
then *"Get advanced features"*, offering:

1. a 6-second video of yourself,
2. a photo of your ID, or
3. "build history as you grow" (~2 months of active use, automatic).

Known to be gated:

- **Related video** on a Short (the first-class Short → film link).
- **Pinning a comment.**

All three options need a human being. There is no automation path and no
API around it — this is precisely the boundary an agent must not cross.
Detect the wall (`tp-yt-paper-dialog` containing "get advanced features" or
"one-time verification"), cancel out so nothing is left half-applied, and
report it. `upload.py` raises `TrustWall` for exactly this, which is why it is
a distinct exception and not a generic failure: it is not retryable.

The user-facing fix is one line: **Studio → Settings → Channel → Feature
eligibility**, then complete the verification.

## The thumbnail step fails silently

In the upload wizard, `set_input_files` on the thumbnail input succeeds, no
error appears, the log says "thumbnail attached" — and YouTube serves an
auto-generated frame from the film instead. On a documentary that means a
random mid-scene frame in every search result.

Studio's edit page is not proof either: it renders the *pending* selection.

The only honest check is the CDN, cache-busted, because that is what a viewer
sees:

```
https://i.ytimg.com/vi/<id>/maxresdefault.jpg?bust=<timestamp>
```

Downscale both it and the local file to 160x90 and compare mean absolute
difference; identical files land under 1.0. Compare against `maxresdefault`
only — `hqdefault` is cropped to 4:3 and will never match.

The `thumbnail` stage re-applies the file on the edit page and then polls the
CDN until it matches, which takes a minute or so to propagate.

## Overlays eat clicks

## The upload is not finished when Studio says it is

The most expensive trap in this whole skill, and it cost two full 1.9 GB
uploads to see.

Studio enables **Done**, writes the video id, shows the share link and reports
"Saved as private" while the file is still going up. The transfer continues in
the background of that browser tab. Close the browser at that point and the
upload is silently abandoned — the draft sits on the channel forever at
whatever percent it reached, with a perfect title, description, tags and
thumbnail. That polish is exactly what makes it look successful.

Wait on the progress label (`ytcp-video-upload-progress`) until it stops
starting with "Uploading". Only then click Done and close.

A part-uploaded draft **cannot be resumed** — the session that owned it is
gone. Remove it and start again. Note the row shows **Cancel upload** rather
than the usual overflow menu, so the delete path does not apply; click Cancel
upload, then `ytcp-button#confirm-button`.

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
box, select all, delete, then insert. Studio pre-seeds the title from the
filename, so a box that looks populated is not evidence your text was applied.

Use `page.keyboard.insert_text(text)` — one CDP call — rather than typing
character by character. A 4,400-char description at 6 ms/char holds focus for
around half a minute, and an upload toast or the checks panel will take it
mid-way, leaving a truncated description that looks entirely plausible. Read
the value back and compare lengths; Studio normalises whitespace, so allow a
few percent of slack rather than demanding an exact match.

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

### One cosmetic red herring

On the edit page the **Description** label and its border sometimes render in
red with no error text anywhere, while the content is correct and both Save and
Undo are disabled — i.e. there is nothing unsaved and nothing rejected. Treat a
red label alone as cosmetic. The signal that actually matters is *"Cannot save
until errors are resolved"*, or a Save button that stays enabled after saving.

## Verifying what actually went live

Studio's visibility field reads "Pending" until processing finishes, so it
proves nothing. Worse, the visibility card reflects the *dialog's pending
selection*, so reading it back without reloading cheerfully confirms a change
that was never saved.

Check from outside the session. Open the watch page in a browser with no
cookies and read `ytInitialPlayerResponse.playabilityStatus`:

- `LOGIN_REQUIRED` / `"Private video"` → still private.
- `OK`, plus `videoDetails.isPrivate === false` → genuinely public.

Scraped watch-page HTML and the oEmbed endpoint are both unreliable here
(oEmbed 403s for anything non-public, and the channel RSS feed lags by hours).
Confirm resolution and duration with `ffprobe` against the source you
uploaded, not against Studio's display.

Two-step confirms are easy to miss. Making a video public needs **both**
`ytcp-button#save-button` inside the dialog (labelled "Done" — it only closes
the dialog) and the page's own `ytcp-button#save`, which is what persists.
Clicking only the first reports success and changes nothing.

## The silent metadata bug

The uploader reads exactly one file: `meta/youtube_metadata.json`.

A generator that writes `meta/youtube.json` instead does not fail. The upload
succeeds using whatever stale file was there before, and the only symptom is a
log line reporting a character count that does not match what you just
generated. **Always compare the reported title/description/tag counts against
the generator's output.** If they differ, the wrong file was read.
