# Resume and safety

## Content-hash resume

`pipeline.py` records completed stages in `meta/stage_cache.json`. A stage is
skipped only when all three still match:

- the relevant input file hashes or JSON inputs,
- the settings that affect that stage,
- the toolchain fingerprint, including the first line of `ffmpeg -version`
  where ffmpeg can affect the output bytes.

That means a repeat run does not re-cut or re-render unchanged work, while a
changed plan, changed asset, changed clip or ffmpeg upgrade invalidates the
cache automatically.

## Atomic state writes

State files in `meta/` are written as `target.tmp.<pid>` in the same directory
and then moved into place with `os.replace()`. This avoids a half-written
manifest if the process is interrupted, and keeps the rename atomic on the
same filesystem.

## Doctor pre-flight

Run this before a long job:

```bash
python3 scripts/pipeline.py <project> --doctor
```

The doctor checks all binaries and Python modules needed by the requested
stages and reports every missing dependency in one pass. It is also run
automatically before normal pipeline execution.

## Artifact-bound overwrite approval

The pipeline does not upload or delete source media. Replacing already-rendered
clips or outputs is still guarded: the approval names the exact existing file
and its current SHA-256.

If a command refuses to overwrite, it prints:

```bash
--approve-overwrite '<relative/path.mp4>:<sha256>'
```

Regenerating or editing that file changes the hash, so the old approval lapses.
There is no blanket `--yes`.

## Failure records

`pipeline.py` writes `meta/failures.json` for the current run. If a stage fails,
the file records the stage name and error, the final summary prints the failed
stage list, and the process exits non-zero.
