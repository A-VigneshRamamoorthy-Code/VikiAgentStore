---
name: macos-app
description: >
  Guide for shipping a native macOS app target (SwiftUI + AppKit): window lifecycle, the
  Window menu, Dock reopen, menu-bar commands, and the Guideline 4 "no way to reopen the
  closed window" rejection. Covers `Window` vs `WindowGroup`, why a lone `Window` scene
  quits the app on close, `applicationShouldTerminateAfterLastWindowClosed` /
  `applicationShouldHandleReopen`, the SwiftUI-to-AppKit `openWindow` bridge, and how to
  prove the behaviour with System Events UI scripting before you submit. Also covers the
  pre-submit menu sweep: why ⌘, is dead without a `Settings` scene and why Help ▸ App Help
  shows "Help isn't available" until you replace `.help`. Triggers on
  keywords like macOS, Mac app, AppKit, NSApplication, Window menu, window reopen,
  menu bar, Settings, Help menu, Guideline 4.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---

# macOS app target — windows, menus & Guideline 4

> Part of the **[iOS Agent Guide](../ios-agent-guide/SKILL.md)**. Submission mechanics are in
> [app-store-submission.md](../app-store-submission/SKILL.md); build and upload in
> [app-store-release.md](../app-store-release/SKILL.md).
>
> Read this **before writing the Mac `App` struct**, not after the rejection email.

---

## 0. ⛔️ The rejection this file exists to prevent

> **Guideline 4 - Design.** "We found that when the user closes the main application
> window there is no menu item to re-open it." — App Review, macOS 1.0 (2), real
> rejection.

Apple's own two acceptable answers, verbatim:

1. "implement a Window menu that lists the main window so it can be reopened, or
   provide similar functionality in another menu item", **or**
2. "if the application is a single-window app, it might be appropriate to save data and
   quit the app when the main window is closed."

**There is no third option.** An app that survives its last window with no route back is
a rejection, every time. This is a *design* guideline, so a reviewer hits it by hand —
you cannot get lucky.

---

## 1. Why a SwiftUI Mac app walks into this by default

The trap is a combination, and each half looks harmless on its own:

| Ingredient | What it does | Why it hurts |
|---|---|---|
| `WindowGroup` / `Window` scene | Declares the main window | The **Window menu lists open windows only** — a closed window has no entry |
| `CommandGroup(replacing: .newItem) {}` | Removes File ▸ New / New Window (correct for a single-window app) | Also removes the **only** stock way to conjure a window back |
| AppKit default | `NSApplication` keeps running with zero windows | The app is alive, invisible, and unreachable except by quitting it |

Net effect: ⌘W, then the app exists only in the Dock, and every menu is a dead end.
Verified on the shipped 1.0 (2) binary with System Events — after Window ▸ Close the
process reported `count of windows = 0` while still running, and the Window menu ended
at "Arrange in Front".

**`WindowGroup` is the wrong scene type for a single-window app** even after you fix the
menu: `openWindow(id:)` on a group *opens another window*, so the user who clicks the
menu item twice gets two copies of a single-window app. Use `Window`.

---

## 2. The fix — three load-bearing parts

Remove any one of these and the rejection comes back. Shipped, reviewer-facing shape:

```swift
@main
struct MyMacApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        // (1) `Window`, not `WindowGroup`: openWindow(id:) re-shows this one scene
        //     instead of stacking duplicates.
        Window("My App", id: MacWindowID.main) {
            RootView()
        }
        .commands {
            CommandGroup(replacing: .newItem) {}   // no "New Window" for a 1-window app
            MacWindowCommands()                    // (2) the way back
        }
    }
}

enum MacWindowID { static let main = "myapp-main" }

// (2) Put the main window in the Window menu, permanently — not just while it is open.
struct MacWindowCommands: Commands {
    @Environment(\.openWindow) private var openWindow

    var body: some Commands {
        CommandGroup(after: .windowList) {
            Button("My App") { MacWindowBridge.showMainWindow(using: openWindow) }
                .keyboardShortcut("0", modifiers: .command)
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    // (3) A lone SwiftUI `Window` scene TERMINATES the app when that window closes.
    //     Verified empirically. Override it or a media/sync app dies mid-task.
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        false
    }

    // Dock-icon click with no windows: AppKit only *offers*; the app must reopen.
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag { MacWindowBridge.showMainWindow() }
        return true
    }
}
```

Precedent for keeping the app alive: **Apple's own Music.app** does exactly this — its
Window menu lists "Music", and closing the window leaves the app running and playing.
Matching a first-party app is the cheapest defence in a design review.

### ⛔️ `CommandGroup(after: .windowList)`, not a new `CommandMenu`

A hand-rolled `CommandMenu("Window")` produces a **second** Window menu next to the
system one — visibly broken, and itself a Guideline 4 risk. `.windowList` is the anchor
that puts your item under "Bring All to Front", where a Mac user looks for it.
Sanity-check the result: the Window menu should read *Close / Minimize / Zoom / … /
Bring All to Front / **YourApp ⌘0***.

