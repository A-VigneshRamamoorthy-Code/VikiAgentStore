#!/usr/bin/env python3
"""
Uploads the episode to YouTube by driving studio.youtube.com with Playwright.

This deliberately does NOT use the YouTube Data API. The Data API route needs a
Google Cloud OAuth app that is either published or has the uploader listed as a
test user, and that console flow is currently wedged ("OAuth configuration is
incomplete", Publish disabled, test-user Save inert). Driving Studio in a
browser that is already signed in sidesteps the app entirely -- this is the same
method that worked in earlier sessions.

Stages:
  recon   -- report which channel the signed-in profile lands on
  upload  -- run the full upload wizard, leaving the video PRIVATE

The video is left PRIVATE on purpose; the user publishes manually.
"""
import argparse
import json
import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

from config import Publish, check_limits

STUDIO = "https://studio.youtube.com/"

# Set by main() from the project's publish.json. Everything channel-specific
# lives there so this uploader is reusable by any video and any channel.
P = None


def _paths():
    return P.profile, P.p("meta"), P.video, P.thumbnail, P.metafile


def want_handle():
    """The channel handle the project insists on, lowercased and bare."""
    return (P.get("channel", "handle", default="") or "").lstrip("@").lower()


def assert_channel(page, action):
    """Refuse to touch the wrong channel.

    A Google login usually owns several brand accounts, and Studio silently
    lands on whichever was last active. Uploading a finished episode to a
    lookalike channel is not recoverable by editing, so this is a hard stop.
    """
    name = channel_name(page)
    say(f"channel: {name}")
    want = want_handle()
    if not want:
        say("! no channel.handle configured -- skipping channel check")
        return name
    if want.replace(" ", "") not in name.lower().replace(" ", ""):
        raise RuntimeError(
            f"refusing to {action}: active channel is {name!r}, "
            f"expected handle @{want}")
    return name

# Studio hides real controls behind Polymer overlays; these swallow clicks.
OVERLAYS = (
    "tp-yt-iron-overlay-backdrop",
    ".glue-cookie-notification-bar",
    "[id^=glue-cookie-notification-bar]",
    "tp-yt-paper-dialog-scrollable + .backdrop",
)


