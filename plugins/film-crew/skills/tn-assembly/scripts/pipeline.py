"""Run the whole session-to-published-videos pipeline, stage by stage.

Every stage writes its result into `meta/` and reads only what earlier stages
wrote, so any stage can be re-run alone after a change without repeating the
expensive ones. That matters: ingest and analyse take tens of minutes on an
eight-hour session, while re-planning takes under a second.

    python3 pipeline.py <project>                # everything up to review
    python3 pipeline.py <project> --from plan    # resume after editing scores
    python3 pipeline.py <project> --only analyse
    python3 pipeline.py <project> --doctor       # pre-flight dependencies

Publishing is deliberately NOT part of the default run. Videos are packaged and
left private for a human to approve, because an automated title claiming a
fight that turns out to be applause is a correction you cannot make after the
fact.
"""
import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (Project, approvals_env, cache_key, file_fingerprint,
                    mark_stage_cached, parse_approvals, publish_scripts, say,
                    stage_is_cached)  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

STAGES = ["ingest", "analyse", "vip", "plan", "cut", "build", "shorts",
          "package", "verify"]
APPROVALS = {}


def run(script, *args, cwd=None):
    cmd = [sys.executable, script, *[str(a) for a in args]]
    r = subprocess.run(cmd, cwd=cwd, env=approvals_env(APPROVALS))
    if r.returncode != 0:
        raise RuntimeError(f"stage failed: {' '.join(cmd)}")


def stage_ingest(pr):
    run(os.path.join(HERE, "ingest.py"), pr.root)


def stage_analyse(pr):
    run(os.path.join(HERE, "analyse.py"), pr.root)


def stage_vip(pr):
    if not pr.get("vip", "enabled", default=False):
        say("vip: disabled in project.json -- skipping")
        return
    if not os.path.exists(pr.scan_video):
        say("vip: no scan video; run ingest.py --stage scan first -- skipping")
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
    """Hand each rendered video to the head-of-marketing skill."""
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
    if problems:
        raise RuntimeError("; ".join(problems))


RUNNERS = {
    "ingest": stage_ingest, "analyse": stage_analyse, "vip": stage_vip,
    "plan": stage_plan, "cut": stage_cut, "build": stage_build,
    "shorts": stage_shorts, "package": stage_package, "verify": stage_verify,
}


def _scrub(obj, drop):
    if isinstance(obj, dict):
        return {k: _scrub(v, drop) for k, v in obj.items() if k not in drop}
    if isinstance(obj, list):
        return [_scrub(v, drop) for v in obj]
    return obj


def _plan_for_cut(pr):
    return _scrub(pr.load("plan", default={}) or {},
                  {"file", "cut_start", "cut_end", "duration", "boundary",
                   "render"})


def _planned_cut_outputs(pr):
    plan = pr.load("plan", default={}) or {}
    out = []
    for ep in plan.get("episodes", []):
        for i, _clip in enumerate(ep.get("clips", []), 1):
            out.append(pr.p("clips", ep["id"], f"clip_{i:02d}.mp4"))
    for s in plan.get("shorts", []):
        out.append(pr.p("clips", "shorts", f"{s['id']}.mp4"))
    return out


def _plan_for_render(pr):
    return _scrub(pr.load("plan", default={}) or {}, {"render"})


def _clip_inputs(pr):
    plan = pr.load("plan", default={}) or {}
    rels = []
    for ep in plan.get("episodes", []):
        rels += [c.get("file") for c in ep.get("clips", []) if c.get("file")]
    rels += [s.get("file") for s in plan.get("shorts", []) if s.get("file")]
    return [file_fingerprint(pr.p(r)) for r in sorted(set(rels))]


def _scripts(*names):
    return [file_fingerprint(os.path.join(HERE, n)) for n in names]


