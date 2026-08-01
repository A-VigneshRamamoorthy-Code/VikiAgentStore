---
name: payment-integration
description: >
  Apple development skill for Payment integration — as-built record. Use this skill when working on payment-integration tasks.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# Payment integration — as-built record

**Status: code complete and validated on hardware. Not yet sellable — four
account-holder steps remain (§8).**

This file is the **record of what was actually built and why**, on branch
`feature/iap-e2e` (worktree `/Users/vignesh/Code/Leap-iap`), after the paid Apple
Developer Program membership was obtained on 2026-07-29.

It is deliberately separate from
[`in-app-purchases.md`](in-app-purchases.md), which is the **implementation spec**
(how the code is structured, where the anchors are, how to extend it). Read this
file to learn **what state the integration is in, what was changed, what was
discovered the hard way, and what is left**. Read that one to change the code.

---

## 1. Where it stands

| | |
|---|---|
| Branch | `feature/iap-e2e` (7 commits, not yet merged to `main`) |
| Build | Release + Internal, app + widget extension, clean |
| Tests | **21 tests, 11 skipped, 0 failures** (`LeapIAPTests`) |
| Device | Installed + launched on Viki's iPhone `00008150-0014746214F2401C` |
| App Store Connect | App + **3 products**, all `READY_TO_SUBMIT` |
| Sandbox purchase | Reaches Apple's "Confirm with Side Button" sheet |
| Blocking to sell | Paid Applications Agreement, sandbox tester, a build, legal URLs |

**7 commits, oldest first:**

| Commit | What |
|---|---|
| `4aef757` | Hardening pass — 11 audit findings, `LeapIAPTests` target, legal views |
| `5efbaf8` | Live ASC products + environment-aware subscription group id |
| `4772a89` | Paywall: live list price, contrasting table, single-line subtitles |
| `e2c0ffd` | Per-territory reference pricing so the discount reads 23% worldwide |
| `fbdc67f` | Catalog moved into the comparison table |
| `1fe9aa2` | Catalog rows contrast ("Limited" vs "All"), free-for-everyone note dropped |
| `12052f0` | Counts dropped from the catalog rows |

**17 files changed**, +2184 / -152. The substantial ones:
`Leap/LeapStoreKitManager.swift`, `Leap/PaywallView.swift`,
`Shared/LeapEntitlements.swift`, `Leap/HomeView.swift` (Settings),
`LeapIAPTests/LeapIAPTests.swift` (new, 532 lines),
`Leap/LeapLegalView.swift` (new, 318 lines), `Leap.storekit`,
`Leap.xctestplan` (new), and both schemes.

---

## 2. What was wrong, and what fixing it looked like

The starting point was a paywall wired to StoreKit that had **never been able to
transact**, so nothing downstream of a purchase had ever run. Eleven findings,
all now closed and all covered by tests.

### Blockers (would have failed review or made purchase impossible)

**`Leap (Internal).xcscheme` pinned `Leap.storekit` on the Run action.** The
Internal configuration is the one used for QA and TestFlight, and a scheme-pinned
StoreKit configuration file **replaces the real App Store** — so every Sandbox
purchase attempt on a real device was being served by a local synthetic store and
could never produce a real transaction. The pin was removed from Internal and
kept on the `Leap` scheme, where local development wants it.

**No Privacy Policy or Terms of Use (guideline 3.1.2).** A subscription must
disclose both, in-app and in the App Store listing. `Leap/LeapLegalView.swift`
renders both in-app (linked from the paywall and Settings), and
`docs/legal/{privacy-policy,terms-of-use}.html` are ready to host for the ASC
metadata fields.

### High

**`debugProOverride` was sticky forever.** Once the debug panel toggled the plan,
the override pinned the entitlement for good — so on a Debug or Internal build a
**real purchase could never unlock anything**, which is exactly the build QA uses
to test purchases. It is now tri-state (`Bool?`) with an explicit "Use real
StoreKit" action that clears it.

**Products loaded exactly once, in `init`.** A cold launch with no network left
the paywall permanently priceless, with every Buy tap failing for the rest of the
session. There is now a reload on paywall appear, a one-shot retry inside
`purchase(id:)`, an explicit unavailable state that **disables** the Buy button,
and a "Try again" control. It never shows a placeholder price as if it were real.

