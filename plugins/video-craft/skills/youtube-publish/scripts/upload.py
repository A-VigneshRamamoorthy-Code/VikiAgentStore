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
import io
import json
import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

from config import Publish, check_limits

STUDIO = "https://studio.youtube.com/"


class TrustWall(RuntimeError):
    """Raised when a feature is locked behind YouTube's channel verification.

    Not a bug and not retryable: it needs a human with a camera or an ID.
    """


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


def fill_box(page, container_sel, text, what, tries=2):
    """Studio's title/description are contenteditable divs, not inputs.

    Typing character by character means holding focus for the whole string --
    about half a minute for a full description -- and Studio will happily
    steal focus mid-way when an upload toast or a checks panel appears,
    leaving a truncated description that looks plausible. `insert_text` puts
    the whole string in with one CDP call, so there is no window to lose. The
    result is read back and retried, because a silently short description is
    worse than a loud failure.
    """
    for attempt in range(1, tries + 1):
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
        try:
            page.keyboard.insert_text(text)
        except Exception:
            el.type(text, delay=4)
        time.sleep(1.0)
        got = el.inner_text().strip()
        # Studio normalises whitespace, so compare on length with slack
        # rather than demanding an exact match.
        if len(got) >= len(text.strip()) * 0.97:
            say(f"{what}: {len(got)} chars set")
            return got
        say(f"{what}: got {len(got)}/{len(text)} chars "
            f"(attempt {attempt}) -- retrying")
    raise SystemExit(f"could not set {what} reliably")


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


def login(ctx, minutes=20):
    """Interactive sign-in for a fresh profile.

    The persistent profile is the only credential this skill has, and a new
    profile has none. Every other stage assumes that session already exists,
    so without this the first run against a new channel fails at `recon` with
    nothing to do about it. Google also blocks sign-in inside an obviously
    automated browser, which is why the context is launched non-headless with
    the automation flags stripped -- the human completes the login by hand,
    including any 2FA, and the profile keeps it from then on.

    Blocks until Studio reports a channel, then records it.
    """
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(STUDIO, wait_until="domcontentloaded", timeout=90000)
    say("A Chrome window is open.")
    say("Sign in to the Google account that owns the target channel,")
    say("and if it is a brand account, switch to it.")
    say(f"Waiting up to {minutes} min -- do not close the window.")

    deadline = time.time() + minutes * 60
    last = ""
    while time.time() < deadline:
        # Scan every tab, not just the first. Google's sign-in frequently
        # finishes in a new tab or popup, and watching only ctx.pages[0]
        # leaves this polling a stale about:blank forever while the profile
        # is in fact signed in.
        for pg in list(ctx.pages):
            try:
                url = pg.url
            except Exception:
                continue
            if url != last:
                last = url
                say(f"url: {url[:90]}")
            if "accounts.google" in url or "signin" in url:
                continue
            m = re.search(r"/channel/(UC[\w-]+)", url)
            cid = m.group(1) if m else ""
            if cid or "studio.youtube.com" in url:
                try:
                    settle(pg)
                    name = channel_name(pg)
                    if not cid:
                        m2 = re.search(r"/channel/(UC[\w-]+)", pg.url)
                        cid = m2.group(1) if m2 else ""
                except Exception:
                    continue
                if not cid:
                    continue
                say(f"signed in: {name}  id={cid}")
                with open(P.p("meta", "channel.json"), "w") as f:
                    json.dump({"handle": "@" + want_handle(), "name": name,
                               "channel_id": cid}, f, indent=2)
                say("wrote meta/channel.json")
                shot(pg, "login")
                return cid
        time.sleep(3)
    raise SystemExit("timed out waiting for sign-in")


def _branding_input(page, tag, want, other):
    """The file input belonging to a named branding section.

    All three inputs on this page share `id=file-selector`, so positional
    index is the only thing telling them apart -- and index order is exactly
    what silently changes when YouTube reshuffles the page, which would put
    the banner into the avatar slot with no error at all.

    Each upload widget is its own custom element, so that is the primary
    match, and Playwright's CSS engine pierces the shadow roots they live in.
    The text walk below is a fallback for when those tags get renamed.
    """
    el = page.locator(f"{tag} input[type=file]").first
    try:
        if el.count():
            return el
    except Exception:
        pass

    inputs = page.locator("input[type=file]#file-selector")
    for i in range(inputs.count()):
        el = inputs.nth(i)
        try:
            hit = el.evaluate(
                """(el, names) => {
                    const [w, o] = names;
                    let n = el;
                    for (let k = 0; k < 20 && n; k++) {
                        // Studio is Polymer: parentElement returns null at a
                        // shadow boundary, so hop to the host to keep going.
                        const root = n.getRootNode();
                        n = n.parentElement ||
                            (root && root.host ? root.host : null);
                        if (!n) break;
                        const t = n.innerText || '';
                        if (t.includes(w) && !t.includes(o)) return true;
                    }
                    return false;
                }""", [want, other])
        except Exception:
            hit = False
        if hit:
            return el
    return None

