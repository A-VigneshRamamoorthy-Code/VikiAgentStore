"""App Review notes for Leap VPN, one text per platform.

Push them (with the demo account, which is never stored in git) with:

    cd plugins/azure/skills/vpn/mac
    LEAP_DEMO_USER=... LEAP_DEMO_PASS=... python3 ../appstore/review_notes.py
"""

COMMON_TOP = """\
Leap VPN is not a VPN service. The developer runs no VPN servers, has no user accounts and never sees, routes or stores user traffic. The app is a client and provisioner for infrastructure the user owns.

HOW IT WORKS
1. The user signs in with their own Microsoft account (Microsoft identity platform, OAuth with PKCE). The app calls Azure Resource Manager directly from the device and creates WireGuard servers in the user's own Azure subscription, in regions the user picks.
2. WireGuard keys are generated on the device; the private key stays in the Keychain.
3. On Connect the app starts that server; on Disconnect it deallocates it, so nothing runs or bills while the VPN is off. A watchdog on the server also stops it if no device has been connected for a few minutes.
4. Azure bills the user directly. We receive no money from Azure usage.

GUIDELINE 5.4
Leap VPN offers no VPN service run by the developer. It is closer to a WireGuard client plus a cloud-console app: every server belongs to the user, sits in the user's cloud account and is administered by the user. The developer cannot reach the servers or the traffic and collects no data (App Privacy: Data Not Collected). NEPacketTunnelProvider is used only for the tunnel to the user's own server. The optional DNS ad and tracker filter runs on the user's own server and does not log queries.

DEMO ACCOUNT - ONE STEP BEFORE USING THE APP
The app needs a Microsoft account with an active Azure subscription, because it creates the server inside that subscription. The demo account in the Sign-In Information fields is a Microsoft account without a subscription yet.
Before opening the app, please:
a) Go to https://portal.azure.com and sign in with the demo account.
b) Activate the Azure free account (US$200 free credit) at https://azure.microsoft.com/free and add a payment card when Microsoft asks for it. Microsoft uses the card only to verify identity; the free account is not charged.
The developer could not attach a payment card to the test account for security reasons, so this step has to be completed by the reviewer. If it is skipped, the app shows "This Microsoft account doesn't have access to Azure yet" with an Open Azure portal button.
"""

IOS_STEPS = """\
HOW TO REVIEW ON IPHONE
1. Open Leap VPN and swipe through the 4 onboarding pages.
2. Tap Sign in with Microsoft and sign in with the same demo account.
3. Select India in the location list and tap Add 1 location. The first build takes about 2 minutes.
4. Tap Connect. The subscription screen with the 2-week free trial appears; start the trial (sandbox), confirm the launch price on the second sheet, then allow the VPN configuration when iOS asks.
5. The VPN connects and the public IP becomes Indian. Tap Disconnect and the server stops (deallocates).

SUBSCRIPTION
Leap VPN Plus (US$11.99/month or US$79.99/year, one group shared by iPhone and Mac) starts with a 2-week free trial (introductory offer). Launch price: promotional offers launch_monthly (US$0.99/month for 12 months) and launch_yearly (US$9.99 for the first year) (server-signed). New subscribers confirm the trial, then a second App Store sheet redeems the launch price from the first renewal; returning subscribers get it in one purchase. If that sheet is dismissed, a Lock in price button stays at the top left. Sign-in and setup are free; connecting needs the trial or a subscription. The subscription screen is also reachable from the Upgrade button at the top left of the home screen and shows regular and launch prices, renewal terms, Restore Purchases, Terms of Use and Privacy Policy.
"""

MAC_STEPS = """\
HOW TO REVIEW ON MAC
1. Open Leap VPN (a window plus a menu bar icon; reopen the window from either the menu bar icon or the Window menu).
2. Go through the 4 onboarding pages.
3. Click Sign in with Microsoft and sign in with the same demo account in the sign-in window that opens.
4. Select India in the location list and click Add 1 location. The first build takes about 2 minutes.
5. Click Connect. The subscription screen with the 2-week free trial appears; start the trial (sandbox), confirm the launch price on the second sheet, then allow the VPN configuration when macOS asks.
6. The VPN connects and the public IP becomes Indian. Click Disconnect and the server stops (deallocates).

SUBSCRIPTION
Leap VPN Plus (US$11.99/month or US$79.99/year, one group shared by Mac and iPhone) starts with a 2-week free trial (introductory offer). Launch price: promotional offers launch_monthly (US$0.99/month for 12 months) and launch_yearly (US$9.99 for the first year) (server-signed). New subscribers confirm the trial, then a second App Store sheet redeems the launch price from the first renewal; returning subscribers get it in one purchase. If that sheet is dismissed, a Lock in price button stays at the top left. Sign-in and setup are free; connecting needs the trial or a subscription. The subscription screen is also reachable from the Upgrade button at the top left of the main window and shows regular and launch prices, renewal terms, Restore Purchases, Terms of Use and Privacy Policy.
"""

FOOTER = """\
External services: Microsoft identity platform (sign-in) and Azure Resource Manager (the user's own servers). No regional differences in features. No user-generated content, no ads, no tracking (no ATT prompt).

Thank you - Vignesh Ramamoorthy, Sololeap (sololeapinc@gmail.com)
"""

NOTES = {
    "IOS": "\n".join([COMMON_TOP, IOS_STEPS, FOOTER]),
    "MAC_OS": "\n".join([COMMON_TOP, MAC_STEPS, FOOTER]),
}

CONTACT = {
    "contactFirstName": "Vignesh",
    "contactLastName": "Ramamoorthy",
    "contactEmail": "sololeapinc@gmail.com",
    "contactPhone": "+353899481187",
}

VERSIONS = {
    "IOS": "699af78f-6a69-4abc-8e34-9e123932cb71",
    "MAC_OS": "454915d6-fe56-44a7-84fa-78d7449c5950",
}

for bad in ("iPhone", "iOS", "tap", "Tap", "Face ID", "swipe"):
    assert bad not in NOTES["MAC_OS"].replace("Mac and iPhone", ""), bad
for plat, text in NOTES.items():
    assert len(text) < 4000, (plat, len(text))


if __name__ == "__main__":
    import os

    exec(open("/tmp/asc.py").read())
    user, pw = os.environ["LEAP_DEMO_USER"], os.environ["LEAP_DEMO_PASS"]
    for plat, vid in VERSIONS.items():
        attrs = {**CONTACT, "notes": NOTES[plat], "demoAccountRequired": True,
                 "demoAccountName": user, "demoAccountPassword": pw}
        cur = a.call("GET", f"/appStoreVersions/{vid}/appStoreReviewDetail").get("data")  # noqa: F821
        if cur:
            a.call("PATCH", f"/appStoreReviewDetails/{cur['id']}",  # noqa: F821
                   {"data": {"type": "appStoreReviewDetails", "id": cur["id"], "attributes": attrs}})
        else:
            a.call("POST", "/appStoreReviewDetails", {"data": {  # noqa: F821
                "type": "appStoreReviewDetails", "attributes": attrs,
                "relationships": {"appStoreVersion": {"data": {"type": "appStoreVersions", "id": vid}}}}})
        print(plat, "review detail set,", len(NOTES[plat]), "chars")