def say(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def shot(page, name):
    try:
        page.screenshot(path=P.p("meta", f"yt_{name}.png"), full_page=False)
    except Exception:
        pass


def kill_overlays(page):
    """Remove click-eating overlays. This was the single biggest time sink."""
    try:
        page.evaluate(
            "(sels) => sels.forEach(s => document.querySelectorAll(s)"
            ".forEach(e => e.remove()))",
            list(OVERLAYS),
        )
    except Exception:
        pass


def settle(page, t=30000):
    try:
        page.wait_for_load_state("networkidle", timeout=t)
    except Exception:
        pass
    time.sleep(2.0)
    kill_overlays(page)


def visible_enabled(el):
    try:
        return el.is_visible() and el.is_enabled()
    except Exception:
        return False


def click_sel(page, selector, what, timeout=60000, required=True):
    """Click the visible+enabled match for a CSS selector, last-first."""
    deadline = time.time() + timeout / 1000.0
    while time.time() < deadline:
        kill_overlays(page)
        loc = page.locator(selector)
        n = loc.count()
        for i in range(n - 1, -1, -1):
            el = loc.nth(i)
            if visible_enabled(el):
                try:
                    el.scroll_into_view_if_needed(timeout=4000)
                except Exception:
                    pass
                kill_overlays(page)
                try:
                    el.click(timeout=8000)
                    say(f"clicked {what}")
                    return True
                except Exception:
                    try:
                        el.evaluate("e => e.click()")
                        say(f"clicked {what} (js)")
                        return True
                    except Exception:
                        pass
        time.sleep(1.5)
    if required:
        raise RuntimeError(f"could not click {what} ({selector})")
    say(f"skipped {what} (not found)")
    return False


def fill_box(page, container_sel, text, what):
    """Studio's title/description are contenteditable divs, not inputs."""
    kill_overlays(page)
    box = page.locator(f"{container_sel} #textbox")
    box.first.wait_for(state="visible", timeout=60000)
    el = box.first
    el.click()
    time.sleep(0.4)
    # Clear whatever Studio prefilled (it seeds title from the filename).
    page.keyboard.press("Meta+A")
    time.sleep(0.2)
    page.keyboard.press("Backspace")
    time.sleep(0.4)
    el.type(text, delay=6)
    time.sleep(0.8)
    got = el.inner_text().strip()
    say(f"{what}: {len(got)} chars set")
    return got


def launch(pw):
    return pw.chromium.launch_persistent_context(
        P.profile,
        channel="chrome",
        headless=False,
        accept_downloads=True,
        viewport={"width": 1500, "height": 950},
        args=["--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation"],
    )


def studio_url():
    """Pin Studio to the resolved channel so an upload can never land on a
    decoy channel ('Politainment Re-defined' / 'Politainment Gamer')."""
    try:
        cid = json.load(open(P.p("meta", "channel.json")))["channel_id"]
        return f"https://studio.youtube.com/channel/{cid}"
    except Exception:
        return STUDIO


def open_studio(ctx):
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(studio_url(), wait_until="domcontentloaded", timeout=90000)
    settle(page)
    return page


def channel_name(page):
    for sel in ("#entity-name", "ytcp-header #channel-name", "#channel-title"):
        try:
            el = page.locator(sel).first
            if el.count() and el.is_visible():
                t = el.inner_text().strip()
                if t:
                    return t
        except Exception:
            pass
    return "(unknown)"


def recon(ctx):
    page = open_studio(ctx)
    say(f"url: {page.url}")
    say(f"channel: {channel_name(page)}")
    shot(page, "recon")
    txt = page.inner_text("body")[:1500]
    print("=== STUDIO ===")
    print(txt)


def switch(ctx, handle=None):
    """Activate the brand account whose handle matches EXACTLY.

    Necessary because the login also owns 'Politainment Re-defined' and
    A login commonly owns several brand accounts with near-identical names
    (e.g. 'X', 'X Re-defined', 'X Gamer'). Substring matching picks the wrong
    one, so the handle is compared exactly.
    """
    handle = handle or "@" + want_handle()
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://www.youtube.com/channel_switcher",
              wait_until="domcontentloaded", timeout=90000)
    settle(page)

    links = page.locator("ytd-account-item-renderer")
    target = None
    for i in range(links.count()):
        el = links.nth(i)
        try:
            if not el.is_visible():
                continue
            lines = [x.strip() for x in el.inner_text().splitlines()]
        except Exception:
            continue
        if handle in lines:
            target = el
            say(f"matched: {' / '.join(x for x in lines if x)}")
            break
    if target is None:
        raise RuntimeError(f"no channel with handle exactly {handle}")

    kill_overlays(page)
    target.click()
    time.sleep(6)
    settle(page)

    page.goto(STUDIO, wait_until="domcontentloaded", timeout=90000)
    settle(page)
    name = channel_name(page)
    m = re.search(r"/channel/(UC[\w-]+)", page.url)
    cid = m.group(1) if m else ""
    say(f"active channel: {name}  id={cid}")
    shot(page, "switched")
    if cid:
        with open(P.p("meta", "channel.json"), "w") as f:
            json.dump({"handle": handle, "name": name, "channel_id": cid}, f, indent=2)
        say("wrote meta/channel.json")
    return cid


def verify(ctx):
    """Confirm the uploaded video's channel, privacy and metadata."""
    res = json.load(open(P.p("meta", "upload_result.json")))
    vid = res["link"].rsplit("/", 1)[-1]
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(f"{studio_url()}/videos/upload", wait_until="domcontentloaded",
              timeout=90000)
    settle(page)
    say(f"channel: {channel_name(page)}")
    shot(page, "7_list")

    page.goto(f"https://studio.youtube.com/video/{vid}/edit",
              wait_until="domcontentloaded", timeout=90000)
    settle(page)
    shot(page, "8_edit")
    body = page.inner_text("body")
    for probe in ("Private", "Visibility", "1080p", "Processing"):
        say(f"{probe}: {'yes' if probe.lower() in body.lower() else 'no'}")
    print("=== EDIT PAGE ===")
    print(body[:1800])


def channels(ctx):
    """List every channel/brand account reachable from this login."""
    handle = handle or "@" + want_handle()
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://www.youtube.com/channel_switcher",
              wait_until="domcontentloaded", timeout=90000)
    settle(page)
    shot(page, "switcher")
    say(f"url: {page.url}")
    print("=== CHANNEL SWITCHER ===")
    print(page.inner_text("body")[:2500])


