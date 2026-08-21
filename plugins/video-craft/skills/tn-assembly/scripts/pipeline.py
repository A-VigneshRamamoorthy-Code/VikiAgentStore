"""Run the whole session-to-published-videos pipeline, stage by stage.

Every stage writes its result into `meta/` and reads only what earlier stages
wrote, so any stage can be re-run alone after a change without repeating the
expensive ones. That matters: ingest and analyse take tens of minutes on an
eight-hour session, while re-planning takes under a second.

    python3 pipeline.py <project>                # everything up to review
    python3 pipeline.py <project> --from plan    # resume after editing scores
    python3 pipeline.py <project> --only analyse

Publishing is deliberately NOT part of the default run. Videos are packaged and
left private for a human to approve, because an automated title claiming a
fight that turns out to be applause is a correction you cannot make after the
fact.
"""
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import Project, publish_scripts, say  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

STAGES = ["ingest", "analyse", "vip", "plan", "cut", "build", "shorts",
          "package", "verify"]


def run(script, *args, cwd=None):
    cmd = [sys.executable, script, *[str(a) for a in args]]
    r = subprocess.run(cmd, cwd=cwd)
    if r.returncode != 0:
        raise SystemExit(f"stage failed: {' '.join(cmd)}")


def stage_ingest(pr):
    run(os.path.join(HERE, "ingest.py"), pr.root)


def stage_analyse(pr):
    run(os.path.join(HERE, "analyse.py"), pr.root)


def stage_vip(pr):
    if not pr.get("vip", "enabled", default=False):
        say("vip: disabled in project.json -- skipping")
        return
    if not os.path.exists(pr.scan_video):
        say("vip: no scan video; run ingest.py --video first -- skipping")
        return
    run(os.path.join(HERE, "faces.py"), pr.root, "--scan")


def stage_plan(pr):
    run(os.path.join(HERE, "plan.py"), pr.root)


def stage_cut(pr):
    run(os.path.join(HERE, "cut.py"), pr.root)


def stage_build(pr):
    run(os.path.join(HERE, "build.py"), pr.root)


def stage_shorts(pr):
    run(os.path.join(HERE, "shorts.py"), pr.root)


def stage_package(pr):
    """Hand each rendered video to the youtube-publish skill."""
    pub = publish_scripts()
    plan = pr.load("plan") or {}
    made = 0
    for item in plan.get("episodes", []) + plan.get("shorts", []):
        if not item.get("render"):
            continue
        d = pr.p("publish", item["id"])
        if not os.path.exists(os.path.join(d, "meta", "metadata_spec.json")):
            say(f"package: {item['id']} has no metadata_spec.json yet -- "
                "write one (see reference/packaging.md), then re-run")
            continue
        run(os.path.join(pub, "metadata.py"), d)
        run(os.path.join(pub, "seocheck.py"), d)
        made += 1
    say(f"package: {made} video(s) have upload-ready metadata")


def stage_verify(pr):
    plan = pr.load("plan") or {}
    problems = []
    for ep in plan.get("episodes", []):
        f = pr.p(ep["render"]) if ep.get("render") else None
        if not f or not os.path.exists(f):
            problems.append(f"{ep['id']}: not rendered")
    for s in plan.get("shorts", []):
        f = pr.p(s["render"]) if s.get("render") else None
        if not f or not os.path.exists(f):
            problems.append(f"{s['id']}: not rendered")
    for p in problems:
        say(f"  ! {p}")
    say("verify: all planned videos rendered" if not problems
        else f"verify: {len(problems)} missing")
    say("Check A/V sync on at least one clip before publishing:")
    say(f"  python3 checks.py {pr.root} <clip.mp4> <source_start_seconds>")


RUNNERS = {
    "ingest": stage_ingest, "analyse": stage_analyse, "vip": stage_vip,
    "plan": stage_plan, "cut": stage_cut, "build": stage_build,
    "shorts": stage_shorts, "package": stage_package, "verify": stage_verify,
}


def main():
    ap = argparse.ArgumentParser(
        description="Run the assembly-session pipeline")
    ap.add_argument("project")
    ap.add_argument("--from", dest="start", choices=STAGES, default=None)
    ap.add_argument("--only", choices=STAGES, default=None)
    ap.add_argument("--to", choices=STAGES, default=None)
    a = ap.parse_args()

    pr = Project(a.project)
    if not pr.url:
        raise SystemExit(f"{pr.p('project.json')} has no source.url")

    if a.only:
        todo = [a.only]
    else:
        i = STAGES.index(a.start) if a.start else 0
        j = STAGES.index(a.to) + 1 if a.to else len(STAGES)
        todo = STAGES[i:j]

    for name in todo:
        say(f"=== {name} ===")
        RUNNERS[name](pr)

    say("done. Nothing has been uploaded -- review, then publish with:")
    say("  python3 ../../youtube-publish/scripts/upload.py upload "
        "<project>/publish/<id>")


if __name__ == "__main__":
    main()
