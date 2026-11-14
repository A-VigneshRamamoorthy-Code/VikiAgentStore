# Leap VPN store screenshots — capture provenance

Regenerate with `python3 make_frames.py` (writes screenshots/iphone 1320x2868, screenshots/mac 2880x1800, RGB).
Raw captures are not committed; recapture as follows.

iPhone (/tmp/cap, iPhone 17 Pro Max simulator 2D5AA198…, 1206x2622, en_US):
- home.png: seeded scrubbed setup.json (5 regions ae, ie, in, jp, uk; no account IDs) + real history.json; region `in`;
  launch `-LeapOpenURL "leapvpn://plusPreview"` (subscriber UI, so no Upgrade button).
- locations.png: `leapvpn://plusPreview|leapvpn://preview?step=locations`.
- usage.png: `leapvpn://plusPreview|leapvpn://history`.
- ob1/ob2/ob3.png: setup.json moved aside, `-LeapOnboardPage 1|2|3` (privacy, blocking, pay-while-connected).
Mac (/tmp/mcap, cacheDisplay snapshots via files/leapshot.sh `<hook> <name>-cache`):
- home.png (`closesheet`), settings.png (`settingsSheet`, cropped below the account card), usage.png (`history`).
Currency shows ₹ because the real usage history is billed in INR. Nothing is retouched.