def upload(ctx):
    meta = P.load_meta()
    title = meta["title"]
    desc = meta["description"]
    tags = meta.get("tags", [])

    for p in (P.video, P.thumbnail):
        if not os.path.exists(p):
            raise SystemExit(f"missing {p}")

    page = open_studio(ctx)
    assert_channel(page, "upload")

    # --- open the upload dialog -------------------------------------------
    # Going straight to the upload URL is far more reliable than hunting the
    # Create button, whose Polymer id changes between Studio revisions.
    page.goto(f"{studio_url()}/videos/upload?d=ud",
              wait_until="domcontentloaded", timeout=90000)
    settle(page)
    shot(page, "0_dialog")

    # --- attach the file ---------------------------------------------------
    fi = page.locator("input[type=file]").first
    fi.wait_for(state="attached", timeout=60000)
    fi.set_input_files(P.video)
    say(f"attached {os.path.basename(P.video)} "
        f"({os.path.getsize(P.video)/1e6:.0f} MB) -- uploading in background")
    time.sleep(8)
    shot(page, "1_attached")

    # --- details -----------------------------------------------------------
    fill_box(page, "#title-textarea", title, "title")
    fill_box(page, "#description-textarea", desc, "description")
    shot(page, "2_details")

    # thumbnail
    try:
        tin = page.locator("#file-loader, input[type=file]#file-loader").first
        tin.wait_for(state="attached", timeout=20000)
        tin.set_input_files(P.thumbnail)
        say("thumbnail attached")
        time.sleep(4)
    except Exception as e:
        say(f"thumbnail step skipped: {e}")

    # not made for kids
    click_sel(
        page,
        "tp-yt-paper-radio-button[name=VIDEO_MADE_FOR_KIDS_NOT_MFK]",
        "Not made for kids",
        required=False,
    )

    # tags live under "Show more"
    click_sel(page, "ytcp-button#toggle-button", "Show more", required=False)
    time.sleep(2)
    ti = clear_tags(page)
    if ti is not None:
        try:
            ti.click()
            ti.type(",".join(tags)[:480] + ",", delay=4)
            say(f"tags: {len(tags)} entered")
        except Exception as e:
            say(f"tags skipped: {e}")
    shot(page, "3_more")

    # --- next x3 -----------------------------------------------------------
    for i in range(3):
        click_sel(page, "ytcp-button#next-button", f"Next {i+1}/3")
        time.sleep(2.5)
    shot(page, "4_visibility")

    # --- keep it PRIVATE ---------------------------------------------------
    click_sel(page, "tp-yt-paper-radio-button[name=PRIVATE]", "Private")
    time.sleep(1.5)
    shot(page, "5_private")

    # --- wait for processing to allow Done ---------------------------------
    for _ in range(120):
        kill_overlays(page)
        try:
            t = page.locator("ytcp-video-upload-progress, .progress-label").first
            if t.count():
                say(f"progress: {t.inner_text().strip()[:80]}")
        except Exception:
            pass
        done = page.locator("ytcp-button#done-button")
        if done.count() and visible_enabled(done.first):
            break
        time.sleep(5)

    click_sel(page, "ytcp-button#done-button", "Done", timeout=120000)
    time.sleep(6)
    shot(page, "6_done")

    # --- capture the link --------------------------------------------------
    link = ""
    for sel in ("a[href*='youtu.be']", "#share-url", "a[href*='watch?v=']"):
        try:
            el = page.locator(sel).first
            if el.count():
                link = (el.get_attribute("href") or el.inner_text() or "").strip()
                if link:
                    break
        except Exception:
            pass
    if not link:
        m = re.search(r"(https://youtu\.be/[\w-]+)", page.inner_text("body"))
        if m:
            link = m.group(1)

    say(f"link: {link or '(not captured)'}")
    out = {
        "method": "studio.youtube.com via Playwright (no Data API)",
        "video": P.video,
        "title": title,
        "privacyStatus": "private",
        "link": link,
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(P.p("meta", "upload_result.json"), "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    say("wrote meta/upload_result.json")
    return link


def clear_tags(page):
    """Empty the tags field.

    Tags are chips, not text, so Cmd/Ctrl+A + Backspace does nothing -- new
    tags simply get appended, which blows the 500-char cap and leaves Studio
    refusing to save. Worse, without a trailing comma the last surviving chip
    fuses with the first new one into a corrupt tag.

    Three strategies, most reliable first: the field's clear-all button, then
    per-chip delete icons, then Backspace (which only selects-then-deletes and
    loses focus easily).
    """
    box = "#tags-container"
    try:
        page.locator(f"{box} input, input[aria-label='Tags']").first.wait_for(
            state="visible", timeout=20000)
    except Exception as e:
        say(f"tag field not found: {e}")
        return None

    def chips():
        return page.locator(f"{box} ytcp-chip").count()

    for sel in (f"{box} ytcp-icon-button[aria-label*='Clear' i]",
                f"{box} #clear-button",
                f"{box} ytcp-icon-button:last-of-type"):
        if chips() == 0:
            break
        try:
            el = page.locator(sel).first
            if el.count():
                el.click(timeout=5000)
                time.sleep(1.2)
        except Exception:
            pass

    for _ in range(80):
        if chips() == 0:
            break
        try:
            page.locator(f"{box} ytcp-chip ytcp-icon-button").last.click(
                timeout=3000)
            time.sleep(0.15)
        except Exception:
            break

    ti = page.locator(f"{box} input, input[aria-label='Tags']").first
    if chips():
        ti.click()
        page.keyboard.press("End")
        for _ in range(240):
            if chips() == 0:
                break
            page.keyboard.press("Backspace")
            time.sleep(0.05)

    say(f"tags cleared, {chips()} chip(s) remaining")
    return ti


def edit(ctx, vid=None):
    """Re-apply title/description/tags to an already-uploaded video.

    Cheaper and tidier than deleting and re-uploading when only the metadata
    was wrong -- the 141 MB transfer and processing wait are skipped, and the
    channel does not accumulate abandoned private duplicates.
    """
    meta = P.load_meta()
    if vid is None:
        res = json.load(open(P.p("meta", "upload_result.json")))
        vid = res["link"].rsplit("/", 1)[-1]

    page = open_studio(ctx)
    assert_channel(page, "edit")

    # The video edit page is addressed directly, NOT under /channel/<id> --
    # studio_url() prefixed that way returns "Oops, something went wrong".
    page.goto(f"https://studio.youtube.com/video/{vid}/edit",
              wait_until="domcontentloaded", timeout=90000)
    settle(page)
    time.sleep(4)
    shot(page, "e0_edit")

    fill_box(page, "#title-textarea", meta["title"], "title")
    fill_box(page, "#description-textarea", meta["description"], "description")

    click_sel(page, "ytcp-button#toggle-button", "Show more", required=False)
    time.sleep(2)
    tags = meta.get("tags", [])
    ti = clear_tags(page)
    if ti is not None:
        try:
            ti.click()
            ti.type(",".join(tags)[:480] + ",", delay=4)
            say(f"tags: {len(tags)} entered")
        except Exception as e:
            say(f"tags skipped: {e}")
    shot(page, "e1_filled")

    click_sel(page, "ytcp-button#save", "Save", timeout=90000)
    time.sleep(8)
    shot(page, "e2_saved")
    body = page.inner_text("body")
    if "until errors are resolved" in body.lower():
        raise RuntimeError("Studio refused the save; see meta/yt_e2_saved.png")
    say(f"saved: {'confirmed' if 'saved' in body.lower() else 'no error shown'}")
    return vid


def main():
    global P
    ap = argparse.ArgumentParser(
        description="Publish a video to YouTube via Studio automation")
    ap.add_argument("stage",
                    choices=["recon", "channels", "switch", "upload", "edit",
                             "verify"])
    ap.add_argument("project", help="directory containing publish.json")
    ap.add_argument("--video", default=None, help="video id for `edit`")
    a = ap.parse_args()

    P = Publish(a.project)
    os.makedirs(P.p("meta"), exist_ok=True)
    if a.stage in ("upload", "edit"):
        problems = check_limits(P.load_meta())
        if problems:
            raise SystemExit("metadata rejected: " + "; ".join(problems))

    with sync_playwright() as pw:
        ctx = launch(pw)
        try:
            if a.stage == "recon":
                recon(ctx)
            elif a.stage == "channels":
                channels(ctx)
            elif a.stage == "switch":
                switch(ctx)
            elif a.stage == "verify":
                verify(ctx)
            elif a.stage == "edit":
                edit(ctx, a.video)
            else:
                upload(ctx)
        finally:
            time.sleep(2)
            ctx.close()  # never SIGKILL: that wipes the signed-in session


if __name__ == "__main__":
    main()
