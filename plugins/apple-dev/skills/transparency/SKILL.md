---
name: transparency
description: >
  Apple development skill for Invisible-widget mechanism (live host transparency + baking fallback). Use this skill when working on transparency tasks.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# Invisible-widget mechanism (live host transparency + baking fallback)

> Part of the **[Leap Agent Guide](../../agents.md)**.
>
> **Full deep-dive: [`docs/TRANSPARENT_WIDGETS.md`](../TRANSPARENT_WIDGETS.md)** —
> read it before touching `LeapWidgetTransparency.mm` or `LeapWidgetBackground`. This
> file is the summary.

---

## ⛔️ SHIPPING BUILDS DO NOT USE HOST TRANSPARENCY (App Store 2.5.1)

**The primary path in §6a below is compiled OUT by default and must stay that way in
anything submitted to the App Store.**

`LeapWidgetTransparency.mm` names private Apple internals *as string literals* —
`CHSBaseDescriptor`, `CHSWidgetDescriptor`, `_preferredBackgroundStyle`,
`setTransparent:`, `setBackgroundRemovable:`,
`getAllCurrentDescriptorsWithCompletion:` — and swizzles a private WidgetKit XPC class
with `method_setImplementation`. Those literals **survive into the binary** and are
precisely what App Store static analysis flags under **guideline 2.5.1 (private API)**.
`dlsym`/`objc_lookUpClass` hide a symbol from the import table but **not** from a
`strings` scan — the same lesson already recorded for the battery investigation in
[status-and-history.md](status-and-history.md).

The whole hook is therefore gated on **`LEAP_HOST_TRANSPARENCY`**, which defaults to
**0**. With the flag off, `+load` records `LeapSetHostTransparencyAvailable(NO)` and the
Swift layer takes the **baking** path (§6b) — the exact fallback it already used on any
OS where the private symbols were missing, so there is no new code path to test.

**Verify before every submission** (must all print `0` / `NONE`):

```sh
APPEX="$APP/PlugIns/LeapWidgetExtension.appex/LeapWidgetExtension"
for s in CHSBaseDescriptor CHSWidgetDescriptor _preferredBackgroundStyle \
         setTransparent: setBackgroundRemovable: \
         getAllCurrentDescriptorsWithCompletion: WidgetExtensionXPCServer; do
  printf '%-44s %s\n' "$s" "$(strings "$APPEX" | grep -c "$s")"
done
nm -u "$APPEX" | grep -i 'objc_lookUpClass\|class_getInstanceVariable\|method_setImplementation\|ivar_getOffset' || echo NONE
```

Set `LEAP_HOST_TRANSPARENCY=1` only for a **local** device build when working on the
hook itself. **Never** define it in a configuration that can be archived for
distribution, and never define it project-wide (the `LEAP_INTERNAL` lesson: a
project-level flag reaches Release through a mis-selected configuration).

**The marketing copy does not depend on it.** The App Store listing deliberately
describes only the baked behaviour ("blends best when that background matches the
wallpaper set on your Home Screen"), and never says "transparent" or "see-through" in
user-visible text. So the flag can stay off without making any published claim untrue.

---

Leap makes the widget see-through **two ways**, tried in order. Both keep the app in
**Default** appearance (the user never turns on iOS "Clear"). The primary path shows
the *live* wallpaper (Koco-style, private API); baking is the fallback.

## 6a. PRIMARY — Koco-style host transparency (live wallpaper, private API) — DISABLED BY DEFAULT

`LeapWidget/LeapWidgetTransparency.mm` (Obj-C++, **widget target only**,
`-fno-objc-arc`, installed by `+load` at extension launch — no Swift call needed)
makes **SpringBoard draw a transparent platter and composite the *live* wallpaper
itself**. So the widget shows the real wallpaper through it, with **no screenshot**
and **surviving wallpaper changes** — the user's original requirement. This is what
apps like **Koco** do.

Mechanism (ported from **pookjw/ClearAndBlurredWidgets**): swizzle the private
WidgetKit XPC object's `getAllCurrentDescriptorsWithCompletion:` **inside** the
extension (the call the host makes over XPC to fetch our descriptors). In the
completion, re-archive the opaque `DescriptorFetchResult`, decode it into a shadow
class using pookjw's NSCoding keys (`widgetDescriptors` / `controlDescriptors` /
`activityDescriptors` — these still match iOS 26.5), mark every `CHSWidgetDescriptor`
clear, re-encode, and hand a real fetch result back.

**iOS 26 API change — verified on iOS 26.5; do NOT use the old setters.** The iOS
17/18 setters `setTransparent:` / `setBackgroundRemovable:` /
`setPreferredBackgroundStyle:` were **REMOVED**. On iOS 26 `CHSWidgetDescriptor
.transparent` is a *computed, read-only* property derived from the
`_preferredBackgroundStyle` **ivar** on superclass `CHSBaseDescriptor` (`q`/long,
offset 56): **0 = opaque, 1 = clear (no material), 2 = clear + material**. So we set
that ivar to **1** directly (resolve the offset dynamically via
`class_getInstanceVariable` for robustness). The value **survives the
NSKeyedArchiver round-trip** to the host, so the host decodes a descriptor whose
`isTransparent` returns YES. The legacy setters are still called best-effort so this
keeps working on iOS 17/18.

