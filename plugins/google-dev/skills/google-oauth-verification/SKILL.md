---
name: google-oauth-verification
description: >
  How to get Google Sign-In and Google OAuth scopes approved by Google's verification
  review. Covers choosing the narrowest scope, sensitive vs restricted tiers and the
  CASA security assessment, the privacy-policy disclosures Google requires, recording a
  demo video that is not rejected, scope matching between app and Cloud Console, and
  how to reply to a rejection. Use when submitting an app for OAuth/data-access
  verification, adding Google Sign-In or Drive/Gmail/Calendar scopes, filling in the
  OAuth consent screen or Google Auth Platform, or responding to a verification
  rejection email.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "1.0.0"
---

# Getting Google Sign-In access approved

Google's OAuth verification is a **correspondence with a human reviewer**, not a form
submission. Most delays come from three avoidable mistakes: asking for a broader scope
than you need, a privacy policy that says what you collect but not how you protect it,
and a demo video that shows sign-in rather than the feature the scope exists for.

Read this page, then open only the module you need.

| Module | Open it when |
|---|---|
| [`scopes.md`](scopes.md) | Choosing a scope, or checking whether CASA applies |
| [`privacy-policy.md`](privacy-policy.md) | Writing or fixing the policy |
| [`demo-video.md`](demo-video.md) | Recording, editing or verifying the video |
| [`rejections.md`](rejections.md) | A rejection email arrived; replying |

---

## Decide the tier first

The tier of the **most sensitive scope you request** sets the cost of the whole
project. Establish this before writing code.

- **Non-sensitive** (`openid`, `userinfo.email`, `userinfo.profile`, `drive.file`) —
  brand verification at most. Days.
- **Sensitive** — review with a privacy policy and a demo video. Weeks.
- **Restricted** (`drive`, `drive.readonly`, most Gmail scopes) — all of the above plus
  Limited Use compliance and, in most public-app cases, an **annual third-party CASA
  security assessment**. Months, and real money.

Dropping from a restricted scope to `drive.file` can remove the video, the assessment
and the annual renewal. It is almost always worth an afternoon of design work to try.

See [`scopes.md`](scopes.md) for the classification table and the exemptions.

---

## The workflow

1. **Pick the narrowest scope that works** and write down, concretely, why each
   narrower one does not. You will paste this into the submission and the reply.
2. **Verify your domain** in Google Search Console.
3. **Configure the consent screen** — Google Auth Platform → Branding, Audience, Data
   access. App name, logo, homepage, privacy policy, authorised domains.
4. **Publish the privacy policy** with the Limited Use statement *and* a data
   protection section — see [`privacy-policy.md`](privacy-policy.md).
5. **Record the demo video** showing the consent screen with scopes readable and the
   feature genuinely in use — see [`demo-video.md`](demo-video.md).
6. **Reconcile scopes** between the app's actual request and the Console list, in both
   directions, and **save**.
7. **Submit**, then watch the email thread on the project owner's account.
8. **On rejection**, fix, verify, and **reply to the email** — see
   [`rejections.md`](rejections.md).

Expect **3–7 business days** per round, longer with CASA. Plan for at least one
rejection; nearly everyone gets one.

---

## The five things that cause most rejections

1. **The video shows authentication, not usage.** Google asks for "the maximum extent of
   the user facing features using the scope". Show the data being used.
2. **The privacy policy has no security section.** "We don't sell your data" is not a
   data protection mechanism.
3. **Scope mismatch between app and Console** — including a scope configured in the
   Console that the app never requests. A leftover `openid` is the classic.
4. **A narrower scope obviously exists** and you did not rule it out explicitly.
5. **You fixed the Console but never replied to the email.** Console edits do not
   restart review. Replying does.

---

## Things worth knowing up front

- **The "Google hasn't verified this app" screen is expected** while review is pending,
  and Google wants it visible in your video. Do not engineer around it.
- **Publishing status "Testing"** caps you at 100 named test users but needs no
  verification — a legitimate place to sit while you build.
- **Never push unverified scopes to production traffic** to record a demo. Use a
  staging build or a separate project.
- **Use a dedicated demo account**, populated with realistic but non-personal content,
  and reuse it for every submission. Screen recordings leak phone numbers, notification
  banners and other accounts in the chooser — check every frame.
- **Some Google guidance asks for the client ID to be visible in the browser URL bar**
  during consent. On mobile, where consent renders in an in-app browser showing only
  `accounts.google.com`, that is not achievable — put the client ID, project ID and
  requested scopes on a closing card in the video instead, which satisfies the same
  intent.
- **Firebase and Identity Platform projects** now route consent-screen configuration
  through the separate **Google Auth Platform** UI. If the settings you remember are
  missing from *APIs & Services*, that is where they moved.

---

## Verify before every submission

```bash
# 1. What does the app actually request?
rg -n "googleapis.com/auth/" --glob '!**/node_modules/**' .

# 2. Is the privacy policy live and public?
curl -sSI https://<your-domain>/<privacy-path> | head -1

# 3. Is the video reachable without signing in, and is it the cut you think it is?
curl -s "https://www.youtube.com/watch?v=<id>" | grep -o '"isUnlisted":[a-z]*' | head -1
yt-dlp -o /tmp/uploaded.mp4 "https://www.youtube.com/watch?v=<id>"
ffprobe -v error -show_entries format=duration -show_entries stream=width,height /tmp/uploaded.mp4
```

Then diff (1) against the Console's Data access list by eye, and step through frames of
the downloaded video confirming every claim you intend to make actually appears in it.
