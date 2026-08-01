---
name: qa-and-reviews
description: >
  Apple development skill for QA & multi-agent review log. Use this skill when working on qa-and-reviews tasks.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# QA & multi-agent review log

The canonical record of **multi-agent QA / review passes** on Leap: the reusable
playbook for running one, plus a dated log of every pass (bugs found -> fixed,
reviewer verdicts, validated non-bugs, deferred items).

> Part of the **[Leap Agent Guide](../../agents.md)**. Open this when you are asked to
> "audit / review / functional-test the app", when you need to **re-run** the review,
> or when you want the record of what a prior pass found and fixed. Day-to-day status
> lives in [`docs/STATUS.md`](../STATUS.md); the broader changelog in
> [status-and-history.md](status-and-history.md).

---

## Reusable playbook — 3-agent, 2-stage review

Run this whenever the ask is "validate the whole app / look for bugs / review the
changes". It has held up once end-to-end (see the pass log below); reuse it verbatim.

**Roles (3 agents).**
- **Orchestrator + fixer — Opus (this agent).** Owns triage, applies every fix, runs
  the builds, updates docs, notifies the user. Reviewers never edit code.
- **Reviewer A — Gemini (`gemini-3.1-pro-preview`)**, launched via the `code-review`
  sub-agent (background).
- **Reviewer B — GPT (`gpt-5.6-sol`)**, launched via the `code-review` sub-agent
  (background), in parallel with Gemini.

**Hard rule:** *no functional bug may be left unfixed.* Non-bugs must be explicitly
justified (verified-correct or by-design) — silence is not resolution.

**Stage 1 — functional test.** Prompt both reviewers (rich, self-contained context) to
hunt for: stale / non-refreshing / blank widgets (timeline + capability-flag mapping),
premium-vs-free state, **7-day-trial reinstall bypass**, and any crash / force-unwrap /
add-edit-delete / onboarding-gating defect. Opus also does its own pass + a **baseline
build**. Collect -> de-dupe -> triage -> **Opus fixes ALL confirmed bugs** -> rebuild ->
**notify the user**.

**Stage 2 — code review.** Re-launch the same two reviewers on the **Stage-1 diff** and
overall quality. Triage -> fix every valid issue -> re-verify. When a reviewer flags
something, fix it and **ask the same reviewer to re-review** until it returns clean.
Then **notify the user**.

**Verification rule (do not skip).** Build **BOTH** configs:

```bash
xcodebuild -project Leap.xcodeproj -scheme Leap -configuration Debug \
  -destination 'platform=iOS Simulator,id=D95D5EEF-A4E4-41B1-976B-52635F7305C7' \
  -derivedDataPath /tmp/LeapDerivedData build
xcodebuild -project Leap.xcodeproj -scheme Leap -configuration Release \
  -destination 'platform=iOS Simulator,id=D95D5EEF-A4E4-41B1-976B-52635F7305C7' \
  -derivedDataPath /tmp/LeapDerivedData build
```

Release is mandatory: `#if DEBUG` / `#else` code paths (e.g. the debug-panel gate) only
compile under `-configuration Release`, so a Debug-only build hides real breakage.

**Notify** after each stage and at final completion:

```bash
bash /Users/vignesh/.copilot/skills/notify-user/scripts/notify.sh "<= 100-char one-liner>"
```

**Tips learned.** Reviewers run best in **parallel, background**; keep the two idle so
you can `write_agent` follow-ups instead of re-launching (they retain context). Widget
staleness almost always traces to `LeapProvider.timeline(for:in:)` precedence vs the
capability flags in `Shared/LeapWidgetContentView.swift` — see
[realtime-widgets.md](realtime-widgets.md). The Simulator masks live transparency and
oversized-timeline drops; some checks need a physical device
([build-and-run.md](build-and-run.md)).

---

## Pass log (newest first)

### Pass 1 — functional test + code review (stale-widget & premium audit)

Two-stage sweep with the playbook above. **10 functional bugs found and fixed;** both
reviewers ended clean; all fixes verified by building **Debug AND Release**. Three
notifications sent (Stage 1, Stage 2, final).

**Bugs found -> fixed**