def _confirm_crop(page):
    """Dismiss the crop/preview dialog YouTube shows after picking an image."""
    for sel in ("ytcp-button#done-button",
                "ytcp-button[label='Done']",
                "tp-yt-paper-dialog ytcp-button#save-button"):
        if click_sel(page, sel, "Done (crop)", timeout=12000, required=False):
            time.sleep(2)
            return True
    # Fall back to matching on the label, which survives id churn.
    try:
        btn = page.get_by_role("button", name=re.compile(r"^(Done|Save)$"))
        if btn.count() and visible_enabled(btn.first):
            btn.first.click(timeout=8000)
            say("clicked Done (crop, by role)")
            time.sleep(2)
            return True
    except Exception:
        pass
    say("no crop dialog appeared")
    return False


def branding(ctx):
    """Set the channel icon and banner, then publish the change.

    A brand new channel shows a letter avatar and an empty grey banner, which
    reads as abandoned before a single video plays. This is the one part of
    launching a channel that cannot be done from the upload wizard.
    """
    icon = P.p("out", "channel_icon.png")
    banner = P.p("out", "channel_banner.jpg")
    for p in (icon, banner):
        if not os.path.exists(p):
            raise SystemExit(f"missing {p} -- run brand.py first")
    # Caps are enforced here rather than by Studio, which rejects an oversized
    # image with a toast that disappears before you can read it.
    if os.path.getsize(banner) > 6 * 1024 * 1024:
        raise SystemExit(f"banner is {os.path.getsize(banner)/1e6:.1f} MB, cap is 6 MB")
    if os.path.getsize(icon) > 4 * 1024 * 1024:
        raise SystemExit(f"icon is {os.path.getsize(icon)/1e6:.1f} MB, cap is 4 MB")

    page = open_studio(ctx)
    assert_channel(page, "change branding")
    cid = json.load(open(P.p("meta", "channel.json")))["channel_id"]

    page.goto(f"https://studio.youtube.com/channel/{cid}/editing/images",
              wait_until="domcontentloaded", timeout=90000)
    settle(page)
    time.sleep(3)
    shot(page, "b0_branding")

    for tag, label, other, path in (
            ("ytcp-banner-upload", "Banner image", "Picture", banner),
            ("ytcp-profile-image-upload", "Picture", "Banner image", icon)):
        el = _branding_input(page, tag, label, other)
        if el is None:
            raise RuntimeError(f"could not find the file input for {label!r}")
        el.set_input_files(path)
        say(f"{label}: attached {os.path.basename(path)} "
            f"({os.path.getsize(path)/1024:.0f} KB)")
        time.sleep(4)
        _confirm_crop(page)
        settle(page)
        shot(page, f"b1_{label.split()[0].lower()}")

    click_sel(page, "ytcp-button#publish-button", "Publish", timeout=60000)
    time.sleep(8)
    settle(page)
    shot(page, "b2_published")
    body = page.inner_text("body")
    say("published" if "publish" not in body.lower()[:200] else "publish clicked")
    return True


def channels(ctx):
    """List every channel/brand account reachable from this login."""
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://www.youtube.com/channel_switcher",
              wait_until="domcontentloaded", timeout=90000)
    settle(page)
    shot(page, "switcher")
    say(f"url: {page.url}")
    rows = page.locator("ytd-account-item-renderer")
    found = []
    for i in range(rows.count()):
        el = rows.nth(i)
        try:
            if not el.is_visible():
                continue
            lines = [x.strip() for x in el.inner_text().splitlines() if x.strip()]
        except Exception:
            continue
        if lines:
            found.append(lines)
    print("=== CHANNELS ===")
    for lines in found:
        handle = next((x for x in lines if x.startswith("@")), "(no handle)")
        print(f"  {lines[0]:<40} {handle}")
    if not found:
        print(page.inner_text("body")[:2500])
    return found


def _upload_dialog_ready(page):
    """True once the file picker is really on screen.

    `input[type=file]` alone is not proof: Studio keeps a detached uploads
    dialog in the DOM on other pages, so waiting on the input can pass on a
    page that will never accept a file.
    """
    try:
        if page.locator("ytcp-uploads-file-picker").first.is_visible():
            return True
    except Exception:
        pass
    try:
        return page.locator("ytcp-uploads-dialog").first.is_visible()
    except Exception:
        return False


