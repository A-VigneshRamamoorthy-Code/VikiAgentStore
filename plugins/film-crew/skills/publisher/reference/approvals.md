# Approvals

Everything here answers one question: **did a human agree to this going out?**

Uploading is the only step in the whole pipeline that cannot be undone by
re-running it. A wrong title can be edited, a bad render can be replaced — but
an audience that has already seen the video has already seen it, and on a
sensitive subject that is not recoverable. So the gate is deliberately awkward.

## The lock file

`director` writes `publish.lock.json` into the production root once every
file in a unit's outgoing bundle has been approved by sha256:

```json
{
  "schema": 2,
  "production": "the-1977-wow-signal",
  "approvals": [
    {
      "unit": "episode 1",
      "channel": "mychannel",
      "privacy": "private",
      "at": "2026-08-22T11:22:25Z",
      "by": "vignesh",
      "targets": { "video": "out/ep1.mp4", "thumbnail": "out/thumb1.jpg" },
      "files": { "out/ep1.mp4": "9ab0ce…", "out/thumb1.jpg": "5fcf46…" }
    }
  ]
}
```

It is a **registry, not a single record**. One production has many units, and
approving episode 2 must not quietly revoke episode 1 — nor may one approval for
a long-form film wave through a folder of Shorts. Each entry is found by the
video it names.

## What is checked, and where

| Command | Checks |
|---------|--------|
| `upload` | the whole bundle, then **copies it aside** and attaches the copy |
| `edit` | the bundle, and that the video id is the one this approval produced |
| `thumbnail` | the same |
| `publish` | the same, **plus** that the visibility is not wider than approved |
| `shorts` | every Short in the batch, individually |

Widening is what needs consent: `private → public` is refused, `public →
private` is not.

### Why it copies

Verifying a hash and then handing over the *path* leaves a window: the check
passes, the file is rewritten, and the rewrite is what uploads. A hardlink is
not enough — it survives a `mv` over the original but not an in-place
truncating write, which reaches the same bytes through either name. That was
measured, not assumed. So the approved bytes are copied into `meta/.verified/`
and re-hashed there, and the copy is what the browser attaches.

## Working without an approval

Delete `publish.lock.json`. The uploader will say it is uploading without a
recorded approval and carry on. This is a real workflow — a channel trailer, a
re-upload, a video that never went through the director at all — and pretending
otherwise would only teach people to work around the gate.

What is *not* possible is having a lock present and quietly not honouring it.

## Common refusals

**“no approval covers it”** — `publish.json` names a video that is not in the
registry. Either point it at an approved cut or approve this one.

**“changed since it was approved”** — the file was re-rendered. That is the
gate working; approve the new bytes.

**“approved for channel X”** — approvals are per channel, because the audience
is the thing being decided.

**“schema N, not 2”** — the lock was written by a different director version.
Re-approve rather than guessing what the old format meant.
