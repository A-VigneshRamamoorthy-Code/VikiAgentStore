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
`leapvpn://trialOffer`, and `leapvpn://trialEnded` followed by `leapvpn://connect?region=in`.

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