| # | Sev | Stage | Bug | Fix | File(s) |
|---|-----|-------|-----|-----|---------|
| 1 | 🔴 crit | 1 | **Debug panel shipped in Release** — shake + hardcoded password (`NammaLeap@2026`) could grant Premium (`debugIsPremium`) and reset the 7-day trial; only its `#Preview` was gated. | Wrapped **every** entry point + the `isPro` override in `#if DEBUG`; Release now derives `isPro` **solely** from StoreKit — no reachable bypass. | `Leap/HomeView.swift`, `Leap/LeapViewModel.swift` |
| 2 | 🟠 high | 1 | **System-stat faces froze up to 24h** — `memory`/`processor`/`systemPulse` (RAM % / CPU % / uptime) + `storage`/`storageBar` fell into the timeline's midnight-only `else`. | Added capability flag **`showsSystemStats`** (`= category == .storage`) + a matching `.after(+30 min)` branch, mirroring `showsBattery`. | `Shared/LeapWidgetContentView.swift`, `LeapWidget/LeapCheckInWidget.swift` |
| 3 | 🟠 high | 1 | **Weather/calendar combos never prompted for permission** — `requestLiveDataAccess` switched on `LeapWidgetCategory`, so weather/calendar faces filed under Time/Date were skipped. | Now takes a `LeapWidgetKind` and dispatches on the **capability flags** (`kind.showsCalendar` / `kind.showsWeather`); call site passes `kind`. | `Leap/LeapViewModel.swift`, `Leap/HomeView.swift` |
| 4 | 🟡 med | 1 | **Weather in clock-combos stale ~3h** — `greetingClock`/`sceneClock` built 180 one-minute entries sharing ONE weather sample. | Cap the horizon to **60** entries when `design.showsWeather` (pure clocks keep 180): `horizonMinutes = design.showsWeather ? 60 : 180`. | `LeapWidget/LeapCheckInWidget.swift` |
| 5 | 🟡 med | 1 | **Custom-photo gate lost the photo on upgrade** — tapping upgrade auto-saved the widget without importing the picked photo. | Reworked into the typed `pendingUpgrade` resume (hardened further in Stage 2, rows 7-10). | `Leap/HomeView.swift` |
| 6 | ⚪ low | 1 | **Record Player rotation looked frozen** — `recordAngle` was minute-derived but that face's timeline isn't rebuilt per-minute. | Set to a constant tilt. | `Shared/LeapWidgetMusic.swift` |
| 7 | 🟡 med | 2 | **Paywall-resume race** — resume depended on the delayed `model.isPro` mirror while `PaywallView` self-dismisses on `store.isPro`, so the pending action could drop. | Typed **single-owner resume**: `pendingUpgrade` enum (`.importPhoto`/`.save`) set before the paywall; the sheet's **`onDismiss`** is sole resumer, reading authoritative `model.storeKit.isPro`. Removed the fragile `onChange(model.isPro)`. | `Leap/HomeView.swift` |
| 8 | 🟡 med | 2 | **Widget savable before async import finished** — Save could persist the OLD wallpaper before `loadTransferable` completed. | **Save disabled while importing** (`isImportingPhoto`). | `Leap/HomeView.swift` |
| 9 | 🟡 med | 2 | **Concurrent photo imports applied out-of-order** — a slow earlier pick could overwrite a newer one / re-enable Save early. | **Versioned imports** (`photoImportToken`): only the latest pick applies + releases the gate. | `Leap/HomeView.swift` |
| 10 | 🟡 med | 2 | **Built-in wallpaper picked mid-import clobbered** by a completing photo import. | `WallpaperStrip.onPick` **bumps `photoImportToken`** + clears the gate, invalidating any in-flight import. | `Leap/HomeView.swift` |

**Reviewer verdicts.**
- **Gemini (Stage 2):** all six Stage-1 fixes confirmed correct, **no regressions**.
- **GPT (Stage 2):** caught the **paywall-resume race** (row 7) and its follow-on photo
  races (rows 8-10). Iterated through re-reviews; final verdict **"no significant issues
  found."**

**Validated non-bugs (justified, no code change).**
- **7-day trial reinstall-bypass — defense is correct.** The trial start is persisted in
  the **Keychain** (`LeapSecureStore`, `kSecAttrAccessibleAfterFirstUnlock`), which
  **survives delete + reinstall** on shipping iOS; `startTrialIfNeeded` checks the
  Keychain before the App-Group default, so a reinstall **cannot** restart the trial. A
  reviewer claim that it resets on reinstall was a **false positive**; its proposed "fix"
  (adding the App Group as `kSecAttrAccessGroup`) would have **broken** persistence —
  **do NOT add it.**
- **Countdown widget** midnight-only refresh is **correct** (it shows whole days).
- **Daily Check-in widget** is intentionally never trial-locked; only surplus *studio*
  widgets are (exempting it would weaken monetization). **By design.**

**Follow-up hardening — Internal build config (post-review).** To keep admin/debug controls
available for QA **without** any public-Release bypass, the debug panel was moved from
`#if DEBUG` to **`#if DEBUG || LEAP_INTERNAL`** and a new **Internal** build configuration
(release-grade + the `LEAP_INTERNAL` flag) plus a shared **`Leap (Internal)`** scheme were
added. The panel now compiles **out** of public Release (verified: `LeapDebugPanelView` /
`leap.debug.plan.override.v1` absent from the fully-linked Release binary, present in Internal)
and **into** Debug + Internal. Details: [build-and-run.md](build-and-run.md) →
"Build configurations: Debug / Release / Internal".

**Deferred — needs a PAID Apple Developer membership (standing TODO).** Weather real data
(WeatherKit entitlement commented out) + StoreKit real purchases can't be validated on the
free signing team; every weather face renders a deterministic placeholder (**expected**,
not a bug). Tracked in [`docs/PLAN.md`](../PLAN.md) -> "Roadmap / backlog"; re-enable
runbooks in [build-and-run.md](build-and-run.md) ("Re-enabling WeatherKit") and
[in-app-purchases.md](in-app-purchases.md).