### Placeholder shortcut warning

⌘0 is free in most apps but means "actual size" in some editors, and ⌘1…⌘9 usually belong
to tabs/sections. Pick one that does not collide with a shortcut you already register —
duplicate shortcuts silently fire only one action.

---

## 3. The AppKit ↔ SwiftUI bridge (why a global is unavoidable here)

`applicationShouldHandleReopen` is an **AppKit** callback: it has no SwiftUI
`@Environment`, so it cannot call `openWindow`. And once the window is destroyed there is
no `NSWindow` left to `makeKeyAndOrderFront`. So the root view parks the action where
AppKit can reach it:

```swift
enum MacWindowBridge {
    private static var openMainWindow: (() -> Void)?

    static func registerMainWindowOpener(_ open: @escaping () -> Void) { openMainWindow = open }

    static func showMainWindow(using open: OpenWindowAction? = nil) {
        NSApp.activate(ignoringOtherApps: true)
        if let open { open(id: MacWindowID.main) }
        else if let openMainWindow { openMainWindow() }
        else { NSApp.windows.first { $0.canBecomeMain }?.makeKeyAndOrderFront(nil) }
    }
}

// in RootView.body:
.onAppear {
    MacWindowBridge.registerMainWindowOpener { openWindow(id: MacWindowID.main) }
}
```

`NSApp.activate(ignoringOtherApps:)` is required: reopening from a background app
otherwise creates the window behind whatever the user is looking at.

---

## 4. Which of Apple's two routes to take

| | Route A — stay alive + Window menu item | Route B — quit on last window close |
|---|---|---|
| Use when | Anything keeps running headless: audio playback, sync, downloads, a menu-bar item, background transfers | The window *is* the app — a pure document/utility UI with no background work |
| Code | `applicationShouldTerminateAfterLastWindowClosed → false` **plus** the Window-menu item | `→ true` **plus** flush state in `applicationWillTerminate` |
| Extra duty | Must handle Dock reopen; must never leave a zero-window app the user cannot get back | Must **save first** — Apple says "save data and quit" |
| Risk | Forgetting the menu item = the rejection | Killing a download/playback the user started = a support complaint |

Route B is *not* cheaper if you have any background activity. Route A is the default for
media, sync, and menu-bar-adjacent apps.

---

## 5. Prove it before you submit — System Events UI scripting

Do not eyeball this. A reviewer will do the exact sequence below; you should have run it
first, on the **Release** build you are about to upload.

```bash
# 0. exactly ONE copy running (see the quirks below) — then:
osascript -e 'tell application "System Events" to tell process "MyApp" to click menu item "Close" of menu 1 of menu bar item "Window" of menu bar 1'
osascript -e 'tell application "System Events" to tell process "MyApp" to count of windows'   # expect 0
pgrep -x MyApp                                                                                # expect: still alive (Route A)

# the item must EXIST and be ENABLED with zero windows open
osascript -e 'tell application "System Events" to tell process "MyApp" to get enabled of menu item "MyApp" of menu 1 of menu bar item "Window" of menu bar 1'
osascript -e 'tell application "System Events" to tell process "MyApp" to click menu item "MyApp" of menu 1 of menu bar item "Window" of menu bar 1'
osascript -e 'tell application "System Events" to tell process "MyApp" to count of windows'   # expect 1

open -a /Applications/MyApp.app     # emulates the Dock-icon reopen path
```

Also check, by hand: clicking the item **twice** yields **one** window (proves `Window`
not `WindowGroup`), and app state (playback position, sign-in, scroll) survives the
close → reopen round trip.

### osascript quirks that will burn an hour

- ⛔️ **Two processes with the same name and System Events answers about the wrong one** —
  silently. `count of windows` returns 0 for a window plainly on screen. Kill every copy
  but one first (a stale DerivedData build is the usual culprit; see §7).
- `before` is a **reserved word** in AppleScript — never use it as an identifier.
- `tell X to tell Y` (the one-line form) **cannot** be followed by a multi-line block; use
  nested `tell … end tell` blocks instead.
- UI scripting needs Accessibility permission for whatever terminal or agent drives it.

---

## 6. ⛔️ Prove the *binary* contains the fix — `strings` will lie to you

Swift's **small-string optimisation** stores any string of ≤ 15 UTF-8 bytes inline in the
struct, so it is **never emitted into the binary**. `"myapp-main"` and most window IDs
fall under that limit, and `strings | grep` returns nothing on a build that is perfectly
correct. Grep for symbols and ObjC selectors instead:

```bash
nm "/Applications/MyApp.app/Contents/MacOS/MyApp" | grep -c MacWindowCommands
strings -a "/Applications/MyApp.app/Contents/MacOS/MyApp" \
  | grep -E 'applicationShouldTerminateAfterLastWindowClosed|applicationShouldHandleReopen'
/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "/Applications/MyApp.app/Contents/Info.plist"
```

