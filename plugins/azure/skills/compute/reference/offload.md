# The offload contract — how another skill borrows compute

This is the interface. A skill that wants a bigger machine does not need to know
anything about Azure; it needs to know these five arguments.

```bash
python3 SCRIPTS/azc.py offload \
  --profile <profile> \
  --hours   <expected runtime, for pricing> \
  --push    <local dir to upload> \
  --cmd     "<command to run there>" \
  --pull    :<remote path> \
  --dest    <local dir for results>
```

`offload` creates the machine, uploads, runs, downloads and **always destroys**, in a
`finally` block — the VM dies whether the command succeeds, fails, or the whole thing
is interrupted.

## Path conventions

- The remote working directory is `/home/azc/work`.
- A path starting with `:` is relative to it. `:out` means `/home/azc/work/out`.
- `--push ./project` uploads the **contents** of `./project` into the working
  directory, so `./project/render.sh` becomes `render.sh` there.
- `--pull :out --dest ./output` puts the contents of the remote `out/` into
  `./output/`.

## Several steps in order

Repeat `--cmd`. They run in sequence and the first failure stops the rest.

```bash
python3 SCRIPTS/azc.py offload --profile render --hours 3 \
  --push ./film \
  --cmd "pip3 install -q -r requirements.txt" \
  --cmd "python3 scripts/render.py --style paper" \
  --cmd "python3 scripts/captions.py" \
  --pull :out --dest ./film/out
```

## Worked example — a film-crew render

The heavy stage of a film-crew production is compositing and encoding. Everything else
(scripting, research, storyboard planning) is cheap and should stay local. Offload only
the expensive stage:

```bash
python3 SCRIPTS/azc.py offload \
  --profile render --hours 2 \
  --push ./production \
  --cmd  "python3 scripts/render.py --storyboard storyboard.json --out out/film.mp4" \
  --pull :out --dest ./production/out
```

The `render` profile arrives with ffmpeg, Pillow, numpy and DejaVu/Liberation fonts
already installed. If a stage needs something else, either add it to the profile in
`scripts/profiles.json` or install it as the first `--cmd`.

**Fonts are the classic failure.** A render that looks right locally loses its captions
on a bare VM because the font file is not there. Ship fonts with the payload and
reference them by path, or add the package to the profile.

## Choosing `--hours`

It does not limit anything — it prices the job, and the price decides the machine. Too
low and you may get a machine bigger than the budget can sustain; too high and the
planner downgrades you unnecessarily. Estimate honestly, then let `--ttl` be the real
safety limit.

## When to keep a machine instead

`offload` pays the two-to-four minute build cost every time. If a skill has several
stages that must share large intermediate files, hold one machine open:

```bash
JOB=$(python3 SCRIPTS/azc.py up --profile render --ttl 180 --json | python3 -c 'import json,sys;print(json.load(sys.stdin)["job"]["id"])')
python3 SCRIPTS/azc.py push ./film : --job "$JOB"
python3 SCRIPTS/azc.py run "python3 stage1.py" --job "$JOB"
python3 SCRIPTS/azc.py run "python3 stage2.py" --job "$JOB"
python3 SCRIPTS/azc.py pull :out ./out --job "$JOB"
python3 SCRIPTS/azc.py down --job "$JOB"
```

`--job` is optional when exactly one machine is running. Wrap this in a trap so the
`down` still runs if the script dies:

```bash
trap 'python3 SCRIPTS/azc.py down --job "$JOB"' EXIT
```

## What to tell the user

Report the plan before launching and the cost after finishing. Both come from the tool
— do not estimate:

```bash
python3 SCRIPTS/azc.py plan --profile render --hours 2 --json
python3 SCRIPTS/azc.py status --all --json
```

## Rules for a calling skill

1. **Offload the expensive stage, not the whole pipeline.** Uploading a project to run
   thirty seconds of work is slower than doing it locally.
2. **Never hardcode a VM size.** Ask for a profile and let the budget decide.
3. **Make the remote command idempotent and self-contained.** It runs in a fresh shell,
   in the working directory, as a non-root user with passwordless `sudo`.
4. **Pull everything you need before the machine dies.** There is no second chance.
5. **Do not offload secrets.** The payload is uploaded verbatim. Exclude `.env`,
   tokens and keys.