**Restore from Settings was silent** and leaked its error into the next paywall
presentation. It now has a spinner and an alert that always reports an outcome,
including the "nothing to restore" case, and the paywall clears `errorMessage` on
appear.

**No way to manage or cancel a subscription in-app.** Added
`.manageSubscriptionsSheet`, shown to subscribers in Settings.

**The comparison table claimed designs, styles, wallpapers and live data were
Premium-only.** They are not — the code gates only widget count, surplus lock,
editability and photo count. Claiming otherwise is a 2.3.1 metadata risk. The
table now matches the enforced gates (see §5 for where it ended up).

### Medium

**Billing retry / grace period was invisible**, so a subscriber whose renewal
failed would silently lose access with no path to fix it.
`Product.SubscriptionInfo.Status` is now observed into `hasBillingIssue`, surfaced
in Settings.

**`canAddCustomPhoto` ignored the 7-day trial** while every other gate honoured
it. Now trial-aware.

**`withTimeout` was broken** — it returned the timeout's result rather than
whichever finished first, so a slow-but-successful call was reported as a failure.
Rewritten around a `FirstResult` actor, and every StoreKit call is bounded.

---

## 3. The test target

`LeapIAPTests` (new target, registered in the hand-authored `project.pbxproj` and
in `Leap.xctestplan`) proves the chain **purchase → entitlement → App-Group mirror
→ unlock**, plus restore, refund revocation and expiry. Two classes:

- **`LeapIAPTests`** — 11 `SKTestSession` tests: catalog load, unavailable
  catalog, lifetime and monthly purchase, entitlement surviving a fresh manager,
  restore (with and without anything to restore), refund revocation, subscription
  expiry.
- **`LeapEntitlementChainTests`** — 10 pure-logic tests that need no store:
  App-Group mirroring, product identifiers, the `Leap.storekit` ↔ code contract,
  every enforced gate under Pro and under trial, the lock hitting the **newest**
  surplus widgets, the trial not being revivable by winding the clock back, the
  debug override being clearable, the paywall refusing to price an unavailable
  catalog, and restore always reporting an outcome.

Run it with the `Leap` scheme (there is no `LeapIAPTests` scheme):

```bash
xcodebuild -project Leap.xcodeproj -scheme Leap \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' test
```

**The 11 skips are expected.** See §6.

---

## 4. App Store Connect — created and priced via the REST API

`POST /v1/apps` is **403 for API keys** (the app record must be created in the
UI), but everything after that was automated with
`/tmp/asc/asc_api` (built from `scripts/asc_api.swift` in the NotchPaw repo;
`ASC_KEY_ID=ZCT5D865V5`, `ASC_ISSUER_ID=b75bbafc-4c57-4d16-803f-25c367d01886`).

| Resource | ID | Price |
|---|---|---|
| App "Leap Widgets" | `6796248408` | — |
| Lifetime unlock (non-consumable) | `6796248820` | 9.99 USD/EUR/GBP |
| Subscription group "Leap Premium" | `22274535` | — |
| Monthly subscription | `6796249550` | 0.99/mo, 175 territories |
| **List-price reference** (never sold) | `6796395835` | ~12.99, per territory |

All three are `READY_TO_SUBMIT`, with review screenshots uploaded via the
three-step reserve → `PUT` → `PATCH` flow (scripted as
`scripts/asc_iap_screenshot.sh`). The shipped capture is
`docs/store/screenshots/iap/paywall-plans.png` — **re-captured** after the lifetime
price moved to $9.99, because the original still showed **$8.99**. See
[in-app-purchases.md](in-app-purchases.md) §12.3b for the re-capture recipe.

---

## 5. The paywall, and how its numbers stay live

The rule throughout: **no price, count or percentage is written down in the app.**

### Pricing

`9.99` and `12.99` appear nowhere in the source. The charged price is
`LeapProduct.lifetime`; the struck-through reference is a **third product**,
`LeapProduct.lifetimeListPrice`, and the "23% OFF" badge is computed from the two.

Why a third product: **StoreKit has no "was" price for a non-consumable.** Apple's
only discount primitives — introductory and promotional offers — are
subscription-only. A second product is the only source that is simultaneously
live, correct in every currency, and re-pricable in App Store Connect after launch
with no app update.