def _open_upload_dialog(page, tries=3):
    """Get the upload dialog open, however Studio feels like behaving.

    The `?d=ud` deep link is still the most direct route, but it only holds
    when it is the navigation that lands -- arriving from the dashboard, the
    SPA router will happily bounce straight back to the dashboard and leave
    you on a page with no picker. So: navigate, check, and fall back to the
    dashboard's own "Upload videos" button before giving up.
    """
    url = f"{studio_url()}/videos/upload?d=ud"
    for attempt in range(1, tries + 1):
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        settle(page)
        if _upload_dialog_ready(page):
            return
        say(f"upload dialog did not open (attempt {attempt}) -- "
            "trying the dashboard button")
        # The dashboard's own upload control. Studio has renamed this more
        # than once (#upload-videos-button is long gone); match on the aria
        # label too, which has outlived every id.
        for sel in ("ytcp-icon-button#upload-icon",
                    "#upload-icon",
                    "button[aria-label='Upload videos']",
                    "ytcp-button#upload-videos-button"):
            try:
                page.locator(sel).first.click(timeout=5000)
                settle(page)
                if _upload_dialog_ready(page):
                    return
            except Exception:
                pass
        # Last resort: the header Create menu. Note the aria label sits on the
        # inner <button>, not on the ytcp-button wrapper.
        try:
            page.locator("button[aria-label='Create']").first.click(
                timeout=5000)
            time.sleep(1.5)
            page.get_by_text("Upload videos", exact=True).first.click(
                timeout=5000)
            settle(page)
            if _upload_dialog_ready(page):
                return
        except Exception:
            pass
    shot(page, "0_no_dialog")
    raise SystemExit(
        "could not open the upload dialog -- see meta/yt_0_no_dialog.png")


def _progress_text(page):
    for sel in ("ytcp-video-upload-progress", ".progress-label"):
        try:
            el = page.locator(sel).first
            if el.count():
                t = el.inner_text().strip()
                if t:
                    return t
        except Exception:
            pass
    return ""


def _wait_for_transfer(page, minutes=120):
    """Block until the bytes are actually on YouTube.

    This is the single most expensive thing to get wrong here. Studio enables
    Done, and reports the video as "saved", while the file is still going up:
    the dialog is only a form, and the transfer continues in the background of
    *that browser tab*. Closing the browser then abandons the upload and
    leaves a draft frozen at whatever percent it reached -- with perfect
    metadata, which is what makes it so convincing. Twice.

    So wait on the progress label, not on the button. "Uploading ..." becomes
    "Upload complete" / "Processing ..." only once the transfer is done.
    """
    deadline = time.time() + minutes * 60
    last, quiet = "", 0
    while time.time() < deadline:
        kill_overlays(page)
        txt = _progress_text(page)
        if txt and txt != last:
            say(f"progress: {txt[:90]}")
            last = txt
        if txt:
            quiet = 0
            if not txt.lower().startswith("uploading"):
                return txt
        else:
            # The label can blink out between states; only treat a long
            # silence as a finished transfer.
            quiet += 1
            if quiet > 12 and last and not last.lower().startswith("uploading"):
                return last
        time.sleep(5)
    raise SystemExit(
        f"upload did not finish within {minutes} minutes (last: {last!r}) -- "
        "the draft on YouTube is incomplete and should be cancelled")


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

    _open_upload_dialog(page)
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

    # --- wait for the file to actually finish going up ---------------------
    _wait_for_transfer(page)

    # --- wait for processing to allow Done ---------------------------------
    for _ in range(120):
        kill_overlays(page)
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
    if not goto_verified(page, f"https://studio.youtube.com/video/{vid}/edit",
                         "#title-textarea #textbox", what="edit page"):
        raise SystemExit(f"could not open the edit page for {vid}")
    time.sleep(2)
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


VISIBILITY_LABEL = {"public": "Public", "unlisted": "Unlisted",
                    "private": "Private"}


