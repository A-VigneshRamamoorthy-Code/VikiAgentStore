"""Compose YouTube title, description, chapters and tags for any video.

Search indexes the **title, description and tags**. It does not index the audio.
So every concept a viewer might type has to appear as text, and if the spoken
language differs from the language people search in, it has to appear twice.
That is the whole reason this module treats a "primary" and a "secondary"
language as first-class: a Tamil video with Tamil-only metadata is invisible to
"Tamil Nadu assembly highlights", which is how most of its potential audience
actually searches.

Reads `meta/metadata_spec.json`, writes the file the uploader consumes. See
`../reference/seo.md` for what goes in each field and why, and
`../reference/titles.md` for how to write the hook.
"""
import argparse
import json
import os
import subprocess

from config import LIMITS, Publish, check_limits, say


def duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], capture_output=True, text=True)
    if out.returncode != 0 or not out.stdout.strip():
        raise SystemExit(f"cannot probe {path}")
    return float(out.stdout.strip())


def mmss(t):
    t = int(round(t))
    return f"{t // 60}:{t % 60:02d}"


def compose_title(hook, tails, limit=LIMITS["title"]):
    """Hook first, keyword tails appended while they still fit.

    The hook earns the click and must never be truncated, so it is placed
    first and the keyword tail is what gets dropped. YouTube elides long
    titles in search, and everything past ~70 characters is for the index
    rather than the reader.
    """
    title = hook.strip()
    for tail in tails:
        candidate = f"{title} | {tail.strip()}"
        if len(candidate) <= limit:
            title = candidate
    if len(title) > limit:
        title = title[:limit].rstrip()
    return title


def build_chapters(spec, root):
    """Chapter offsets from the rendered files, so timestamps cannot drift.

    Clip lengths change whenever cuts are re-snapped; computing offsets from
    the actual files is the only way the description stays truthful.
    """
    lines, t = [], 0.0
    intro = spec.get("intro_file")
    if intro:
        label = spec.get("intro_label", "Intro")
        lines.append(f"0:00 {label}")
        t += duration(os.path.join(root, intro))
    for ch in spec.get("chapters", []):
        label = ch["label"]
        if ch.get("gloss"):
            label = f"{label} | {ch['gloss']}"
        lines.append(f"{mmss(t)} {label}")
        t += duration(os.path.join(root, ch["file"]))
    return "\n".join(lines), t


def budget_tags(groups, limit=LIMITS["tags_total"]):
    """Fit tags under the character cap, highest priority first.

    Groups are consumed in order, so put the terms you most want indexed
    first. Exceeding the cap makes Studio refuse to save with a message that
    never mentions tags, so this is enforced rather than trusted.
    """
    kept, used = [], 0
    for group in groups:
        for tag in group:
            tag = tag.strip()
            if not tag or tag in kept:
                continue
            cost = len(tag) + (1 if kept else 0)
            if used + cost > limit:
                continue
            kept.append(tag)
            used += cost
    return kept, used


def build(spec, root):
    chapters, runtime = build_chapters(spec, root)
    title = compose_title(spec["hook"], spec.get("title_tails", []))

    tags, tag_len = budget_tags([
        spec.get("tags", {}).get("primary", []),
        spec.get("tags", {}).get("secondary", []),
        spec.get("tags", {}).get("extra", []),
    ])

    parts = [spec["lead"].strip(), ""]
    if spec.get("chapters"):
        parts += [spec.get("chapters_heading", "Chapters"), chapters, ""]
    if spec.get("summary_secondary"):
        parts += [spec.get("summary_heading", "In English"),
                  spec["summary_secondary"].strip(), ""]
    if spec.get("topics"):
        parts += [spec.get("topics_heading", "Topics covered"),
                  " · ".join(spec["topics"]), ""]
    src = spec.get("source") or {}
    if src.get("name"):
        parts += [spec.get("source_heading", "Source"),
                  src["name"], src.get("url", ""), ""]
    if spec.get("cta"):
        parts += [spec["cta"].strip(), ""]
    if spec.get("hashtags"):
        parts.append(" ".join(
            h if h.startswith("#") else f"#{h}" for h in spec["hashtags"]))

    description = "\n".join(p for p in parts if p is not None).strip() + "\n"

    meta = {
        "title": title,
        "description": description,
        "tags": tags,
        "categoryId": spec.get("category_id", "25"),
        "privacyStatus": spec.get("privacy", "private"),
        "madeForKids": bool(spec.get("made_for_kids", False)),
        "language": spec.get("language", "en"),
    }
    return meta, {"runtime": runtime, "tag_chars": tag_len}


def main():
    ap = argparse.ArgumentParser(description="Build YouTube metadata")
    ap.add_argument("project")
    ap.add_argument("--spec", default=None,
                    help="defaults to <project>/meta/metadata_spec.json")
    a = ap.parse_args()

    pub = Publish(a.project)
    spec_path = a.spec or pub.p("meta", "metadata_spec.json")
    if not os.path.exists(spec_path):
        raise SystemExit(f"missing {spec_path}")
    spec = json.load(open(spec_path))

    meta, info = build(spec, pub.root)
    problems = check_limits(meta)
    if problems:
        raise SystemExit("metadata rejected: " + "; ".join(problems))

    os.makedirs(os.path.dirname(pub.metafile), exist_ok=True)
    with open(pub.metafile, "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    say(f"title       {len(meta['title'])}/{LIMITS['title']}")
    say(f"description {len(meta['description'])}/{LIMITS['description']}")
    say(f"tags        {info['tag_chars']}/{LIMITS['tags_total']} "
        f"({len(meta['tags'])} tags)")
    say(f"runtime     {mmss(info['runtime'])}")
    say(f"wrote {pub.metafile}")


if __name__ == "__main__":
    main()
