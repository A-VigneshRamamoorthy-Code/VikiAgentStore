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

# Studio never asks for a category during upload; it silently files everything
# under "People & Blogs". These are the labels its dropdown actually shows, so
# the uploader can pick one by name.
CATEGORY_LABEL = {
    "22": "People & Blogs",
    "24": "Entertainment",
    "25": "News & Politics",
    "27": "Education",
    "29": "Nonprofits & Activism",
}


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


def parse_at(v):
    """Accept 93.4, "1:33", or "1:33.4" as a chapter offset in seconds."""
    if isinstance(v, (int, float)):
        return float(v)
    parts = str(v).strip().split(":")
    try:
        secs = float(parts[-1])
        for i, p in enumerate(reversed(parts[:-1]), start=1):
            secs += float(p) * (60 ** i)
        return secs
    except ValueError:
        raise SystemExit(f"cannot parse chapter offset {v!r}")


# YouTube silently disables chapters -- all of them, with no warning anywhere
# in Studio -- unless every one of these holds.
MIN_CHAPTERS = 3
MIN_CHAPTER_LEN = 10.0


def build_chapters(spec, root, runtime_hint=None):
    """Chapter offsets, either measured from clips or given explicitly.

    Two shapes are supported because two shapes exist in practice:

    * A video assembled from per-segment files -- give each chapter a `file`
      and the offset is the sum of the durations before it, so re-snapping a
      cut cannot leave the description lying.
    * A single rendered film -- give each chapter an `at`. Deriving offsets
      from anything other than the finished render is guesswork, so these are
      validated against the real duration rather than trusted.
    """
    explicit = any("at" in ch for ch in spec.get("chapters", []))
    lines, t = [], 0.0

    if explicit:
        marks = []
        for ch in spec.get("chapters", []):
            if "at" not in ch:
                raise SystemExit(
                    "mixed chapter styles: give every chapter an `at`, or none")
            marks.append((parse_at(ch["at"]), ch))
        marks.sort(key=lambda m: m[0])
        # The first chapter must start at 0:00 or YouTube ignores the lot.
        if marks and marks[0][0] > 0:
            marks[0] = (0.0, marks[0][1])
        for at, ch in marks:
            label = ch["label"]
            if ch.get("gloss"):
                label = f"{label} | {ch['gloss']}"
            lines.append(f"{mmss(at)} {label}")
        t = runtime_hint or (marks[-1][0] if marks else 0.0)
        _check_chapters([m[0] for m in marks], t)
        return "\n".join(lines), t

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


def _check_chapters(marks, runtime):
    problems = []
    if len(marks) < MIN_CHAPTERS:
        problems.append(f"{len(marks)} chapters, YouTube needs {MIN_CHAPTERS}")
    if marks and marks[0] != 0:
        problems.append("first chapter is not 0:00")
    for a, b in zip(marks, marks[1:]):
        if b - a < MIN_CHAPTER_LEN:
            problems.append(
                f"{mmss(a)}->{mmss(b)} is {b - a:.0f}s, minimum is "
                f"{MIN_CHAPTER_LEN:.0f}s")
    if runtime and marks and marks[-1] > runtime - MIN_CHAPTER_LEN:
        problems.append(f"last chapter {mmss(marks[-1])} is within "
                        f"{MIN_CHAPTER_LEN:.0f}s of the end ({mmss(runtime)})")
    if problems:
        raise SystemExit("chapters rejected: " + "; ".join(problems))


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


def build(spec, root, runtime_hint=None):
    chapters, runtime = build_chapters(spec, root, runtime_hint)
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
    # A factual film usually rests on many sources, and for a sensitive
    # subject the provenance is part of the work rather than a footnote.
    # Listing them is also the cheapest defence against a good-faith dispute
    # in the comments.
    srcs = spec.get("sources") or []
    if srcs:
        parts.append(spec.get("sources_heading", "Sources"))
        for s in srcs:
            name = s.get("name", "").strip()
            url = s.get("url", "").strip()
            parts.append(f"{name} — {url}" if url else name)
        parts.append("")
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
        "category": spec.get("category", CATEGORY_LABEL.get(
            str(spec.get("category_id", "25")), "News & Politics")),
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

    # For an explicitly-timed single file, the real runtime is the only thing
    # that can prove the last chapter is not past the end of the video.
    hint = None
    if os.path.exists(pub.video):
        hint = duration(pub.video)

    meta, info = build(spec, pub.root, hint)
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
