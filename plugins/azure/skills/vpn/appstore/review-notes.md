# App Review notes — Leap VPN (iOS and macOS, one app record 6834297538)

The notes are kept per platform in [`review_notes.py`](review_notes.py), because the Mac reviewer
must not be told to tap a phone. Running it asserts each text is under the 4000-character cap, then
pushes the notes, contact details and demo account to both `appStoreReviewDetail` records:

```bash
cd plugins/azure/skills/vpn/mac
LEAP_DEMO_USER=... LEAP_DEMO_PASS=... python3 ../appstore/review_notes.py
```

The demo account credentials are passed through the environment only and are never committed.
The demo Microsoft account has no Azure subscription, so the notes ask the reviewer to activate the
Azure free account (adding a card) first and explain why the developer could not attach a card.
