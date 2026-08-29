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

## Getting a file into a bundle the director derives

`--artifact` does not choose *what* is approved. The director derives the
outgoing bundle from `publish.json`'s targets plus the recorded upstream work,
and `--artifact` only names which members of that derived set the human is
signing off — naming a file outside it approves nothing, and naming none of
them is refused outright:

```
director: approve what, exactly? pass --artifact <file> — an approval
that is not bound to a file approves nothing
```

That is the point: if the caller could both propose what is approved and report
what happened, the approval would say nothing at all. It does mean a file the
derivation does not know about **cannot be added to the bundle from the command
line**. A Short's thumbnail is the case in point — a Short's bundle is its
video, its captions, its mix report and `meta/shorts_publish.json`, and a
`publish.json` thumbnail belongs to the film, not to it.

Lock it **through a file that is already in the bundle**. Record the path and
sha256 in `meta/shorts_publish.json`, then re-approve the Short:

```jsonc
{ "id": "s1", "file": "short1/short.mixed.mp4",
  "thumbnail": "short1/meta/thumbnail.jpg",
  "thumbnail_sha256": "a3175423fe21…" }
```

The spec is hashed by the approval, the spec records the image, so the image is
covered by the director's lock transitively rather than on the uploading
script's word.

Two things follow. **Editing the spec lapses every Short at once**, because
every Short's entry covers that one file — so adding thumbnails to it means
re-approving all of them, not just the one you were working on. And the lock is
only written once the *whole* derived set is named; leave a member out and the
run says so and writes nothing:

```
approved for short 1 / publish: short1/short.mixed.mp4
still unapproved for short 1 / publish:
    meta/shorts_publish.json
```

```bash
for n in 1 2 3; do
  director.py approve publish . --short $n --artifact \
    short$n/short.mixed.mp4 meta/shorts_publish.json \
    short$n/meta/mix_report.json short$n/meta/captions.srt
done
```

Approving one unit otherwise leaves the others alone — the lock is a registry,
and re-approving an episode does not disturb the Shorts beside it.

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
