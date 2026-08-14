# Scopes: tiers, choosing, and matching

The tier of the *most* sensitive scope you request determines the entire review.
Decide this before you write any code — it is the difference between a form and a
paid annual security audit.

---

## The three tiers

| Tier | What it means | What it triggers |
|---|---|---|
| **Non-sensitive** | No private user data | Brand verification only (if you want a custom name/logo) |
| **Sensitive** | Private user data, narrow slice | Google review: privacy policy + demo video |
| **Restricted** | Broad, high-risk access | Everything above **+ Limited Use compliance + usually a CASA security assessment** |

Classification is **not** intuitive — "readonly" does not mean "safe tier".

| Scope | Tier |
|---|---|
| `openid`, `userinfo.email`, `userinfo.profile` | Non-sensitive |
| `drive.file` | Non-sensitive |
| `drive.metadata.readonly` | Sensitive |
| `gmail.send`, `gmail.labels` | Sensitive |
| `drive`, **`drive.readonly`** | **Restricted** |
| `gmail.readonly`, `gmail.modify`, `mail.google.com` | **Restricted** |

`drive.readonly` being restricted surprises people: it is read-only, but it reads
*every file in the user's Drive*, which is precisely the risk being priced in.

Sources: [OAuth API verification FAQ](https://support.google.com/cloud/answer/9110914),
[Drive API scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth),
[Gmail API scopes](https://developers.google.com/gmail/api/auth/scopes).

> ⚠️ Verify the tier of your exact scope string against Google's own tables before
> committing. Classifications shift, and near-identical scopes can sit in different
> tiers.

---

## CASA — the expensive part

If you request a restricted scope in a public app, budget for a **Cloud Application
Security Assessment**: an OWASP ASVS-based third-party audit, **repeated annually**.

- **Tier 2** — automated scanning / self-assessment. The usual bar for restricted access.
- **Tier 3** — independent manual penetration testing. Needed for the Workspace
  Marketplace security badge.

Google charges nothing; the authorised labs do. Expect four figures for a manual
assessment, and add weeks to the timeline.

**Documented exemptions** are about *use case*, not architecture:

- **Personal use** — only the developer's own account.
- **Internal use** — all users in a single Google Workspace domain.
- **Testing/development** — publishing status "Testing", ≤100 named test users.

> **Unclear, so do not assume:** whether an app that only ever handles restricted-scope
> data **on the client device**, with no developer-operated servers, escapes CASA.
> There is no clearly documented architectural carve-out. If that is your
> architecture, state it plainly in your submission and let the reviewer rule — but
> plan as though the assessment will be required.

---

## Choose the narrowest scope that works

Google rejects requests where a narrower scope would do, so make the decision
deliberately and record the reasoning — you will need it verbatim in the submission.

Work down this ladder and stop at the first that genuinely works:

1. **No scope at all** — can the user just upload/paste the data?
2. **`drive.file` / picker-based access** — the file-level grant. Non-sensitive, no
   video, no CASA. Enormously cheaper. It covers only files the user explicitly picks
   or your app created; **picking a folder does not grant the files inside it**.
3. **A metadata-only scope** — if you need to list but never read content.
4. **A full read scope** — only if the feature genuinely needs the whole corpus.

If you land on a restricted scope, be able to answer: *what does a real user have to
do, one action at a time, if I use the narrower scope instead?* Concrete beats
abstract. "The user would have to hand-pick each of ~400 songs, and re-pick whenever
they add one" is an argument. "It would be inconvenient" is not.

---

## Scope matching — a real trap

> **Scope Matching:** The scopes requested by your app or manifest must exactly match
> the scopes configured and submitted for verification in the Google Cloud Console.

This is checked, and it fails in **both** directions. A scope configured in the Console
that your app never requests is just as much a mismatch as a missing one.

The classic case is a stray **`openid`** left in the Console while the code requests
only `drive.readonly`, `userinfo.email` and `userinfo.profile`.

Reconcile before every submission:

```bash
# what the app actually asks for — grep your real request, not your docs
rg -n "googleapis.com/auth/" --glob '!**/node_modules/**' .
```

Then open **Google Auth Platform → Data access** and diff the list by eye.

Two things that bite:

- **These pages have an explicit Save.** Removing a row and navigating away silently
  discards the change. Remove, save, then **reload and re-read the list** to confirm.
- **Do not "fix" a mismatch by widening the app.** Delete the unused scope from the
  Console instead — adding scopes to your code to match a stale Console entry
  contradicts least privilege and invalidates your recorded consent screen.

---

## Publishing status

| Status | Effect |
|---|---|
| **Testing** | Up to 100 named test users. No verification needed. No warning screen for those users. |
| **In Production** | No user cap. Unverified sensitive/restricted scopes show the "Google hasn't verified this app" interstitial. |

If your app is already live, **do not push unverified scopes to production traffic** to
record a demo — it consumes unverified-user quota and disrupts real users. Use a
staging build, a hidden route, or a separate project, and leave publishing status
"In Production".