def stage_cache_spec(pr, stage):
    """Inputs, settings, tools and expected outputs for a resumable stage."""
    project_json = file_fingerprint(pr.p("project.json"))
    if stage == "ingest":
        outs = [pr.p("meta", "source.json"), pr.audio]
        if pr.get("vip", "enabled", default=False):
            outs.append(pr.scan_video)
        return {
            "inputs": {"project": project_json, "url": pr.get("source", "url"),
                       "scripts": _scripts("ingest.py", "config.py")},
            "settings": {"source": pr["source"], "vip": pr["vip"]},
            "tools": ["yt-dlp", "ffmpeg"],
            "outputs": outs,
        }
    if stage == "analyse":
        return {
            "inputs": {"audio": file_fingerprint(pr.audio),
                       "scripts": _scripts("analyse.py", "config.py")},
            "settings": {"window": 45, "top": 40},
            "tools": ["ffmpeg"],
            "outputs": [pr.p("meta", "features.json"),
                        pr.p("meta", "candidates.json")],
        }
    if stage == "vip":
        if not pr.get("vip", "enabled", default=False):
            return None
        refs = [file_fingerprint(pr.p(r))
                for r in pr.get("vip", "ref_images", default=[])]
        return {
            "inputs": {"scan": file_fingerprint(pr.scan_video), "refs": refs,
                       "scripts": _scripts("faces.py", "config.py")},
            "settings": pr["vip"],
            "tools": ["ffmpeg"],
            "outputs": [pr.p("meta", "vip_hits.json")],
        }
    if stage == "plan":
        return {
            "inputs": {
                "candidates": file_fingerprint(pr.p("meta", "candidates.json")),
                "vip_hits": file_fingerprint(pr.p("meta", "vip_hits.json")),
                "labels": file_fingerprint(pr.p("meta", "labels.json")),
                "scripts": _scripts("plan.py", "config.py"),
            },
            "settings": {"longform": pr["longform"], "shorts": pr["shorts"],
                         "vip_enabled": pr.get("vip", "enabled", default=False)},
            "tools": [],
            "outputs": [pr.p("meta", "plan.json")],
        }
    if stage == "cut":
        return {
            "inputs": {"plan": _plan_for_cut(pr),
                       "audio": file_fingerprint(pr.audio),
                       "source": pr["source"],
                       "scripts": _scripts("cut.py", "boundaries.py",
                                           "config.py")},
            "settings": {"audio": pr.get("audio", default={}),
                         "longform": pr["longform"],
                         "shorts": pr["shorts"]},
            "tools": ["yt-dlp", "ffmpeg", "ffprobe"],
            "outputs": _planned_cut_outputs(pr),
        }
    if stage == "build":
        episodes = (pr.load("plan", default={}) or {}).get("episodes", [])
        return {
            "inputs": {"plan": _plan_for_render(pr), "clips": _clip_inputs(pr),
                       "intro": file_fingerprint(pr.p("assets", "intro.mp4")),
                       "outro": file_fingerprint(pr.p("assets", "outro.mp4")),
                       "scripts": _scripts("build.py", "config.py")},
            "settings": {"video": pr["video"], "brand": pr["brand"]},
            "tools": ["ffmpeg"],
            "outputs": [pr.p("out", ep["id"], "episode_1080p.mp4")
                        for ep in episodes],
        }
    if stage == "shorts":
        shorts = (pr.load("plan", default={}) or {}).get("shorts", [])
        return {
            "inputs": {"plan": _plan_for_render(pr), "clips": _clip_inputs(pr),
                       "scripts": _scripts("shorts.py", "config.py")},
            "settings": {"shorts": pr["shorts"], "brand": pr["brand"]},
            "tools": ["ffmpeg", "ffprobe"],
            "outputs": [pr.p("out", "shorts", f"{s['id']}.mp4")
                        for s in shorts],
        }
    return None


def maybe_run_stage(pr, name):
    spec = stage_cache_spec(pr, name)
    if spec:
        key = cache_key(name, spec["inputs"], spec["settings"], spec["tools"])
        if spec["outputs"] and stage_is_cached(pr, name, key, spec["outputs"]):
            say(f"{name}: unchanged -- skipping")
            return
    RUNNERS[name](pr)
    if spec:
        mark_stage_cached(pr, name, key, spec["outputs"])


def _module_found(name):
    return importlib.util.find_spec(name) is not None


