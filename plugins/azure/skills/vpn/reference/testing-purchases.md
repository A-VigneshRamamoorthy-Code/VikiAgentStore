# Testing Leap VPN Plus locally

Leap VPN Plus is an auto-renewing subscription with a 2-week free trial (an App Store
introductory offer). Here are three ways to see the trial offer, the paywall and the
trial-ended upsell without paying anything.

## 1. Debug and local builds: the Purchase testing card

Debug builds (Xcode **Run**, `swift build`, and `LEAPVPN_CAPTURE=1 ./mac/build.sh`) have an
extra **Purchase testing** card at the bottom of **Settings**. The card shows the current
entitlement, whether you can still take the trial, and how many products loaded. It has four
buttons:

| Button | Shows |
|---|---|
| Trial offer | "2 weeks free, on us", the screen a first Connect opens |
| Trial ended | "Your free trial has ended", the screen Connect opens after the 14 days |
| Paywall | The Upgrade screen |
| Reset | Clears the preview and "already shown" flags and asks StoreKit again |

The previews only change what this run of the app displays. Nothing is bought. Release,
TestFlight and App Store builds compile the card out.

The same screens can be opened by URL, after
`defaults write com.sololeap.leapvpn AllowURLControl -bool true`:
`leapvpn://trialOffer`, `leapvpn://trialEnded` (opens the trial-ended screen directly),
`leapvpn://trialEnding?s=240` (a cancelled trial that ends in 240 seconds; see section 5) and
`leapvpn://closesheet`.

## 2. Real purchases in a local build (sandbox)

- **iPhone, from Xcode.** The LeapVPN scheme's Run action uses `ios/LeapVPN.storekit`, so
  purchases are local and free. Use **Debug › StoreKit › Manage Transactions** to expire or
  refund a purchase, and to replay the trial. To watch the 14-day trial end within
  minutes, open the `.storekit` file and choose a faster **Editor › Time Rate**.
- **Mac (`./mac/build.sh`) and the iOS simulator.** Purchases go to Apple's sandbox. When you
  subscribe you're asked to sign in with a **Sandbox Apple Account**. Create one in App Store
  Connect › Users and Access › Sandbox. To take the trial again, clear that tester's purchase
  history there, or create a new tester.

## 3. TestFlight

TestFlight builds also use the sandbox, with your own Apple Account, and are never charged.
Subscriptions renew on an accelerated schedule, so the trial ends long before 14 days. This is the
end-to-end check of the trial-ended upsell on a real device.

## 4. Automated StoreKit tests

`./ios/test.sh <simulator-udid>` runs `ios/Tests/StoreTrialTests.swift` against
`ios/LeapVPN.storekit` with StoreKitTest (no Apple Account needed):

| Test | Checks |
|---|---|
| `testTrialEndsWithoutRenewing` | First purchase is the 2-week trial; when it lapses Connect shows "Your free trial has ended" |
| `testPaidPeriodEndingIsNotATrialEnding` | A lapsed paid period shows the regular paywall, not the trial-ended copy |
| `testPurchaseLiftsRestrictions` | Subscribing removes every restriction; Connect goes straight through |
| `testCancellingAfterPaidMonthsRestoresRestrictions` | After paid renewals, cancelling (auto-renew off) keeps Plus until the period ends, then the gate returns and a live session is ended |
| `testRefundRestoresRestrictions` | A refund revokes Plus immediately |
| `testTrialOnlyOnceEvenAfterReinstall` | Wiping local state and rebuilding the store from StoreKit alone does not bring the trial back: eligibility comes from the Apple Account (`isEligibleForIntroOffer`), never from the device |

## 5. The trial ending during a live session

When Plus ends (the trial runs out without converting, a cancelled subscription expires, a
refund), a connected VPN disconnects, even if the app is suspended or quit:

- The app passes the Plus expiry and whether it is set to renew to the tunnel extension at
  start, and sends it again on every renewal (provider message `plus:<epoch>:<0|1>`).
- At the expiry the extension asks StoreKit itself. A verified entitlement, including one in
  billing grace, keeps the tunnel up and moves the deadline. If none remains it reads the
  verified renewal intent: a cancelled subscription stops the tunnel at once. One still set to
  renew gets up to 6 hours, rechecked every 15 minutes, for the renewal to reach the device.
- While the app runs it also rechecks 5 seconds after the expiry and disconnects. When the
  tunnel ends for this reason the app does not reconnect it. It shows "Your free trial has
  ended", and the next Connect opens the trial-ended subscription screen.
- With no handshakes the server deallocates as usual.
- Starts from the system VPN settings never work, because the WireGuard key is passed only by
  the app at start.

To watch it on a debug Mac build, open `leapvpn://trialEnding?s=240`, then
`leapvpn://connect?region=in`. The tunnel log
(`log show --predicate 'subsystem == "com.sololeap.leapvpn.tunnel"'`) shows
`plus ended at …; stopping tunnel` within 30 seconds of the deadline.
