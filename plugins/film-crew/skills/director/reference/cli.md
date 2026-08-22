# The `/director` command line

`python3 scripts/director.py --help` is authoritative and always current. This
file covers the things a flag list cannot explain.

---

## Starting a production

```bash
director.py --paper --topic "the 1984 Bhopal gas disaster" --parts 2 --shorts 3
```

reads as: *shoot this topic in the paper style, as two episodes of one
narrative, and cut three vertical Shorts from the hookiest moments.*

It writes `production.json` and prints the plan. It does **not** do any of the
work — the crew does that, one stage at a time, through `next` and `advance`.

### `--parts` is a count, not a duration

`--parts 2` means two ordered episodes of one story. `--long 2` is an alias, kept
because it is the obvious thing to type, but it is ambiguous — it reads as
"two long videos" or "two minutes" just as easily. Runtime is separate:

```bash
--parts 2 --runtime 13m        # two episodes, thirteen minutes each
--runtime 8:30                 # one episode, eight and a half minutes
--runtime 480s
```

### `--channel` and `--publish`

`--channel my-handle` selects the profile to *package for* — its metadata
conventions, thumbnail style, tags. `--publish` is the decision to actually
upload. Packaging for a channel without publishing is normal and useful, which
is why neither implies the other.

`--publish` also takes the channel name directly, because that is the obvious
thing to type:

```bash
--publish my-handle                 # same as --channel my-handle --publish
--channel my-handle --publish       # identical
--channel my-handle                 # package only; nothing is uploaded
```

Naming a different channel in each is rejected rather than silently resolved.

---

## Working a production

```bash
director.py next                    # what to do now, who does it, what it must emit
director.py advance <stage> [root] --artifact <file>
director.py status
director.py report
```

`next` prints a handoff: the stage, the crew skill that owns it, why it comes
now, what it must emit, and the exact `advance` line to run when it is done.

**Load a crew skill only when `next` names it.** That is the whole context
strategy — seven skills' worth of instruction never sit in the window together.

### Scope flags

Stages that exist per episode or per Short take a scope:

```bash
director.py advance script . --episode 1 --artifact ep1/script.draft.md
director.py advance shoot    . --short 2   --artifact shorts/s2.mp4
director.py advance research .             --artifact research/ledger.json
```

`research` is production-wide and takes no scope.

### Recording a failure

```bash
director.py advance render --episode 2 --fail "ffmpeg ran out of disk"
```

This is not the same as leaving it undone. A failure is recorded, downstream
stages are blocked, and it appears in `report` — rather than a run that quietly
reports success while episode 2 is missing.

---

## Staleness

Every stage records the sha256 of what it consumed. Change a script and
everything downstream becomes `changed` or `stale`, and `next` sends you back to
redo it.

It is **content-addressed, not timestamp-based**: edit a file and revert it, and
the stages go back to `done`. Touching a file changes nothing.

Stages that emit no artifact of their own — the `lint` gate, for instance —
cannot detect an upstream change by hashing alone, because their record is a
snapshot taken when they ran. They inherit staleness by walking their upstreams
instead.

The cache key also includes a **toolchain fingerprint**. An ffmpeg upgrade can
change output bytes, so it should invalidate a render.

---

## Approval

`publish` is the one irreversible stage, so it is gated on an approval bound to
**the exact bytes** of everything it would put in front of an audience — the
render and the packaged metadata:

```bash
director.py approve publish . --episode 1 --artifact out/ep1.mp4
director.py approve publish . --episode 1 --artifact out/thumb1.jpg
director.py approve publish . --episode 1 --artifact meta/youtube_metadata.json
director.py advance publish . --episode 1 --artifact meta/upload_result.json
```

`approve` prints what is still unapproved, and refuses a file that is not part
of the bundle at all.

An approval covers **one file, for one unit**. Re-render and it lapses; point it
at a different episode and it does not apply.

The set is derived from the unit's own recorded `render`/`shoot` and `package`
artifacts — **not** from whatever `--artifact` is passed to `advance`. That
matters: the caller both proposes what to approve and reports what happened, so
an approval it chose for itself would attest to nothing. Approving an unrelated
file cannot open the gate.

It also folds in whatever `publish.json` says the uploader will attach — which
is where the thumbnail in the example comes from, since no stage records one.
That file is only treated as this unit's when the video it names is this unit's
own render, because one `publish.json` describes one upload while a production
has many. Approving a Short must not silently vouch for episode 1's artwork.

### What the uploader sees

Once a unit's whole bundle is approved, the director writes `publish.lock.json`
— a registry of `{unit, channel, privacy, targets, files: {path: sha256}}`,
one entry per unit, so approving episode 2 does not revoke episode 1.

`head-of-marketing` refuses to upload, edit metadata, replace a thumbnail
or change visibility unless its own `publish.json` matches an entry. It also
copies the approved bytes aside before attaching them, so a file rewritten
between the check and the upload cannot reach the channel. Deleting the lock
is the documented way to act without an approval — and it is announced, not
silent.

### Approval is not consent

They are two different questions, and both must be answered:

| | question | answered by |
|---|---|---|
| **approval** | are *these bytes* good enough to release? | `approve`, per file, per unit |
| **consent** | was this production meant to be released at all? | `--publish <channel>` at plan time |

`--channel` alone records a destination for the metadata; it is **not**
permission to upload, and a production planned without `--publish` will refuse
`advance publish` even when every file is approved. To release one anyway,
say so explicitly:

```bash
director.py advance publish . --episode 1 --allow-publish --artifact meta/upload_result.json
```

That records `publish_authorised_at` in the brief, so the wrap report shows the
release was authorised at the command line rather than planned.

There is deliberately no blanket `--approved` flag. The scope of what is being
agreed to must be visible at the moment of agreeing.

---

## `--skip research` marks the film unverified

Skipping research sets `unverified: true` on the production. From then on
nothing — narration, title, description — may describe the work as researched,
fact-checked or sourced. `report` says so at the bottom, and packaging must
honour it.

---

## `doctor`

```bash
director.py doctor
```

Checks the toolchain, that every crew skill is present, and that every installed
style's dependencies resolve — **before** any expensive work begins. It reports
everything missing at once rather than dying on the first one, because
discovering a missing font after a twenty-minute render is a waste of a
twenty-minute render.

---

## Concurrency and durability

`production.json` is written atomically, through a temp file **in the same
directory** (`os.replace` is only atomic within one filesystem, and `/tmp` is
usually a different one). Saves carry a revision, so a stale writer is refused
rather than silently clobbering a newer state.

The revision alone is not enough: two processes can both read revision 4, both
find it unmoved, and both write revision 5, and the second silently discards the
first while both report success. So `advance` and `approve` also take an
exclusive `flock` on `.director.lock` for the whole read-modify-write. That file
is created next to `production.json` and deliberately **left in place** —
deleting it would hand two later processes two different inodes and no mutual
exclusion at all. It is empty; ignore it, or add it to `.gitignore`.

A `production.json` that is truncated, hand-mangled, or not a production at all
is reported as such rather than raising. So is an unwritable directory.

It is also the memory. If context is compacted and you lose the thread, run
`report` and carry on — do not start the production again.