def doctor(pr, stages, project_checks=False):
    """Check the whole requested toolchain before expensive work starts."""
    bins = set()
    mods = set()
    stage_bins = {
        "ingest": ["yt-dlp", "ffmpeg"],
        "analyse": ["ffmpeg"],
        "vip": ["ffmpeg"],
        "cut": ["yt-dlp", "ffmpeg", "ffprobe"],
        "build": ["ffmpeg"],
        "shorts": ["ffmpeg", "ffprobe"],
    }
    for st in stages:
        bins.update(stage_bins.get(st, []))
        if st in ("analyse", "checks"):
            mods.add("numpy")
        if st in ("build", "shorts"):
            mods.add("PIL")
            try:
                publish_scripts()
                mods.add("ct_text")
            except SystemExit as e:
                mods.add(f"ct_text ({e})")
        if st == "package":
            try:
                publish_scripts()
            except SystemExit as e:
                mods.add(f"head-of-marketing ({e})")
        if st == "vip" and pr.get("vip", "enabled", default=False):
            mods.update(["numpy", "insightface", "onnxruntime", "cv2"])

    missing = []
    ok = []
    for b in sorted(bins):
        if not shutil.which(b):
            missing.append(f"binary: {b}")
        else:
            ok.append(f"binary: {b}")
    for m in sorted(mods):
        if m.startswith("ct_text (") or m.startswith("head-of-marketing ("):
            missing.append(m)
        elif not _module_found(m):
            missing.append(f"python module: {m}")
        else:
            ok.append(f"python module: {m}")

    if ok:
        say("doctor: found requirements:")
        for item in ok:
            say(f"  ok {item}")

    if project_checks:
        if pr.config_missing:
            say("doctor: project checks skipped: no project.json")
        elif pr.config_error:
            say(f"doctor: project checks skipped: invalid project.json "
                f"({pr.config_error})")
        elif not pr.get("source", "url"):
            say("doctor: project checks skipped: source.url is empty")
        else:
            say("doctor: project config present")
        if not (pr.config_missing or pr.config_error):
            for b in pr.problems():
                missing.append(f"project.json: {b}")
            dead = pr.unused()
            if dead:
                say("doctor: these project.json keys are not read by anything "
                    "— check the spelling:")
                for d in dead:
                    say(f"  ? {d}")

    if missing:
        say("doctor: missing requirements:")
        for m in missing:
            say(f"  ! {m}")
        raise SystemExit(1)
    say("doctor: all requested requirements found")


def record_failures(pr, failures):
    pr.save("failures", {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "failed_stages": failures,
    })


def main():
    global APPROVALS
    ap = argparse.ArgumentParser(
        description="Run the assembly-session pipeline")
    ap.add_argument("project")
    ap.add_argument("--from", dest="start", choices=STAGES, default=None)
    ap.add_argument("--only", choices=STAGES, default=None)
    ap.add_argument("--to", choices=STAGES, default=None)
    ap.add_argument("--doctor", action="store_true",
                    help="check binaries and Python modules, then exit")
    ap.add_argument("--approve-overwrite", action="append", default=[],
                    help="allow replacing an existing artifact as path:sha256")
    a = ap.parse_args()

    pr = Project(a.project, create_dirs=not a.doctor)
    APPROVALS = parse_approvals(a.approve_overwrite)

    if a.only:
        todo = [a.only]
    else:
        i = STAGES.index(a.start) if a.start else 0
        j = STAGES.index(a.to) + 1 if a.to else len(STAGES)
        todo = STAGES[i:j]

    doctor(pr, todo, project_checks=a.doctor)
    if a.doctor:
        return

    if pr.config_error:
        raise SystemExit(pr.config_error)
    if not pr.url:
        raise SystemExit(f"{pr.p('project.json')} has no source.url")

    failures = []
    record_failures(pr, failures)
    for name in todo:
        say(f"=== {name} ===")
        try:
            maybe_run_stage(pr, name)
        except BaseException as e:
            failures.append({"stage": name, "error": str(e)})
            record_failures(pr, failures)
            break

    if failures:
        say("failed stages:")
        for f in failures:
            say(f"  ! {f['stage']}: {f['error']}")
        raise SystemExit(1)

    record_failures(pr, failures)

    say("done. Nothing has been uploaded -- review, then publish with:")
    say("  python3 ../../head-of-marketing/scripts/upload.py upload "
        "<project>/publish/<id>")


if __name__ == "__main__":
    main()