def _live_thumbnail_matches(vid, path, tol=8.0):
    """Compare YouTube's served poster with the file we uploaded.

    Studio's own edit page is not proof -- it renders the pending selection.
    The CDN is, provided the request is cache-busted, because that is exactly
    what a viewer sees. Returns None if the comparison could not be made.
    """
    try:
        import urllib.request
        from PIL import Image
        import numpy as np
    except Exception:
        return None
    url = (f"https://i.ytimg.com/vi/{vid}/maxresdefault.jpg"
           f"?bust={int(time.time())}")
    try:
        req = urllib.request.Request(
            url, headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        live = Image.open(io.BytesIO(data)).convert("RGB").resize((160, 90))
        mine = Image.open(path).convert("RGB").resize((160, 90))
        d = float(np.abs(np.asarray(live, float)
                         - np.asarray(mine, float)).mean())
        say(f"live poster differs from the render by {d:.2f} (0 = identical)")
        return d < tol
    except Exception as e:
        say(f"could not verify the live poster: {str(e)[:70]}")
        return None


def thumbnail(ctx, vid=None):
    """Apply the custom thumbnail to an already-uploaded video, and check it.

    Its own stage because the wizard's thumbnail step fails *silently*: the
    file input accepts `set_input_files`, the log says "thumbnail attached",
    and YouTube quietly serves an auto-generated frame instead. The only
    honest confirmation is to read the poster back off the CDN afterwards.
    """
    if vid is None:
        res = json.load(open(P.p("meta", "upload_result.json")))
        vid = res["link"].rsplit("/", 1)[-1]
    if not os.path.exists(P.thumbnail):
        raise SystemExit(f"missing thumbnail {P.thumbnail}")

    page = open_studio(ctx)
    assert_channel(page, "set the thumbnail")
    tab = fresh_tab(page, f"https://studio.youtube.com/video/{vid}/edit")
    try:
        tab.locator("#title-textarea #textbox").first.wait_for(
            state="visible", timeout=30000)
        kill_overlays(tab)
        fi = tab.locator("ytcp-thumbnail-editor input#file-loader, "
                         "input#file-loader").first
        fi.wait_for(state="attached", timeout=20000)
        fi.set_input_files(P.thumbnail)
        say(f"attached {os.path.basename(P.thumbnail)}")
        time.sleep(6)
        if _trust_wall(tab):
            _dismiss_trust_wall(tab)
            raise TrustWall(
                "custom thumbnails need the one-time channel verification")
        shot(tab, "t0_thumb")
        click_sel(tab, "ytcp-button#save", "Save", timeout=90000)
        time.sleep(8)
        body = tab.inner_text("body")
        if "until errors are resolved" in body.lower():
            raise RuntimeError(
                "Studio refused the save; see meta/yt_t0_thumb.png")
    finally:
        try:
            tab.close()
        except Exception:
            pass

    say("saved -- waiting for the CDN, then verifying")
    ok = None
    for _ in range(6):
        time.sleep(15)
        ok = _live_thumbnail_matches(vid, P.thumbnail)
        if ok:
            break
    if ok:
        say("thumbnail confirmed live")
    elif ok is False:
        say("! the live poster still does not match -- re-run in a minute; "
            "if it never matches, the thumbnail was rejected")
    return vid


def publish(ctx, vid=None, privacy="public"):
    """Flip an uploaded video to its final visibility.

    Deliberately a separate stage from `upload`. Uploading straight to public
    means any mistake -- a truncated description, a wrong thumbnail, a bad
    encode -- is live before anyone has looked at it, and on a sensitive
    subject that is not a recoverable mistake. Upload private, verify, then
    run this.
    """
    if vid is None:
        res = json.load(open(P.p("meta", "upload_result.json")))
        vid = res["link"].rsplit("/", 1)[-1]
    want = VISIBILITY_LABEL[privacy.lower()]

    page = open_studio(ctx)
    assert_channel(page, "publish")
    if not goto_verified(page, f"https://studio.youtube.com/video/{vid}/edit",
                         "#title-textarea #textbox", what="edit page"):
        raise SystemExit(f"could not open the edit page for {vid}")
    time.sleep(2)

    # The sidebar card is <ytcp-video-metadata-visibility>; it carries no id,
    # so the current state's own label is the most stable handle there is.
    opened = False
    for sel in ("ytcp-video-metadata-visibility",
                "ytcp-video-metadata-visibility #dropdown-trigger"):
        try:
            page.locator(sel).first.click(timeout=6000)
            opened = True
            break
        except Exception:
            pass
    if not opened:
        for label in VISIBILITY_LABEL.values():
            try:
                page.get_by_text(label, exact=True).first.click(timeout=4000)
                opened = True
                break
            except Exception:
                pass
    if not opened:
        shot(page, "p0_no_visibility")
        raise SystemExit("could not open the visibility dialog")
    time.sleep(2.5)
    shot(page, "p0_visibility")

    click_sel(page, f"tp-yt-paper-radio-button[name={privacy.upper()}]", want)
    time.sleep(1.5)
    # Two confirmations, and missing the second is silent. The dialog's own
    # button is ytcp-button#save-button but is labelled "Done" -- it only
    # closes the dialog. The page's ytcp-button#save is what actually persists
    # the change; skip it and Studio keeps showing "Undo changes" while the
    # video stays exactly as private as it was.
    click_sel(page, "ytcp-button#save-button", "Done", timeout=60000)
    time.sleep(2.5)
    click_sel(page, "ytcp-button#save", "Save", timeout=60000)
    time.sleep(6)
    shot(page, "p1_saved")

    # Re-load before reading it back: the card reflects the dialog's pending
    # selection, so reading it in place will happily confirm a change that was
    # never saved.
    state = ""
    if goto_verified(page, f"https://studio.youtube.com/video/{vid}/edit",
                     "#title-textarea #textbox", what="edit page"):
        time.sleep(3)
        try:
            state = page.locator(
                "ytcp-video-metadata-visibility").first.inner_text().strip()
        except Exception:
            pass
    say(f"visibility now: {state.replace(chr(10), ' ') or '(unread)'}")
    if want.lower() not in state.lower():
        raise SystemExit(
            f"visibility did not change to {want} (reads {state!r}) -- "
            "see meta/yt_p1_saved.png")
    say(f"live: https://youtu.be/{vid}")
    return vid


def goto_verified(page, url, marker, tries=3, what="page"):
    """Navigate, and confirm we actually landed there.

    Studio is a single-page app with its own router. A navigation issued while
    it is still settling -- for example straight after landing on the
    dashboard -- gets silently rewritten back to the dashboard. The symptom is
    always the same and always misleading: a selector times out, and the
    screenshot shows a perfectly healthy page that simply is not the one you
    asked for.
    """
    for attempt in range(1, tries + 1):
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        settle(page)
        time.sleep(2)
        try:
            page.locator(marker).first.wait_for(state="visible",
                                                timeout=15000)
            return True
        except Exception:
            say(f"{what}: navigation bounced back (attempt {attempt})")
    return False


TRUST_WALL = "get advanced features"


def _trust_wall(page):
    """True if YouTube's one-time channel verification dialog is on screen.

    A brand-new channel sits in the lowest trust tier, where several things
    that look like plain metadata are actually gated: linking a Short to a
    video, and pinning a comment, both raise the same wizard. Clearing it
    needs a 6-second selfie video or a photo ID -- a human, in person. So the
    only correct machine behaviour is to recognise the wall, back out without
    leaving anything half-applied, and say so.
    """
    try:
        for d in page.locator("tp-yt-paper-dialog").all():
            if not d.is_visible():
                continue
            t = (d.inner_text() or "").lower()
            if TRUST_WALL in t or "one-time verification" in t:
                return True
    except Exception:
        pass
    return False


def _dismiss_trust_wall(page):
    for sel in ("ytcp-button#cancel-button",
                "tp-yt-paper-dialog button[aria-label='Cancel']",
                "tp-yt-paper-dialog >> text=Cancel"):
        try:
            page.locator(sel).first.click(timeout=4000)
            time.sleep(1)
            return True
        except Exception:
            pass
    try:
        page.keyboard.press("Escape")
        time.sleep(1)
        return True
    except Exception:
        return False


def _set_related_video(page, short_id, film_id):
    """Point a Short at the long-form video it came from.

    YouTube surfaces this as a "Related video" link on the Short itself, which
    is the only first-class way to send Shorts traffic to a full film. Two
    things gate it: the target must already be public (a private film never
    appears in the picker), and the channel must have cleared the one-time
    verification -- which a new channel has not. Raises TrustWall in that case
    so the caller can fall back rather than pretend it worked.
    """
    tab = fresh_tab(page, f"https://studio.youtube.com/video/{short_id}/edit")
    try:
        try:
            tab.locator("#title-textarea #textbox").first.wait_for(
                state="visible", timeout=30000)
        except Exception:
            shot(tab, f"r_{short_id}_no_edit")
            raise RuntimeError(f"could not open the edit page for {short_id}")
        kill_overlays(tab)

        trig = tab.locator(
            "ytcp-text-dropdown-trigger#linked-video-editor-link").first
        if not trig.count():
            shot(tab, f"r_{short_id}_no_field")
            raise RuntimeError("no Related video field found (Shorts only)")
        trig.scroll_into_view_if_needed(timeout=8000)
        time.sleep(1)
        trig.click(timeout=8000)
        time.sleep(3)

        if _trust_wall(tab):
            _dismiss_trust_wall(tab)
            raise TrustWall(
                "Related video needs the one-time channel verification")

        picked = False
        for sel in (f"[href*='{film_id}']", f"[video-id='{film_id}']",
                    "ytcp-video-picker-row", "tp-yt-paper-item"):
            try:
                el = tab.locator(sel).first
                if el.count():
                    el.click(timeout=6000)
                    picked = True
                    break
            except Exception:
                pass
        if not picked:
            shot(tab, f"r_{short_id}_no_pick")
            raise RuntimeError("could not pick the film in the picker")

        time.sleep(2)
        for sel in ("ytcp-button#save-button", "ytcp-button#save", "#save"):
            try:
                tab.locator(sel).first.click(timeout=6000)
                break
            except Exception:
                pass
        time.sleep(5)
    finally:
        try:
            tab.close()
        except Exception:
            pass


def _load_comments(page, vid):
    """Open a watch page in a fresh tab with the comment section rendered.

    Comments are lazy: they only mount once the section scrolls into view, so
    a bare goto leaves `#simplebox-placeholder` permanently missing and every
    comment action fails for what looks like the wrong reason. Caller closes
    the returned tab.
    """
    tab = fresh_tab(page, f"https://www.youtube.com/watch?v={vid}",
                    settle_extra=4.0)
    for _ in range(10):
        tab.mouse.wheel(0, 800)
        time.sleep(0.8)
        if tab.locator("ytd-comments #simplebox-placeholder").count() or \
                tab.locator("ytd-comment-thread-renderer").count():
            break
    time.sleep(3)
    return tab


def _find_comment(tab, marker):
    """The channel's own top-level comment containing `marker`, or None."""
    threads = tab.locator("ytd-comment-thread-renderer")
    for i in range(min(threads.count(), 20)):
        th = threads.nth(i)
        try:
            if marker in th.inner_text():
                return th
        except Exception:
            pass
    return None


def _comment_film_link(page, vid, text, marker):
    """Post `text` as a comment on `vid`, unless it is already there.

    On an unverified channel this is the only link back to the film that can
    be placed *outside* the description, and on a channel with no other
    comments it is also the top one. Idempotent: re-running will not duplicate.
    """
    tab = _load_comments(page, vid)
    try:
        if _find_comment(tab, marker) is not None:
            say(f"{vid}: film-link comment already present")
            return True
        try:
            tab.locator("#simplebox-placeholder").first.click(timeout=20000)
        except Exception as e:
            say(f"{vid}: comment box unavailable -- {str(e)[:70]}")
            return False
        time.sleep(1.5)
        box = tab.locator("#contenteditable-root").first
        box.click()
        tab.keyboard.insert_text(text)
        time.sleep(1)
        try:
            tab.locator("#submit-button button, "
                        "ytd-button-renderer#submit-button button"
                        ).first.click(timeout=10000)
        except Exception as e:
            say(f"{vid}: could not submit comment -- {str(e)[:70]}")
            return False
        time.sleep(6)
        ok = _find_comment(tab, marker) is not None
        say(f"{vid}: comment {'posted' if ok else 'NOT confirmed'}")
        return ok
    finally:
        try:
            tab.close()
        except Exception:
            pass


def _pin_comment(page, vid, marker):
    """Pin the channel's film-link comment. Raises TrustWall if gated."""
    tab = _load_comments(page, vid)
    try:
        th = _find_comment(tab, marker)
        if th is None:
            raise RuntimeError("no film-link comment to pin")
        if "Pinned by" in th.inner_text():
            say(f"{vid}: already pinned")
            return True
        th.scroll_into_view_if_needed()
        th.hover()
        time.sleep(1.5)
        th.locator("#action-menu button").first.click(timeout=10000)
        time.sleep(2.5)
        pop = tab.locator("ytd-menu-popup-renderer:visible").first
        pop.locator("ytd-menu-navigation-item-renderer",
                    has_text="Pin").first.click(timeout=8000)
        time.sleep(3)
        if _trust_wall(tab):
            _dismiss_trust_wall(tab)
            raise TrustWall("pinning a comment needs the one-time verification")
        for sel in ("yt-confirm-dialog-renderer #confirm-button button",
                    "#confirm-button button"):
            try:
                tab.locator(sel).first.click(timeout=6000)
                break
            except Exception:
                pass
        time.sleep(4)
    finally:
        try:
            tab.close()
        except Exception:
            pass
    check = _load_comments(page, vid)
    try:
        th = _find_comment(check, marker)
        return th is not None and "Pinned by" in th.inner_text()
    finally:
        try:
            check.close()
        except Exception:
            pass


def _upload_one(page, path, title, desc, privacy, tags=None):
    """Upload a single file and return its link.

    Leaner than `upload()`: no thumbnail, no chapters, no tag chips unless
    asked. Used for Shorts, where the whole point is to publish several in a
    row without babysitting each one.
    """
    _open_upload_dialog(page)
    fi = page.locator("input[type=file]").first
    fi.wait_for(state="attached", timeout=60000)
    fi.set_input_files(path)
    say(f"attached {os.path.basename(path)} "
        f"({os.path.getsize(path)/1e6:.0f} MB)")
    time.sleep(6)

    fill_box(page, "#title-textarea", title, "title")
    fill_box(page, "#description-textarea", desc, "description")

    click_sel(
        page,
        "tp-yt-paper-radio-button[name=VIDEO_MADE_FOR_KIDS_NOT_MFK]",
        "Not made for kids", required=False)

    if tags:
        click_sel(page, "ytcp-button#toggle-button", "Show more",
                  required=False)
        time.sleep(1.5)
        ti = clear_tags(page)
        if ti is not None:
            try:
                ti.click()
                ti.type(",".join(tags)[:480] + ",", delay=4)
                say(f"tags: {len(tags)} entered")
            except Exception as e:
                say(f"tags skipped: {e}")

    for i in range(3):
        click_sel(page, "ytcp-button#next-button", f"Next {i+1}/3")
        time.sleep(2.0)

    click_sel(page, f"tp-yt-paper-radio-button[name={privacy.upper()}]",
              privacy.title())
    time.sleep(1.5)

    _wait_for_transfer(page)
    for _ in range(120):
        kill_overlays(page)
        done = page.locator("ytcp-button#done-button")
        if done.count() and visible_enabled(done.first):
            break
        time.sleep(5)
    click_sel(page, "ytcp-button#done-button", "Done", timeout=120000)
    time.sleep(6)

    link = ""
    for sel in ("a[href*='youtu.be']", "#share-url", "a[href*='watch?v=']"):
        try:
            el = page.locator(sel).first
            if el.count():
                link = (el.get_attribute("href")
                        or el.inner_text() or "").strip()
                if link:
                    break
        except Exception:
            pass
    if not link:
        m = re.search(r"(https://youtu\.be/[\w-]+)", page.inner_text("body"))
        if m:
            link = m.group(1)
    # Dismiss the "video published" panel so the next upload starts clean.
    for sel in ("ytcp-button#close-button", "ytcp-icon-button#close-button"):
        try:
            page.locator(sel).first.click(timeout=4000)
            break
        except Exception:
            pass
    time.sleep(3)
    return link


def shorts(ctx):
    """Upload every Short in `meta/shorts_publish.json` and link each to the
    long-form film.

    A Short that does not point back at the film is just a Short: the whole
    reason to cut them is to feed the thing they came from. YouTube's own
    mechanism for that is the Related video field, which is why this stage
    does both jobs rather than leaving the linking to a human.
    """
    spec_path = P.p("meta", "shorts_publish.json")
    if not os.path.exists(spec_path):
        raise SystemExit(f"missing {spec_path}")
    spec = json.load(open(spec_path))

    film = spec.get("related_video", "auto")
    if film == "auto":
        res = json.load(open(P.p("meta", "upload_result.json")))
        film = res["link"].rsplit("/", 1)[-1]
    film = film.rsplit("/", 1)[-1]
    film_url = f"https://youtu.be/{film}"

    privacy = spec.get("privacy", "public")
    page = open_studio(ctx)
    assert_channel(page, "shorts")

    out = []
    for sh in spec["shorts"]:
        path = os.path.join(P.root, sh["file"])
        if not os.path.exists(path):
            raise SystemExit(f"missing {path}")
        desc = sh["description"].replace("{film_url}", film_url)
        say(f"--- short {sh['id']} ---")
        link = _upload_one(page, path, sh["title"], desc, privacy,
                           sh.get("tags"))
        say(f"{sh['id']}: {link or '(link not captured)'}")
        out.append({"id": sh["id"], "file": sh["file"], "link": link,
                    "title": sh["title"]})

    with open(P.p("meta", "shorts_result.json"), "w") as f:
        json.dump({"film": film_url, "shorts": out}, f, indent=2,
                  ensure_ascii=False)
    say("wrote meta/shorts_result.json")

    for item in out:
        if not item["link"]:
            continue
        item["video_id"] = item["link"].rsplit("/", 1)[-1]
    _resolve_ids(page, out)
    _link_back(page, out, film, film_url)
    with open(P.p("meta", "shorts_result.json"), "w") as f:
        json.dump({"film": film_url, "shorts": out}, f, indent=2,
                  ensure_ascii=False)
    return out


def fresh_tab(page, url, settle_extra=3.0):
    """Open `url` in a brand-new tab and return that tab.

    Studio's router only rewrites navigations issued inside a tab that has
    already rendered another Studio route -- which is why `page.goto` from the
    dashboard keeps landing back on the dashboard no matter how many times it
    is retried. A new tab is always a first navigation, and a first navigation
    always lands. Use this for anything read-only; it is far more reliable
    than retrying in place. Caller closes the tab.
    """
    tab = page.context.new_page()
    tab.goto(url, wait_until="domcontentloaded", timeout=90000)
    settle(tab)
    time.sleep(settle_extra)
    return tab


def _channel_videos(page):
    """{video_id: title} for every Short and video on the channel.

    The published dialog does not always surrender the share link, so title
    lookup is the reliable way to find what was just uploaded.
    """
    js = """() => {
      const out = {};
      const walk = (root, d) => {
        if (d > 12) return;
        let els; try { els = root.querySelectorAll('*'); } catch(e) { return; }
        for (const e of els) {
          if (e.tagName === 'YTCP-VIDEO-ROW') {
            const a = e.querySelector("a[href*='/video/']");
            if (a) {
              const id = a.getAttribute('href').split('/video/')[1]
                          .split('/')[0];
              out[id] = e.innerText || '';
            }
          }
          if (e.shadowRoot) walk(e.shadowRoot, d + 1);
        }
      };
      walk(document, 0);
      return out;
    }"""
    found = {}
    for tab in ("short", "upload"):
        t = fresh_tab(page, f"{studio_url()}/videos/{tab}")
        try:
            rows = {}
            for _ in range(8):
                try:
                    rows = t.evaluate(js)
                except Exception:
                    rows = {}
                if rows:
                    break
                time.sleep(2)
            if rows:
                found.update(rows)
            else:
                say(f"{tab} list: no rows found")
        finally:
            try:
                t.close()
            except Exception:
                pass
    return found


def _resolve_ids(page, items):
    """Fill in missing video ids by matching titles on the channel."""
    missing = [i for i in items if not i.get("video_id")]
    if not missing:
        return items
    table = _channel_videos(page)
    for item in missing:
        title = item["title"].strip()
        for vid, blob in table.items():
            if title and title in blob:
                item["video_id"] = vid
                item["link"] = f"https://youtu.be/{vid}"
                say(f"{item['id']}: resolved to {vid} by title")
                break
        else:
            say(f"{item['id']}: could not resolve a video id")
    return items


def _link_back(page, items, film_id, film_url):
    """Send every Short's viewers to the film, by whatever means YouTube allows.

    Preferred: the Related video field, which renders as a first-class link on
    the Short itself. On an unverified channel that is locked, and so is
    pinning -- so fall back to posting the link as a comment, which on a young
    channel is also the top comment. The description already carries it; this
    is belt and braces, because a Short that does not point at its film is
    just a Short.
    """
    comment = (f"Full film — Sixty Hours: The 2008 Mumbai Attacks, "
               f"In the Order They Happened: {film_url}")
    comment = P.get("shorts", "comment", default=comment).replace(
        "{film_url}", film_url)
    walled = False
    pin_walled = False
    for item in items:
        vid = item.get("video_id")
        if not vid:
            continue
        if not walled:
            try:
                _set_related_video(page, vid, film_id)
                item["related_video"] = film_id
                say(f"{item['id']}: related video set to {film_id}")
                continue
            except TrustWall as e:
                walled = True
                say(f"! {e} -- falling back to comments for every Short")
            except Exception as e:
                say(f"{item['id']}: related video NOT set -- {str(e)[:90]}")
        item["comment"] = _comment_film_link(page, vid, comment, film_url)
        if pin_walled or not item["comment"]:
            item["pinned"] = False
            continue
        try:
            item["pinned"] = _pin_comment(page, vid, film_url)
        except TrustWall as e:
            item["pinned"] = False
            pin_walled = True
            say(f"{item['id']}: not pinned -- {e}")
        except Exception as e:
            item["pinned"] = False
            say(f"{item['id']}: pin failed -- {str(e)[:90]}")
    if walled or pin_walled:
        say("")
        say("ACTION NEEDED: Studio > Settings > Channel > Feature eligibility")
        say("  -> complete the one-time verification (6s selfie video or ID).")
        say("  Until then, Related video and pinned comments stay locked.")
    return items


def promote(ctx):
    """Link already-uploaded Shorts back to the film.

    Split out from `shorts` on purpose: uploading is the expensive, one-shot
    part, and linking is the part that fails for reasons outside the tool.
    Re-running this is safe and idempotent.
    """
    spec = json.load(open(P.p("meta", "shorts_publish.json")))
    film = spec.get("related_video", "auto")
    if film == "auto":
        film = json.load(open(P.p("meta", "upload_result.json")))["link"]
    film = film.rsplit("/", 1)[-1]
    film_url = f"https://youtu.be/{film}"

    res_path = P.p("meta", "shorts_result.json")
    if os.path.exists(res_path):
        items = json.load(open(res_path))["shorts"]
    else:
        items = [{"id": s["id"], "file": s["file"], "title": s["title"],
                  "link": ""} for s in spec["shorts"]]

    page = open_studio(ctx)
    assert_channel(page, "promote")
    _resolve_ids(page, items)
    _link_back(page, items, film, film_url)
    with open(res_path, "w") as f:
        json.dump({"film": film_url, "shorts": items}, f, indent=2,
                  ensure_ascii=False)
    say("wrote meta/shorts_result.json")
    return items


def main():
    global P
    ap = argparse.ArgumentParser(
        description="Publish a video to YouTube via Studio automation")
    ap.add_argument("stage",
                    choices=["login", "recon", "channels", "switch", "branding",
                             "upload", "shorts", "promote", "edit",
                             "thumbnail", "publish", "verify"])
    ap.add_argument("project", help="directory containing publish.json")
    ap.add_argument("--video", default=None, help="video id for `edit`")
    ap.add_argument("--minutes", type=int, default=20,
                    help="how long `login` waits for sign-in")
    ap.add_argument("--privacy", default="public",
                    choices=["public", "unlisted", "private"],
                    help="target visibility for `publish`")
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
            elif a.stage == "login":
                login(ctx, a.minutes)
            elif a.stage == "channels":
                channels(ctx)
            elif a.stage == "switch":
                switch(ctx)
            elif a.stage == "branding":
                branding(ctx)
            elif a.stage == "verify":
                verify(ctx)
            elif a.stage == "edit":
                edit(ctx, a.video)
            elif a.stage == "publish":
                publish(ctx, a.video, a.privacy)
            elif a.stage == "shorts":
                shorts(ctx)
            elif a.stage == "promote":
                promote(ctx)
            elif a.stage == "thumbnail":
                thumbnail(ctx, a.video)
            else:
                upload(ctx)
        finally:
            time.sleep(2)
            ctx.close()  # never SIGKILL: that wipes the signed-in session


if __name__ == "__main__":
    main()
