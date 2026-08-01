---
name: qa-and-reviews
description: >
  Guide for QA testing, app reviews, and multi-agent code audits. Triggers on keywords like QA, review, audit, functional test, bug hunt, and multi-agent.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# QA & Review Log

The canonical record of **QA and review passes** on your iOS project: the reusable playbook for running one, plus a log of every pass (bugs found -> fixed, reviewer verdicts, validated non-bugs).

> Part of the **[iOS Agent Guide](../ios-agent-guide/SKILL.md)**. Open this when you are asked to
> "audit / review / functional-test the app", when you need to **re-run** the review,
> or when you want the record of what a prior pass found and fixed. Day-to-day status
> lives in `docs/STATUS.md`.

---

## Reusable playbook — multi-agent, 2-stage review

Run this whenever the ask is "validate the whole app / look for bugs / review the
changes".

**Roles.**
- **Orchestrator + fixer (this agent).** Owns triage, applies every fix, runs the builds, updates docs, notifies the user. Reviewers never edit code.
- **Reviewer A**, launched via the `code-review` sub-agent (background).
- **Reviewer B**, launched via the `code-review` sub-agent (background), in parallel with Reviewer A.

**Hard rule:** *no functional bug may be left unfixed.* Non-bugs must be explicitly justified (verified-correct or by-design) — silence is not resolution.

**Stage 1 — functional test.** Prompt both reviewers (rich, self-contained context) to hunt for: UI state synchronization issues, premium-vs-free logic bugs, data persistence bypass, and any crash / force-unwrap / add-edit-delete / onboarding-gating defect. 
The orchestrator also does its own pass + a **baseline build**. Collect -> de-dupe -> triage -> **orchestrator fixes ALL confirmed bugs** -> rebuild -> **notify the user**.

**Stage 2 — code review.** Re-launch the same two reviewers on the **Stage-1 diff** and overall quality. Triage -> fix every valid issue -> re-verify. When a reviewer flags something, fix it and **ask the same reviewer to re-review** until it returns clean. Then **notify the user**.

**Verification rule (do not skip).** Build **BOTH** configs:

```bash
xcodebuild -project com.example.app.xcodeproj -scheme com.example.app -configuration Debug \
  -sdk iphonesimulator \
  -derivedDataPath build/DerivedData build
xcodebuild -project com.example.app.xcodeproj -scheme com.example.app -configuration Release \
  -sdk iphonesimulator \
  -derivedDataPath build/DerivedData build
```

Release is mandatory: `#if DEBUG` / `#else` code paths only compile under `-configuration Release`, so a Debug-only build hides real breakage.

**Notify** after each stage and at final completion (using a local notification mechanism if available):

```bash
# Example notification command
notify_user "<= 100-char one-liner>"
```

**Tips learned.** Reviewers run best in **parallel, background**; keep them idle so you can send follow-ups instead of re-launching (they retain context). The Simulator masks certain UI behaviors like live transparency; some checks need a physical device.

---

## Example Pass log

*(Use this structure to track findings during a review pass)*

### Pass X — functional test + code review

**Bugs found -> fixed**

| # | Sev | Stage | Bug | Fix | File(s) |
|---|-----|-------|-----|-----|---------|
| 1 | 🔴 crit | 1 | **Debug panel shipped in Release** — internal test triggers bypassed production logic. | Wrapped entry point in `#if DEBUG`. | `App/Views/...` |
| 2 | 🟠 high | 1 | **Background states froze** — background update timelines were missing flags. | Added capability flag mapping. | `Widgets/...` |

**Reviewer verdicts.**
- **Reviewer A (Stage 2):** all Stage-1 fixes confirmed correct, **no regressions**.
- **Reviewer B (Stage 2):** caught an async resume race. Iterated through re-reviews; final verdict **"no significant issues found."**

**Validated non-bugs (justified, no code change).**
- **Trial reinstall-bypass defense is correct.** The trial start is persisted in the **Keychain**, which survives delete + reinstall on iOS.