**⚠️ PRIVATE API → App Store Review Guideline 2.5.1 rejection risk** (accepted by
the user). iOS 26 may add a Liquid Glass outline. If the private class/ivar is ever
absent, the installer writes nothing, clears the availability flag, and the Swift
layer falls back to baking (§6b). Do NOT "simplify" this into system Clear/Tinted
mode — that would force the user to toggle iOS appearance, which is exactly what this
feature avoids.

**App Group flags it writes** (`group.com.sololeap.leap.app`, read by the Swift
render path + the app's Settings "LIVE WALLPAPER" status row):

| Key | Meaning |
|-----|---------|
| `leap.hostTransparent.v1` | hook installed (private API present) → **availability** |
| `leap.hostTransparent.os.v1` | OS build the last availability probe ran on |
| `leap.hostTransparent.fired.v1` | the swizzled callback actually ran (host called through it) |
| `leap.hostTransparent.count.v1` | # widget descriptors the callback saw |
| `leap.hostTransparent.applied.v1` | # descriptors confirmed `isTransparent == YES` |

**⛔️ Install the hook with RETRIES, and keep `leap.hostTransparent.v1` HONEST**
(`LeapTryInstallHostTransparency` / `LeapScheduleHostTransparencyRetry` in
`LeapWidget/LeapWidgetTransparency.mm`). `+load` runs while the extension's images are
still being wired up, and the swizzled class
`_TtCC9WidgetKit24WidgetExtensionXPCServer14ExportedObject` is a **nested Swift class**
inside WidgetKit whose ObjC metadata may not be realised yet — so `objc_lookUpClass`
misses, `swizzle()` returns `NO`, and that whole launch silently falls back to baking.
Because the Swift layer reads this flag **every time a timeline is built**, such a launch
produced a whole timeline of **baked** tiles while the next produced **clear** ones — a
widget with a visibly coloured wallpaper had its **hue appear and disappear** as reloads
alternated (issue6 #1; widgets whose wallpaper is dark hid the same flip-flop). The
installer now retries on the main queue at 10/40/120/300/800/2000 ms, which is well
before the host asks for descriptors.

Do **not** "fix" this by latching the flag to `YES`: the flag must mean *the swizzle is
installed in this process*. Latching it while the hook is absent draws `Color.clear` onto
an **opaque** platter, which is the old grey-material bug. If every retry fails the
installer records the honest `NO` so the Swift layer bakes.

**Swift render path** — `LeapWidgetBackground.transparentBackground`
(`Shared/LeapWidgetContentView.swift`), three cases in order:
1. `renderingMode != .fullColor` (system Clear/Tinted) → `Color.clear` (iOS paints its own glass).
2. `isLiveWidget && LeapStore.shared.hostTransparencyAvailable` → **`Color.clear`** — the **primary** path: the descriptor is transparent so the host composites the live wallpaper. `isLiveWidget` is `true` **only inside the real extension** (set at the `containerBackground` call site in `LeapWidget/LeapCheckInWidget.swift`), `false` for in-app previews.
3. else → **bake** (§6b): private API absent, or an in-app preview card (so the transparent effect stays visible on the card).

**Verification REQUIRES a physical device.** The Simulator never relaunches a
3rd-party widget extension (so `+load` / the flags never run) and renders custom
wallpaper as black — it **cannot** show host transparency. Read the on-device flags
without a debugger by pulling the App Group prefs plist:

```bash
xcrun devicectl device copy from --device <UDID> \
  --domain-type appGroupDataContainer \
  --domain-identifier group.com.sololeap.leap.app \
  --source Library/Preferences/group.com.sololeap.leap.app.plist \
  --destination /tmp/leap_group.plist && plutil -p /tmp/leap_group.plist
```

Device-verified (Viki's iPhone, iOS 26.5.2): `hostTransparent=true, fired=true,
count=1, applied=1` → the hook installed, the host fetched through it, and the placed
widget's descriptor was marked transparent. The app calls
`WidgetCenter.shared.reloadAllTimelines()` on foreground so the host re-fetches.

## 6b. FALLBACK — bake the wallpaper slice (no private API)

`LeapWidgetBackground.bakedWallpaper` renders `LeapWallpaper(kind:)` full-screen,
offset by `slot.origin(for:size:screen:)`, and lets `containerBackground` clip it to
the widget rect → the widget paints the exact wallpaper slice behind it and blends
into a **static** wallpaper. Used for in-app preview cards and whenever host
transparency is unavailable. For `.custom` it bakes the uploaded photo. Unlike §6a
this does **not** survive a wallpaper change (the user must re-upload / re-pick).

**Simulator caveat:** the iOS Simulator renders custom photo Home-Screen
wallpapers as solid **black** and exposes no Wallpaper settings pane. Verify the
bake with the **Midnight** (pure-black) Leap wallpaper on a black Home Screen —
the baked black background blends in and the widget reads as transparent.

**Measured baking floor (iPhone 17 Pro / iOS 26.5):** on the black Home Screen,
empty Home = `rgb(0,0,0)`, a baked Leap widget background = `rgb(12,12,12)` (blends,
~5% luminance delta), while Apple's own Calendar widget = `rgb(38,39,43)`. The
residual `rgb(12)` is iOS's **irreducible Default-mode widget material floor** — you
cannot go below it via public API, so do not chase "perfect" `rgb(0)`; baking is
already at the limit. (§6a's live path avoids this floor entirely because the platter
itself is transparent.)
