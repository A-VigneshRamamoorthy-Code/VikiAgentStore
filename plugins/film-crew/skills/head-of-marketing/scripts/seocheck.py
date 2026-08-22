"""Lint YouTube metadata before it is uploaded.

Catches the mistakes that are invisible until the video is already live: a
description that never repeats the title's keywords, tags that blow the 500
character cap (Studio reports this only as "Cannot save until errors are
resolved"), a single-language description on a video with a bilingual
audience, and a missing 0:00 chapter, which silently disables chapter markers.

    python3 seocheck.py <project>

Exits non-zero if any hard rule fails, so it can gate an upload.
"""
import argparse
import re
import sys

import _shared  # noqa: F401  (locates config.py)
from config import LIMITS, Publish, check_limits


def has_second_script(text):
    """True if the text carries a non-Latin script alongside Latin.

    A crude but reliable proxy for "this description is bilingual": Tamil,
    Devanagari, Telugu, Kannada, Malayalam, Bengali, Arabic, CJK, Cyrillic.
    """
    return bool(re.search(
        r"[\u0900-\u097F\u0980-\u09FF\u0B80-\u0BFF\u0C00-\u0C7F"
        r"\u0C80-\u0CFF\u0D00-\u0D7F\u0600-\u06FF\u0400-\u04FF"
        r"\u4E00-\u9FFF\u3040-\u30FF]", text))


def has_latin_words(text):
    return len(re.findall(r"\b[A-Za-z]{4,}\b", text)) >= 8


def keywords(title):
    stop = {"the", "and", "for", "with", "from", "that", "this", "what",
            "when", "your", "into", "over", "full", "live"}
    return [w.lower() for w in re.findall(r"\b[A-Za-z]{4,}\b", title)
            if w.lower() not in stop]


def audit(meta):
    """Returns (errors, warnings). Errors block the upload."""
    errors = list(check_limits(meta))
    warns = []

    title = meta.get("title", "")
    desc = meta.get("description", "")
    tags = meta.get("tags", [])
    low_desc = desc.lower()

    if len(title) < 30:
        warns.append(f"title is only {len(title)} chars -- room for more "
                     "searchable keywords")
    if len(desc) < 250:
        warns.append(f"description is only {len(desc)} chars; the first 150 "
                     "show in search, the rest still gets indexed")
    if not tags:
        warns.append("no tags")

    # The first two lines are what search and the collapsed panel show.
    first = "\n".join(desc.splitlines()[:2]).lower()
    missing = [k for k in keywords(title)[:5] if k not in first]
    if missing:
        warns.append("title keywords absent from the opening lines: "
                     + ", ".join(missing))

    if "0:00" not in desc and re.search(r"\b\d+:\d{2}\b", desc):
        errors.append("timestamps present but none at 0:00 -- YouTube will "
                      "not render chapters")

    bilingual = has_second_script(desc)
    if bilingual and not has_latin_words(desc):
        warns.append("description is non-Latin only; viewers searching in "
                     "English will never reach this video")
    if bilingual and not any(re.search(r"[A-Za-z]{4,}", t) for t in tags):
        warns.append("no Latin-script tags on a non-Latin video")

    for t in tags:
        if len(t) > 60:
            warns.append(f"tag longer than 60 chars: {t[:40]}...")

    return errors, warns


def main():
    ap = argparse.ArgumentParser(description="Lint YouTube metadata")
    ap.add_argument("project")
    a = ap.parse_args()

    meta = Publish(a.project).load_meta()
    errors, warns = audit(meta)

    tag_chars = sum(len(t) for t in meta.get("tags", [])) + \
        max(0, len(meta.get("tags", [])) - 1)
    print(f"title       {len(meta.get('title',''))}/{LIMITS['title']}")
    print(f"description {len(meta.get('description',''))}/"
          f"{LIMITS['description']}")
    print(f"tags        {tag_chars}/{LIMITS['tags_total']} "
          f"({len(meta.get('tags', []))} tags)")

    for w in warns:
        print(f"  warn  {w}")
    for e in errors:
        print(f"  FAIL  {e}")
    if errors:
        sys.exit(1)
    print("ok" if not warns else "ok with warnings")


if __name__ == "__main__":
    main()