Confirm `CFBundleVersion` matches the build you actually uploaded — verifying a stale
local copy proves nothing.

---

## 7. macOS pre-submit sweep (Guideline 4 — Design)

Beyond the window fix, walk these before every Mac submission. Each is something a Mac
reviewer touches and an iOS-first codebase commonly gets wrong:

| # | Check | Why |
|---|---|---|
| 1 | Close the main window → reopen it from the **Window** menu | §0. The rejection. |
| 2 | Dock-icon click with no windows reopens it | Same guideline, second path |
| 3 | Window menu has **no duplicate** and no dead entries | Hand-rolled `CommandMenu("Window")` |
| 4 | ⌘W / ⌘M / ⌘Q / ⌘, all behave as a Mac user expects | Preferences **must** be ⌘, in the app menu |
| 5 | No stub menu items that do nothing | A greyed-out or no-op item reads as unfinished |
| 6 | Window resizes sanely down to its `minWidth`/`minHeight`; nothing truncates | Reviewers resize |
| 7 | Full screen and Stage Manager do not break layout | Free to test, common failure |
| 8 | No iOS-isms: no tap-sized rows, no "tap", no iPhone-only copy | Guideline 4 "lower-quality experience" |
| 9 | Keyboard navigation and text selection work where expected | Mac baseline |
| 10 | Exactly **one** copy of the app installed while testing | Prevents §5's silent wrong-process answers |

**Duplicate copies (test hygiene):** `lsregister -u <path>` clears Launch Services but
**not** Spotlight — delete the stray `.app` products under `DerivedData` to make
`mdfind "kMDItemFSName == 'MyApp.app'"` return one result. Avoid `lsregister -kill -r`;
it resets the user's default-app associations.

### The two rows 4 and 5 actually catch

Running this sweep on a Release build that had already shipped to review turned up both
of these. Neither is visible from the source — you have to open the menus.

**⌘, is dead unless you declare a `Settings` scene.** SwiftUI puts *Settings…* in the app
menu only if the scene exists; otherwise the item is absent and the shortcut a Mac user
reaches for by reflex does nothing. An app with a settings screen reachable only from
inside its own UI still fails row 4.

```swift
Settings { SettingsView() }        // adds "Settings…  ⌘," to the app menu
```

⛔️ **Help ▸ *YourApp* Help raises an error sheet by default.** AppKit synthesises that
item and, with no help book in the bundle, clicking it shows *"Help isn't available for
YourApp."* — a stock alert, in a menu the reviewer will open, that reads as broken. It is
row 5 in its purest form. Either ship a help book, or replace the item:

```swift
CommandGroup(replacing: .help) {
    Link("YourApp Help", destination: URL(string: "https://example.com/help")!)
}
```

Both are verified the same way as §5 — click the item with System Events on the built
app and assert on what appears, because both look perfectly fine in code.

---

## 8. If you are already rejected

1. Fix the code, then **verify with §5 on the Release build**.
2. Bump the build number, archive, upload, wait for `COMPLETE` processing, **attach the
   build to the version** (do this *before* touching the submission).
3. Answer the rejection in the **App Review notes** — name the guideline and describe the
   new menu item, e.g. *"Window ▸ MyApp (⌘0) reopens the main window; the app keeps
   playing with the window closed, matching Music.app."* Notes are capped at 4000 chars.
4. Resubmit — a rejected submission is **reused**, not re-created. See
   [app-store-submission.md](../app-store-submission/SKILL.md) §10.

⛔️ **Reply in Resolution Center before step 4, not after.** Submitting flips the version
to `WAITING_FOR_REVIEW` and App Store Connect removes the Reply button, leaving only
*Cancel Submission* — the old thread cannot be answered again until the next decision.
Because of that, step 3 is not optional politeness: the notes are the only channel that
survives submitting. See [app-store-submission.md](../app-store-submission/SKILL.md) §8.

⛔️ **The rejection letter itself is web-UI only.** The ASC API exposes a submission's
`state` and nothing else — there is no Resolution Center endpoint, `/v1/resolutionCenterThreads`
404s, and the internal iris API rejects API-key JWTs with a 401. An agent cannot read the
rejection for you; ask for the text to be pasted in, and do not guess at it from the state
alone.

⛔️ On a **two-platform** app record (iOS + macOS), never run a metadata script that walks
both platforms to push a macOS-only change: it will edit an iOS version that may be
sitting in `WAITING_FOR_REVIEW`. PATCH the single macOS `appStoreReviewDetail` instead.
The same applies to *attaching a build* — a bare "attach the latest build" helper that
loops over platforms will swap the binary under a live iOS review. Gate every such tool on
an explicit `--platform`.

---

← Back to [iOS Agent Guide](../ios-agent-guide/SKILL.md) ·
[Submission & review](../app-store-submission/SKILL.md)