Safety rails, because a purchasable product that grants nothing would be a bug:

- It is excluded from `LeapProduct.all` (the entitling set) and appears only in
  `allFetchable`.
- `performLoad()` splits it into `lifetimeListProduct` before the paywall ever
  sees the array, so it cannot be rendered as a plan or bought.
- `lifetimeReference` falls back to 12× the monthly price, then to **nothing** —
  a paywall that cannot prove a saving must not claim one.
- `lifetimeSavingsPercent` rounds **down** and returns `nil` below 5%, so the
  badge can never overstate the discount.

**Consequence: the price is fully ASC-configurable post-launch.** Moving the list
price to 14.99 needs no code change; the badge recomputes to 33%. If the charged
price is ever raised above the reference, the strikethrough hides itself rather
than rendering a negative discount.

### The comparison table

```
WHAT YOU GET                    FREE      PREMIUM
Widget designs                  Limited   All
Widget styles                   Limited   All
Saved widgets                   4         Unlimited
Custom photo wallpapers         1         Unlimited
Extra widgets stay unlocked     x         check
Edit every saved widget         x         check
```

Two things to preserve:

**Every row below the catalog rows is a gate the code really applies** —
`freeWidgetAllowance`, `freePhotoAllowance`, the surplus lock, and editability.
Nothing else is gated, so nothing else belongs here.

**The catalog cells stay vague on purpose.** "Limited" describes the *tier*: a
free user is capped at four saved widgets, so only four designs and styles can be
in use at once. Design and style **picking is never gated** and nothing is hidden
from a free user in Browse or the Add sheet. Naming a count ("4 designs") would
claim a per-design paywall the code does not implement, which a reviewer can
disprove in one tap — a 2.3.1 risk. Equally, do not restore the earlier "All 67 /
All 67" form: identical cells read as "free gets everything" and make the upsell
look pointless.

Counts that *are* shown — the "3,500+ unique widgets" capsule and the 67 badge —
come from `LeapCatalogStats`, the same source as the Browse header, so they cannot
drift.

---

## 6. Traps discovered here — do not relearn these

**⛔️ The FB22237318 skip probe must not be "the catalog is empty".**
`SKTestSession` is broken on iOS 26.3–26.5 simulators (Apple bug FB22237318):
requests **fall through to the real store** instead of failing. Once the ASC
records went live, that fall-through started returning *real* products, so the
"empty catalog" probe stopped skipping and the suite ran against **production** —
where it hung for **30 minutes** on a Sandbox sign-in dialog that no test can
dismiss. That dialog outlives the killed test host and blocks the simulator until
reboot. The probe now checks the monthly product's **subscription group id**
against the one in `Leap.storekit`, which the real store can never match.

**⛔️ A subscription needs a price in EVERY available territory** to leave
`MISSING_METADATA`. A non-consumable price *schedule* auto-equalizes from a base
territory; a subscription does not. Chasing the review screenshot as the blocker
wasted a cycle — it was the 174 missing prices.

**⛔️ `subscriptionAvailabilities` must exist BEFORE `POST /v1/subscriptionPrices`**,
or the API returns a 409 that misleadingly blames the price point.

**⛔️ The price-point "tier" index is NOT aligned across territories.** A price
point id is base64url of `{"s":"<productId>","t":"<territory>","p":"<tier>"}` and
is trivially constructible — but the same `p` means different money in different
storefronts. Pinning both products to "matching" tiers looked right in USD, EUR
and GBP and silently produced a **list price BELOW the charged price in India**
(tier 10142 = ₹479 against a ₹999 unlock). Letting Apple auto-equalize is wrong
the other way: EUR price points are VAT-inclusive, so a $12.99 base equalizes to
**€14.99** and the badge read 33% off instead of 23%.

The reference product is therefore priced **per territory**: take each
storefront's actual charged price and select the nearest price point **at or
above** `charged × 1.3003`. Result: 23–25% off in all 175 storefronts —
12.99/9.99 in USD, EUR and GBP; ₹1299/₹999; ¥1960/¥1500. Because the product is
never purchased, pinning it has **zero revenue impact**; it only controls what the
strikethrough reads.

