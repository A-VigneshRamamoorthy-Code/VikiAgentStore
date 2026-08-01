---
name: transparency
description: >
  Guide for iOS transparent widgets, background baking, wallpaper cropping, host transparency hacks, coordinate math, and blending UI components.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# Invisible-Widget Mechanism (Live Host Transparency + Baking Fallback)

> A technical playbook for implementing "transparent" iOS Home Screen widgets using a hybrid approach: a private API path (live host transparency) for development/internal use, and a public API path (static wallpaper baking) for production.

---

## ⛔️ SHIPPING BUILDS MUST NOT USE HOST TRANSPARENCY (App Store Guideline 2.5.1)

**The primary path below is compiled OUT by default and must stay that way in anything submitted to the App Store.**

The implementation names private Apple internals *as string literals* — `CHSBaseDescriptor`, `CHSWidgetDescriptor`, `_preferredBackgroundStyle`, `setTransparent:`, `setBackgroundRemovable:`, `getAllCurrentDescriptorsWithCompletion:` — and swizzles a private WidgetKit XPC class. Those literals **survive into the binary** and are exactly what App Store static analysis flags under **Guideline 2.5.1 (Private API)**. Hiding symbols from the import table does **not** hide them from a `strings` scan.

The whole hook must therefore be gated on a specific build flag (e.g., **`HOST_TRANSPARENCY_ENABLED`**), which defaults to **0**. With the flag off, the installer simply marks the feature unavailable, and the Swift layer takes the **baking** path (the exact fallback used if private symbols are missing).

**Verify before every submission** (must all print `0` or `NONE`):

```sh
APPEX="Path/To/Your/WidgetExtension.appex/YourWidgetExtension"
for s in CHSBaseDescriptor CHSWidgetDescriptor _preferredBackgroundStyle \
         setTransparent: setBackgroundRemovable: \
         getAllCurrentDescriptorsWithCompletion: WidgetExtensionXPCServer; do
  printf '%-44s %s\n' "$s" "$(strings "$APPEX" | grep -c "$s")"
done
nm -u "$APPEX" | grep -i 'objc_lookUpClass\|class_getInstanceVariable\|method_setImplementation\|ivar_getOffset' || echo NONE
```

Set `HOST_TRANSPARENCY_ENABLED=1` only for a **local** device build when working on the hook itself. **Never** define it in a configuration archived for distribution.

---

The widget is made see-through using **two ways**, tried in order. Both keep the app in Default appearance (the user never has to turn on the iOS "Clear" or "Tinted" mode).

## 1. PRIMARY — Live Host Transparency (Private API) — DISABLED BY DEFAULT

An Objective-C++ routine (compiled for the **widget target only**, `-fno-objc-arc`, installed via `+load` at extension launch) makes **SpringBoard draw a transparent platter and composite the *live* wallpaper itself**. The widget shows the real wallpaper through it, surviving wallpaper changes without taking screenshots.

Mechanism: swizzle the private WidgetKit XPC object's `getAllCurrentDescriptorsWithCompletion:` **inside** the extension (the call the host makes over XPC to fetch our descriptors). In the completion, re-archive the opaque `DescriptorFetchResult`, decode it into a shadow class using NSCoding keys (`widgetDescriptors` / `controlDescriptors` / `activityDescriptors`), mark every `CHSWidgetDescriptor` clear, re-encode, and hand a real fetch result back.

**API Evolution:** Newer iOS versions removed legacy setters (`setTransparent:` / `setBackgroundRemovable:`). Transparency is now often a *computed, read-only* property derived from the `_preferredBackgroundStyle` **ivar** on superclass `CHSBaseDescriptor`. By dynamically resolving the ivar offset (via `class_getInstanceVariable`) and setting it to **1** (`0 = opaque, 1 = clear, 2 = clear + material`), the value **survives the NSKeyedArchiver round-trip** to the host. The legacy setters should still be called best-effort for backward compatibility.

**App Group Flags for Observability** (Written by the installer, read by the Swift layer):

| Key | Meaning |
|-----|---------|
| `e.g., widget.hostTransparent.v1` | hook installed (private API present) → **availability** |
| `e.g., widget.hostTransparent.os.v1` | OS build the last availability probe ran on |
| `e.g., widget.hostTransparent.fired.v1` | the swizzled callback actually ran (host called through it) |
| `e.g., widget.hostTransparent.count.v1` | # widget descriptors the callback saw |
| `e.g., widget.hostTransparent.applied.v1` | # descriptors successfully marked transparent |

**⛔️ Install the hook with RETRIES, and keep the availability flag HONEST.**
`+load` runs while the extension's images are still being wired up. The swizzled class (e.g., `_TtCC9WidgetKit24WidgetExtensionXPCServer14ExportedObject`) is a **nested Swift class** whose ObjC metadata may not be realized yet — so `objc_lookUpClass` might miss. A silent failure here causes a fallback to baking, and as the metadata later loads, subsequent timeline builds could flip-flop between baked and clear widgets. The installer must retry on the main queue (e.g., 10/40/120/300/800 ms) before the host asks for descriptors. If every retry fails, the installer must record a definitive `NO` so the system reliably falls back.

**Swift render path** evaluates in this order:
1. `renderingMode != .fullColor` (system Clear/Tinted mode) → `Color.clear` (iOS paints its own glass).
2. `isLiveWidget && hostTransparencyAvailable` → **`Color.clear`**: the descriptor was successfully marked transparent so the host composites the live wallpaper. (Ensure this is gated so in-app preview cards don't mistakenly use it).
3. else → **bake** (Fallback): private API absent, or rendering an in-app preview.

**Verification REQUIRES a physical device.** The Simulator never relaunches a 3rd-party widget extension (so `+load` never runs) and renders custom wallpapers as black — it **cannot** show host transparency. Verify on-device by extracting the App Group preferences:

```bash
xcrun devicectl device copy from --device <UDID> \
  --domain-type appGroupDataContainer \
  --domain-identifier group.com.example.app \
  --source Library/Preferences/group.com.example.app.plist \
  --destination app_group.plist && plutil -p app_group.plist
```

## 2. FALLBACK — Static Wallpaper Baking (Public API)

If the private API is absent or unavailable, the fallback renders a previously-uploaded user wallpaper full-screen, offset by the widget's positional origin (`e.g., slot.origin(for:size:screen:)`), and clipped to the widget bounds via `containerBackground`. The widget paints the exact wallpaper slice behind it, blending into a **static** background.

Unlike the live path, this does **not** survive a wallpaper change without the user manually uploading their new background.

**Simulator caveat:** The iOS Simulator renders custom Home Screen wallpapers as solid black. To verify blending on the Simulator, set the background to pure black and check that the baked background correctly aligns and blends.

**Measured baking floor:** When baking a black wallpaper against a black Home Screen, the baked widget background will not be perfectly `rgb(0,0,0)`. There is an irreducible Default-mode widget material floor introduced by iOS (e.g., `rgb(12,12,12)`). You cannot bypass this floor via public API, so do not chase a perfect 0-luminance match; baking is already at the limit. The live path (Private API) avoids this floor entirely because the platter itself is stripped of material.
