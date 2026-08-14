# The privacy policy

The most common first rejection, and the easiest to fix — because most policies
answer *what we collect* and Google is also asking *how you protect it*.

Typical rejection wording:

> Your privacy policy does not specify any data protection mechanisms for sensitive data.

---

## Hosting requirements

Before content, get these right or the review stalls on logistics:

- Hosted on a **domain you own**, verified in Google Search Console.
- On the **same domain** as the app homepage you declared.
- **Publicly reachable** — no login, no `noindex` gate, no PDF-only.
- Linked from the OAuth consent screen **and** from the app homepage.
- Specific to *this* app. A generic company template gets rejected; it must name the
  Google data involved and what you do with it.

---

## The two things Google looks for

### 1. The Limited Use statement (verbatim-ish)

For restricted scopes — and good practice for sensitive ones — the policy must carry a
sentence substantially similar to:

> App's use and transfer to any other app of information received from Google APIs will
> adhere to the [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy),
> including the Limited Use requirements.

Then state the four commitments explicitly, because reviewers look for them:

1. Data is used **only to provide or improve user-facing features**.
2. Data is **not used or transferred for advertising** — including retargeting,
   personalised or interest-based advertising.
3. **Humans do not read the data**, except with the user's explicit consent, for
   security purposes, to comply with law, or on aggregated/anonymised data.
4. Data is **not used to develop, train or improve AI or ML models**.

Point 4 is enforced far more aggressively than it once was. Policies written before it
existed are routinely rejected today purely for its absence.

### 2. A data-protection section

This is the part that is usually missing. Give it its own heading — reviewers scan for
it. Say concretely, for the Google data specifically:

- **In transit** — TLS on every API call.
- **Credentials at rest** — where tokens live (iOS/macOS Keychain, Android Keystore,
  encrypted server store) and that they are never logged or emailed.
- **Data at rest** — device encryption, or the server-side encryption you use.
- **Server-side handling** — what you store and for how long. If you run **no** servers,
  say so explicitly: it is the strongest possible answer, so do not leave it implied.
- **Access control** — who can reach the data internally, and that no human reviews it.
- **Retention and deletion** — what signing out deletes, and that access is revocable
  at [myaccount.google.com/permissions](https://myaccount.google.com/permissions).

### Example

For a client-only app, this reads as:

> **How your data is protected.** Every call to Google's APIs is made over TLS. Your
> OAuth tokens are stored in the system Keychain, which is hardware-encrypted, and are
> never written to our servers — we do not operate any. Audio streams from Google Drive
> directly to your device, so no copy of your files ever passes through us. The local
> index is stored in your app's private, encrypted container. Signing out deletes the
> stored tokens and the local index, and you can revoke access at any time at
> myaccount.google.com/permissions. We do not sell or transfer your Google data, no
> human reviews it, and it is never used to train AI or ML models.

Adapt honestly. Do not claim encryption or controls you have not implemented — this is
a compliance document, and it is a bad place to be aspirational.

---

## Checklist

- [ ] Own, Search-Console-verified domain, same domain as the homepage
- [ ] Publicly reachable, no auth wall
- [ ] Linked from the consent screen and the homepage
- [ ] Names the specific Google scopes/data involved
- [ ] Limited Use statement present and linked
- [ ] All four Limited Use commitments spelled out, **including the AI/ML one**
- [ ] A dedicated data-protection/security section
- [ ] Retention and deletion described, with the revocation link
- [ ] Says whether you operate servers at all
- [ ] URL in the Console points at the live page