**⚠️ The subscription group id differs between the synthetic and real stores.**
`refreshSubscriptionStatus()` reads it off the loaded product
(`monthly?.subscription?.subscriptionGroupID`) rather than the constant in
`LeapEntitlements`, which is now only a fallback.

**⚠️ A Simulator build fetches LIVE App Store prices** (its client environment is
Sandbox, so it hits the real Media API) — even before the Paid Applications
Agreement is Active. Useful for checking pricing without a device.

**⚠️ ASC API paging.** `filter[territory]` with `limit=1000` on `pricePoints`
returns **HTTP 500**; use 200 there, or 8000 on the unfiltered collection and
follow `links.next` (18 pages, ~140,000 points). Inline `included` resources need
the `"${localId}"` form. Localization limits: name ≤30, description ≤45.

**⚠️ Sandbox testers are NOT creatable via the API** — ASC UI only. Zero testers
is why *Settings → Developer* shows no Sandbox row.

**⚠️ `xcrun devicectl` needs the phone UNLOCKED to launch** (`FBSOpenApplication
ErrorDomain error 7` / "Locked"). Install works while locked; only the launch
fails.

**⚠️ Do not drive the Simulator with CGEvent taps.** This is a shared machine —
the Simulator lost focus mid-sequence and a click landed in the user's browser.

---

## 7. Judgement calls worth revisiting

**A never-purchasable reference IAP is unusual.** A `reviewNote` explaining it is
attached to `6796395835`. If App Review objects, deleting the product is safe:
`lifetimeReference` falls back to 12× monthly, then hides the strikethrough
entirely. No code change needed.

**⚠️ OPEN — "Limited" against "All" for designs and styles (2.3.1).** Two of the
three reviewers flagged the two catalog rows in `comparisonRows` as an accurate-
metadata risk: a reviewer can select any of the 67 designs, in any of the 4 styles,
on a free account, in one tap. The defence is that "Limited" describes the *tier*
(a free user holds four saved widgets, so only four designs can be in use at once)
rather than claiming per-design gating, and the cells deliberately name no count for
exactly that reason. **This wording is an explicit product decision by the owner**,
made after the risk was raised, so it has been left as-is. If review does object,
the two safe rewrites are "Designs in use → 4 / Unlimited" or dropping both rows.

**FIXED — the trial now starts only after its term is disclosed (3.1.1).** It used
to start in `LeapViewModel.init`, before the first user-visible statement of the
7-day term (the onboarding spin wheel), so a user who abandoned onboarding burned
trial days having never been told the duration. `beginTrialIfNeeded()` now runs from
**`completeOnboarding()`**, the single exit from the flow.

This was assessed as an onboarding restructure and it is not - **nothing observable
changes during onboarding**, because an unstarted trial gates identically to an
active one for a brand-new user: `isFreeWidgetLocked` needs rank >= 4 (they hold 0
widgets), `canAddCustomPhoto` needs count >= 1 (they hold 0), `trialDaysRemaining`
already reports the full length before the clock starts, and the paywall is gated on
`hasCompletedOnboarding` so it cannot appear mid-flow. The spin wheel grants nothing
- it reads the constants and sets a flag - so its "prize" was always theatre for a
trial that had already started.

Two things to keep in mind if you touch this:
- **`init` still backfills** when `hasCompletedOnboarding` is already true. Without
  it, installs that finished onboarding under an older build would never start a
  trial. Do not delete that branch.
- **The spin page is conditional** (`showsSpinPage` is false once spun), so on that
  path `completeOnboarding()` fires without restating the term - harmless, because
  having spun implies a trial already ran and the keychain latch refuses a second.

**A lapsed subscriber's placed widgets lock past the free 4 — but only after the app
is next opened.** The extension **does** read the entitlement, through the App-Group
`isPro` mirror (`isProCached` is the default argument to `isSavedWidgetLocked`); what
it cannot do is *observe* the lapse, because only the app can call StoreKit. Until
Leap is next launched the mirror is stale and every placement keeps rendering. Trial
expiry is exact by contrast — the extension computes it from App-Group inputs alone.
The soft landing (oldest 4 survive, rest blur behind a lock) is deliberate — see
[`in-app-purchases.md`](in-app-purchases.md) §6.5c before "fixing" it.

---

## 8. Outstanding — account holder only

