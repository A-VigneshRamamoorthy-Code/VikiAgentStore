# Shorts, and linking them back to the film

A Short that does not point at the film it came from is just a Short. The whole
reason to cut them is to feed the thing they were cut from, so the link back is
not a nice-to-have — it is the deliverable.

## Cutting

`shorts.py` reads `meta/shorts_spec.json` and renders 1080x1920 clips from the
finished film. Each Short is a self-contained beat, not a random excerpt:

- **One question, one answer.** A Short that needs setup from the film fails,
  because nobody has seen the film.
- **Hook in the first second**, on screen as text — most Shorts are watched
  muted for the first beat.
- **30–35 seconds** is the useful band for a documentary cut. Long enough for a
  claim and its payoff, short enough to loop.
- **Carry the wordmark** so the Short and the film read as the same channel.
- **End on the reason to watch the film**, not on "subscribe".

Verify frames, not durations: extract the first, middle and last frame and
confirm the hook, the wordmark and the CTA are legible at phone size.

## Uploading

```bash
python3 <skill>/scripts/upload.py shorts .    # uploads every Short
python3 <skill>/scripts/upload.py promote .   # links them to the film
```

They are separate stages on purpose. Uploading is the expensive, one-shot part;
linking is the part that fails for reasons outside the tool. `promote` is
idempotent and safe to re-run, and it resolves video ids by matching titles
against the channel's Shorts tab, so it works even when the published dialog
never surrendered a share link.

A vertical file under about 3 minutes is classified as a Short automatically —
there is no toggle. `#shorts` in the title is conventional, not functional.

## The link back — in order of preference

### 1. Related video (best, and usually locked)

The Short's edit page has a **Related video** field:
`ytcp-text-dropdown-trigger#linked-video-editor-link`. It renders as a
first-class link on the Short itself. Two preconditions:

- the film must already be **public** — a private film never appears in the
  picker;
- the channel must have cleared YouTube's **one-time verification**.

A new channel has not, so clicking the field opens *"One-time verification
needed"* → *"Get advanced features"*, which wants a 6-second selfie video or a
photo ID. That is a human step. Detect it, cancel out, fall back — never try to
satisfy it. `upload.py` raises `TrustWall` for this.

### 2. The description

Always do this, regardless of tier. Put the film on its own labelled line:

```
Full film — <title>:
https://youtu.be/<id>
```

It survives every gate and it is the one link YouTube will always render.

### 3. A comment (the working fallback)

Pinning is gated by the same verification — but *posting* is not, and on a
channel with no other comments the sole comment is the top comment. `promote`
posts the film link as a comment on every Short and is idempotent: it looks for
an existing comment containing the film URL before writing another.

Practical notes:

- The comment box is lazy. It only mounts once the comment section has been
  scrolled into view, so a bare `goto` leaves `#simplebox-placeholder` missing
  and every comment action fails for what looks like the wrong reason. Scroll
  until `ytd-comments #simplebox-placeholder` or
  `ytd-comment-thread-renderer` exists.
- Open the watch page in a **fresh tab** (see `upload.md`).
- The comment's own menu is `#action-menu button` on the
  `ytd-comment-thread-renderer`; its items are
  `ytd-menu-navigation-item-renderer` (Pin / Edit / Delete) inside a visible
  `ytd-menu-popup-renderer` — not `ytd-menu-service-item-renderer`.
- Verify from a signed-out browser. A comment that exists in your session is
  not proof that a viewer can see it.

## What `promote` writes

`meta/shorts_result.json` records, per Short: the file, the resolved
`video_id`, the live link, whether the comment went out, and whether it could
be pinned. When anything was gated it prints the one-line fix:

> Studio → Settings → Channel → Feature eligibility → complete the one-time
> verification.

Re-running `promote` after the channel is verified upgrades every Short from
the comment fallback to a real Related video link.
