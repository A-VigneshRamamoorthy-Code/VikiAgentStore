# Rejections and how to reply

Verification is a correspondence, not a form. How you reply decides how many more
rounds you get.

---

## The one rule people get wrong

**Editing the Cloud Console does not restart review. Replying to the email does.**

Every rejection ends with some version of:

> Important! Once you have addressed the issues above, reply directly to this email to
> confirm. You must reply to this email after fixing the highlighted issues to continue
> with the app verification process.

The reply address is a long tagged address like
`api-oauth-dev-verification-reply+<token>@google.com`. It routes to your case. Reply
to it directly — a fresh email to a different Google address goes nowhere, and fixing
the Console silently leaves your request sitting untouched.

Order of operations: **fix everything → verify it → then reply.** A reply that arrives
before the Console is correct burns a cycle.

---

## Common rejection reasons

| Rejection | What it actually means | Fix |
|---|---|---|
| "Your privacy policy does not specify any data protection mechanisms for sensitive data" | You wrote what you collect, not how you protect it | Add a security section — see [privacy-policy.md](privacy-policy.md) |
| "The demo video does not sufficiently demonstrate why the scope(s) are necessary" | You showed sign-in, not the feature | Re-record showing the data in use — see [demo-video.md](demo-video.md) |
| "Scopes must exactly match" | Console lists a scope the app never requests, or vice versa | Reconcile both sides — see [scopes.md](scopes.md) |
| "Your app's use case does not justify the requested scope" | A narrower scope exists and you did not rule it out | Argue each narrower scope concretely |
| Homepage / domain ownership problems | Domain not verified, or the homepage does not describe the app | Verify in Search Console; make the page describe *this* app |
| Privacy policy not reachable / not on the same domain | Hosted on a different domain to the app homepage | Move it under the verified domain |

---

## Writing the reply

Reviewers process a queue. Optimise for someone who has 90 seconds.

**Do:**
- Address each item they raised, in the order they raised it, under a matching heading.
- Give timestamps into the video.
- State the scopes you request as a literal list.
- Say plainly when something does not apply, and why.

**Don't:**
- Restate your product pitch.
- Describe features the video does not show.
- Send a wall of prose. Short and specific beats thorough and vague.
- Claim something is fixed that is not yet saved in the Console.

### Template

```
Hi,

Thanks for the review — I've sorted both items.

**Privacy policy**

<url>

I've added a "How your data is protected" section. It covers <transport security>,
<credential storage>, <encryption at rest>, and <server-side handling, or the absence
of servers>. It also states we don't sell, transfer or human-review Google data and
don't use it to train AI/ML models, and that signing out deletes the tokens and any
local index.

**New demo video**

<url> (<duration>)

Recorded against <demo account>, which holds <n> <items>.

- **0:40** — the consent screen, with "<exact scope wording>" shown in full and ticked
  at 0:57. That's the only sensitive scope we ask for.
- **1:50** — <the feature the scope exists for>.
- **2:38** — Settings, showing the connected account and Disconnect.
- **3:13** — closing card with the client ID, the project and the scope requested.

<App> is read-only — it never creates, renames, moves or deletes anything — so there's
no write behaviour to show back in the source account.

**Why not something narrower**

`<narrower.scope>` only <limitation>, so <concrete consequence for a real user>.
`<other.scope>` can <what it does> but can't <what it can't>, so <feature> wouldn't work.

The app requests `<scope>`, `<scope>` and `<scope>` and nothing else, which matches the
Console. Publishing status is still "In Production".

Happy to record more if it would help.

Best,
<name>
<company>
```

Keep it around 300–350 words. If a section is not in dispute, one line is enough.

---

## Pre-send checklist

Run this every time. Most second rejections are self-inflicted.

- [ ] Every claim in the reply is visible in the *uploaded* video — re-downloaded and
      spot-checked, not assumed
- [ ] Video is **unlisted, not private**; opens in a logged-out browser
- [ ] Console scope list and the app's requested scopes match **exactly**, both
      directions
- [ ] Console changes are **saved** (these pages have an explicit Save; navigating away
      silently discards)
- [ ] Privacy policy is live at the URL in the Console, on the verified domain, and
      contains the security section
- [ ] Publishing status still "In Production"
- [ ] The video URL is in the verification request itself, not only in the email
- [ ] Replying to the correct tagged address

---

## If you disagree with a rejection

Sometimes the reviewer has misread the app. Say so once, politely, with evidence —
a timestamp or a screenshot — and offer to record whatever would settle it. Do not
resubmit the same material unchanged with a longer explanation; that reads as
non-responsive and costs another cycle.

If two rounds go by on the same point, change the artefact rather than the argument:
record the specific thing they keep asking for, even if you believe it is already
implied by what you sent.
