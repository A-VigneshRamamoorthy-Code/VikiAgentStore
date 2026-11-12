# Sign-in, tenants and consent

The app holds **no** credentials of its own. Everything is done with the signed-in user's
delegated tokens; servers and the reconciler use managed identities.

## App registration

- Public client, audience **AzureADandPersonalMicrosoftAccount** (work/school *and*
  personal accounts). No secret. Client ID is in `Auth.swift`
  (override with `defaults write com.viki.vikivpn VikiVPNClientID <id>`).
- Redirect: loopback `http://127.0.0.1:<random port>` (PKCE, system browser).
- Delegated scopes: ARM `user_impersonation`, Storage `user_impersonation`, `offline_access`.

## Flow (`Auth.swift`)

1. Browser sign-in at `/common` with `prompt=select_account` → refresh token.
2. List tenants (`ARM /tenants`). Personal accounts (MSA) sign in through the consumers
   tenant `9188040d-…` but own subscriptions in their **default directory**; the app
   redeems the refresh token at that tenant's authority.
3. If a tenant has not consented to Storage yet (`AADSTS65001`), a second interactive
   authorize against that tenant is triggered once.
4. The user picks a subscription; `Provisioner` registers resource providers and builds.

Personal accounts fail with "You can't sign in here with a personal account" if the app
registration audience is `AzureADMultipleOrgs` or the authority is `/organizations`.

## What is stored on the Mac

| Item | Where |
|------|-------|
| Microsoft refresh token | Keychain, service `VikiVPN`, account `ms-refresh-token` |
| Device WireGuard private key | Keychain (`VikiVPN WireGuard key`); the public key goes into `config/peers.json` |
| Tenant/subscription/region choices, session history | `~/Library/Application Support/VikiVPN/` (no secrets) |

Sign-out deletes the refresh token and resets the setup state; the device key is kept so
the same peer is reused after signing back in.

## Server identities

- Each VM: system-assigned identity with **VikiVPN Stopper** (read + `deallocate`) on its
  own resource group and Storage Blob Data access to the control account.
- Reconciler: Automation account identity with Stopper on the VPN resource groups.
- Home-PC invites: short-lived **user-delegation SAS** (create-only on
  `exits/_enroll/<id>.json`), derived from the signed-in user's token.
