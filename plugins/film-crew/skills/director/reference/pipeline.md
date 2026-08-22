# The pipeline

Twelve stages, each owned by one crew skill. `director.py next` tells you which
one you are on; this explains why each exists and what it owes the next.

```
research ─┬─ script ─ punchup ─ lint ─ voice ─ board ─┬─ compile ─ render ─┬─ package ─ publish
          │                                          │                    │
          └─ (per episode) ──────────────────────────┘                    │
                                            cut ─ shoot ──────────────────┘
                                          (per Short)
```

Scope matters: `research` happens once for the whole production; `script`
through `render` happen per episode; `cut` and `shoot` happen per Short;
`package` and `publish` happen per deliverable — every episode and every Short.

This is why the state is a tree and not a list. A production with two episodes
where one rendered and one failed cannot be described by a single `render:
failed`, and pretending otherwise is how a half-finished film gets published.

---

## `research` — screenwriter

Build the fact ledger. Every claim carries two independent citations.

Everything downstream inherits its truthfulness from here, which is why it runs
first and why skipping it marks the whole production `unverified`.

Emits: `research/ledger.json`.

## `script` — screenwriter

Write the narration for this episode against the ledger, sized to the runtime
budget. Every spoken fact traces to a ledger entry.

With `--parts N`, this is **one narrative split into N ordered episodes**, not N
separate videos. Episode 2 assumes episode 1 and must not re-explain it.

Emits: `script.draft.md` — a *draft*. The story editor's pass emits
`script.md`, so the two stages never contend for one filename and a rewrite
at either end is visible to everything downstream.

## `punchup` — story-editor

Engineer retention: the opening three seconds, the open loops that hold the
middle, the re-hooks, and an ending that earns a rewatch.

Emits: `script.md`, the shooting script. This is the file every later stage
reads; `script.draft.md` is kept only so the punch-up can be re-run.

## `lint` — director

**A gate, and the reason the pipeline is trustworthy.**

The story editor just rewrote a script that had already been fact-checked.
Punch-up is exactly the operation that turns *"roughly forty people"* into
*"forty people"*, and a hook is exactly where the temptation to overstate lives.

So both linters run again, here, after the rewrite. A hook that outran its
sources is caught at this stage or it is never caught at all.

Emits nothing — which means it cannot detect upstream change by hashing, and
inherits staleness from `punchup` instead.

## `voice` — voice-booth

One narration clip per line, measured. Everything after this is timed against
these files, so a re-recording invalidates the board, the storyboard and the
render.

Emits: `vo/`.

## `board` — storyboard-artist

Script plus measured narration becomes a style-neutral
[`beat-plan.json`](../../storyboard-artist/reference/beat-plan.md): one
visual event every 2–4 seconds, each pinned to a narration line id.

This is also where the Shorts are chosen, by marking hooks `short_worthy` — the
decision is made once, with the whole script in view.

Emits: `beat-plan.json`.

## `compile` — production-designer

The chosen style compiles the beat plan into its own storyboard.

The result is a **draft that renders**, not a finished board. Open it, cut what
is decorative, give the beats that matter more room. Anything the style could
not draw comes back as a labelled placeholder — resolve every one.

Emits: `storyboard.json`.

## `render` — production-designer

Render, then verify format, loudness and motion. **Check the contact sheet
first** (`--sheet`): it is seconds instead of minutes and it exposes the two
failures a single frame hides — elements piling up because nothing retires, and
neighbours overlapping.

Emits: `*.mp4`.

## `cut` — story-editor

Choose this Short's window from the beat plan's hook markers, and write its own
hook and call to action.

A Short is **not** a crop of the long video. It is a piece that stands alone: it
needs its own opening, and it usually needs re-rendering vertically rather than
cropping, because a 16:9 composition loses its edges in 9:16. Beats marked
`safe: "vertical"` are the ones that survive.

Emits: `short.json`.

## `shoot` — production-designer

Render the vertical Short and check it works without the episode around it.

Emits: `*.mp4`.

## `package` — head-of-marketing

Title, description, chapters, tags, thumbnail — linted against the platform caps
**and against the ledger**. A title that claims more than the research supports
fails here.

If the production is `unverified`, packaging may not describe it as researched
or sourced.

Emits: `meta/youtube_metadata.json`.

## `publish` — head-of-marketing

Upload private, verify what actually went live, then make it public.

Irreversible, so it requires an approval bound to the exact bytes. See
[`cli.md`](cli.md#approval).

Emits: `meta/upload_result.json`.
