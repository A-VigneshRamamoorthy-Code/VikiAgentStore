# Leap VPN — In-App Purchase setup (App Store Connect, app 6834297538)

Universal purchase: one app record (bundle com.sololeap.leapvpn) with iOS + macOS versions → one subscription unlocks both.

Subscription group: **Leap VPN Plus** (id 22578704)

| Product ID | ASC id | Period | US price | Intro offer | Territories |
|---|---|---|---|---|---|
| com.sololeap.leapvpn.plus.monthly | 6834781392 | 1 month | $0.99 | Free trial, 2 weeks, all 175 storefronts | 175 (equalized) |
| com.sololeap.leapvpn.plus.yearly  | 6834781509 | 1 year  | $9.99 | Free trial, 2 weeks, all 175 storefronts | 175 (equalized) |

- Apple only offers fixed trial lengths (3 days, 1 week, 2 weeks, 1 month…); 15 days is not available → 2 weeks.
- Family Sharing: off (enabling later is irreversible, so left off deliberately).
- Manual step before first submission: in App Store Connect → the version page → "In-App Purchases and Subscriptions", add both subscriptions to the version (web UI only — the API cannot do this).
- Each subscription needs a review screenshot (paywall) — uploaded via API if present; see handoff.