Nothing here can be automated or done by an agent.

1. **Paid Applications Agreement.** Individual → Contact Info, personal bank
   account, **W-8BEN**. Until it is Active, purchases cannot complete in
   production. This is the one true blocker on revenue.
2. **Create a Sandbox tester** in the ASC UI (not API-creatable).
3. **Upload a build.** The app has **0 builds**, which is why Apple's payment
   sheet shows a blank icon — it fetches artwork from the App Store listing. Not
   a code bug.
4. **Host `docs/legal/*.html`** and paste the URLs into the ASC metadata fields.

---

## 9. Review round (2026-07-30) — three reviewers, six real bugs

The whole payment surface was re-reviewed by three independent agents (one Gemini
code pass, one GPT policy pass, one Opus code pass). **Their verdicts disagreed, and
the disagreement was the signal**: the pass that reported "everything is clean" was
wrong about the legal copy, and the two most expensive bugs below were each found by
exactly one reviewer. Do not treat a single clean review as sufficient here.

### 9.1 Bugs found and fixed

1. **Charged but not entitled.** `refreshEntitlements()` was the *only* path that set
   `isPro`, and it returns silently on timeout — so a customer whose network stalled
   right after paying was charged and left on the free tier until some later refresh
   happened to succeed. `purchase(_:)` and the `Transaction.updates` listener now call
   **`grant(from:)`** on the verified transaction *before* the refresh. **This is the
   one to remember: every other bug here costs trust, this one costs money.**
2. **Restore lied to paying customers.** A scan that timed out fell through to
   "No previous purchases were found" — the exact sentence that makes a user demand a
   refund. `refreshEntitlements()` now returns `RefreshOutcome { refreshed, timedOut }`
   and restore reports the real cause (telemetry reason `"timeout"`).
3. **A stale refresh could revoke a fresh entitlement.** Refreshes run on detached
   workers and are unserialized — and the StoreKit payment sheet itself takes the scene
   through `.inactive`, firing a foreground refresh that races the purchase. A
   **`refreshGeneration`** stamp now drops results from superseded runs.
4. **Double pay.** `purchase(_:)` did not check ownership; tapping Lifetime while
   already entitled went straight to Apple. It now re-checks `isPro` against StoreKit
   and refuses.
5. **The trial latch did not mirror to the App Group.** Reinstalling wipes the App
   Group but **not** the keychain, so a user who wound the clock back and reinstalled
   had an expired trial treated as **active in every placed widget** while the app said
   otherwise. `hasTrialEndedLatch` now writes the mirror whenever it reads the keychain.
6. **Cross-currency discount maths.** `lifetimeReference` compared two `Decimal`s
   without checking they were the same currency. It now requires
   `priceFormatStyle.currencyCode` to match before computing a percentage.

### 9.2 Copy corrections shipped in the same pass

- **"unlimited photo wallpapers"** oversold Premium. There is exactly **one** custom
  photo file (`leap_custom_wallpaper.png`); `freePhotoAllowance` counts *widgets using
  it*. The row is now **"Widgets using your photo"**.
- **"Cancel anytime"** was shown under the Lifetime plan, which is a non-consumable.
  The reassurance line is now plan-specific.
- **Ask-to-Buy / SCA** (`.pending`) rendered as **"Something went wrong"**. It now has
  its own non-error `noticeMessage` and a "Purchase pending" alert.
- **Privacy copy** claimed "Nothing is uploaded, tracked or sold", "no servers holding
  your data" and "deleting the app removes everything". All three were false given
  Firebase/GA4, Firestore feedback and the deliberately-persisted keychain trial latch.
  Corrected in `OnboardingPrivacyPage.swift`, `LeapLegalView.swift` **and the generated
  `docs/legal/*.html`** — those three must be changed together.

### 9.3 Raised and deliberately NOT changed

- **"Limited" / "All" catalog rows** — see §7 and `in-app-purchases.md` §12.6.
- **Trial starts before it is disclosed** — raised here, then **fixed** once it
  turned out to be a two-line move rather than an onboarding restructure; see §7.
- **Analytics without a consent prompt (5.1.1(ii))** — anonymous, first-party, no IDFA
  and no ATT-scope tracking, so a prompt is not required; out of scope for payments.
