---
title: Party Mode round-table — Partner referral links and revocable coupons
date: 2026-10-30
mode: session (inline voices)
cast: Mary (Analyst), John (PM), Winston (Architect), Sally (UX), Amelia (Dev), Kofi (Security, walk-on), Quinn (QA, walk-on)
inputs: research.md, docs/optin-and-partner-coupon-journeys.md, crm/api/facility_onboarding.py, crm/partner_portal/*
status: superseded (do not use, see ../DO-NOT-USE.md)
---

> **⚠ SUPERSEDED, DO NOT USE.** This feature was implemented elsewhere. See `../DO-NOT-USE.md`. AI agents and BMAD skills must not reference this file in future work or enhancements.

# Round-table transcript

## Round 1: what is a coupon, actually?

📊 **Mary:** Start with what's in production. Today the "Partner Coupon" is the network's
six-digit Partner ID. It's printed on Network Detail and pasted into WhatsApp groups. It isn't
a coupon. It's a public account number that happens to unlock bonus tokens.

🛡️ **Kofi:** About 20 bits, public, and no revocation short of disabling the whole network.
NIST says anything under 64 bits needs rate limiting at the verifier. We rate-limit by IP,
and the IP comes from the *leftmost* `X-Forwarded-For`, which the attacker writes. So in
practice there's no limit.

📋 **John:** Partners already hand that link out. If we break it on day one, the Partner
Portal team will be on my phone by lunch.

🏗️ **Winston:** So it's not one thing. There's the **network**, which is who you belong to.
There's the **coupon**, a revocable entitlement to the bonus. And there's the **referral
link**, a revocable, trackable way to deliver both. Three nouns. Collapse any two and we get
the journey-mixing mess again.

💻 **Amelia:** Three DocTypes and a click log. And the coupon row on `CRM Facility Membership`
keeps its `partner_coupon` flag, because `token_bonus._coupon_network` reads it. I'm not
rewriting the bonus engine.

📊 **Mary:** Agreed. The bonus engine already does the hard bit: one bonus per facility, paid
only after the invoice clears. That's the hold-the-reward control the fraud literature asks for.

## Round 2: whose domain is the link on?

📋 **John:** The brief says partners share from the Partner Portal, so the URL people see is
the portal's, not ours. Yet we're the ones who have to trust it.

🛡️ **Kofi:** Then the CRM mints the link, and the portal only carries it. The token is
`v1.<kid>.<link_id>.<exp>.<sig>`, HMAC-SHA256 over the network's Partner ID and those fields.
The portal never holds the key. If it wants to show "valid/invalid" before sharing, it calls a
server-to-server verify endpoint with its API key.

🏗️ **Winston:** And the portal's short URL, something like `<portal-host>/r/<slug>`, does a
302 to the canonical CRM URL it got back from the create call. We never redirect *outward*.
Our landing is fixed: `/facility-onboarding?ref=<token>`. No `next=`, no `url=`. RFC 9700:
no open redirectors.

🎨 **Sally:** Hold on. If the share URL is the portal's and the page is ours, the facility
owner jumps domains mid-click. That's exactly what a phishing link looks like. The first screen
has to say who referred them, in the network's branding, before it asks for anything.

🛡️ **Kofi:** Fine, provided the branding comes from *our* database keyed on the verified
token, never from query parameters. Otherwise someone sends `?network_name=Your Bank`.

🎨 **Sally:** Everything on screen comes from the server. Got it. What about the token sitting
in the address bar?

🛡️ **Kofi:** Three things. `Referrer-Policy: no-referrer` on that page. After the claim,
`history.replaceState` removes `ref` from the URL. And no third-party scripts on the landing
page. The token is a bearer for a bonus, not for an account, so this is about hygiene, not
access.

🏗️ **Winston:** Partners register their share hosts. The CRM emits a `share_url` only for an
exact-match https host on that network's allowlist. That's the "tie it back to the partner"
mechanism, in layers: CRM signature → database ownership row → registered host → S2S verify.

## Round 3: signatures, or just a long random ID?

💻 **Amelia:** Honest question. A 128-bit random `link_id` is already unguessable, and we look
it up in the database on every click anyway. Why sign at all?

🛡️ **Kofi:** Three reasons. A forged token fails before it reaches the database, which matters
when someone sprays the claim endpoint. The `exp` and Partner ID are bound, so nobody can
take a link and swap in another network's Partner ID. And when a key leaks we retire its `kid`
and every link signed with it dies at once.

🏗️ **Winston:** No JWT. A JWT in an SMS is 200 characters of noise, and `alg` confusion bugs
are a whole genre. Five fixed fields, one algorithm, `hmac.compare_digest`. It's about 70
characters.

💻 **Amelia:** And the keyring lives in `CRM Opt-In Settings` as Password fields: active key +
`kid`, previous key + `kid`. Not reusing `optin_signing_key`. Different purpose, different
blast radius.

🧪 **Quinn:** I want the pure sign/verify in `crm/utils/referral_tokens.py` with no Frappe
imports, so I can unit-test tampered sig, wrong `kid`, expired, and every field changed one at
a time.

## Round 4: the fight about error messages

🎨 **Sally:** When a link fails, tell people *why*. "This link has expired, ask your partner
for a new one" is useful. "Invalid link" makes them think they've been scammed.

🛡️ **Kofi:** Distinct errors are an oracle for enumeration. Unknown, malformed, revoked and
expired should all look the same.

🎨 **Sally:** Then partners get support calls they can't answer.

📊 **Mary:** Wait, you're both right, and the signature is what settles it. If the signature
**verifies**, the visitor holds a link we genuinely minted, so telling them it expired or was
withdrawn leaks nothing they didn't have. If the signature fails, they get the generic
message.

🛡️ **Kofi:** …I'll take that. Generic for bad signatures and unknown codes, specific only after
a valid signature.

🎨 **Sally:** And in every case they can carry on onboarding without the bonus. A dead link
must never be a dead end.

## Round 5: attribution rules

📋 **John:** Two partners send the same clinic a link. Who wins?

📊 **Mary:** Industry default is last-click. The sources disagree, though.

🛡️ **Kofi:** Last-click until the visitor's identity is verified (Client Registry + OTP).
After that it's locked to the onboarding session. Otherwise a rival can hijack the referral
mid-flow just by getting a second click in.

🎨 **Sally:** The page shows "Referred by <Network>, +N bonus Care Tokens" with a Remove
option. If they type a different coupon, we show which partner it belongs to and they choose.
No silent swaps.

💻 **Amelia:** At submit the server ignores any `partner_id` the client sends whenever a
referral claim sits on the session. The claim wins and is re-verified then: still active, not
expired, redemptions under the cap. All of that happens inside a `for_update` read on the
coupon row so two submits can't both take the last redemption.

🧪 **Quinn:** And the journey contract holds. A referral conversion is the customer-linked
membership row and never touches an Opt-In row. I'll extend `test_journey_separation.py`.

## Round 6: vanity codes and the legacy link

📋 **John:** Partners will want `AFYA2026`, not `7KQ9-X2MD-4HPB`.

🛡️ **Kofi:** Vanity codes are guessable by definition. Then they need a `max_redemptions` and
an `expires_at`, and only CRM staff can create them. The Partner Portal API mints random codes
only.

📋 **John:** I can live with that. And the old six-digit link?

🏗️ **Winston:** A setting, `allow_legacy_partner_id_coupon`, on for now. Network Detail stops
advertising it the day the new panel ships. Once partners have reissued their links it
defaults to off. Every legacy redemption gets logged so we know when it's safe to switch off.

🛡️ **Kofi:** And it's under the same per-network rate limit as typed codes. Plus fix
`_client_ip` to take the right-most untrusted hop from `X-Forwarded-For`, or the rate limit is
for show.

## Round 7: the API surface, and the guest hole

💻 **Amelia:** Partner Portal APIs live in `crm/partner_portal/referrals.py`. Create, list and
revoke for coupons and links, plus verify and stats. All POST/GET whitelisted, **no
allow_guest**.

🛡️ **Kofi:** And *not* `_assert_portal_access`. That one lets Guests in for any enabled
network. New helper `assert_network_scope(network, write=True)`: the caller must be a System
or Sales Manager, or hold `Partner Portal API` / `Network Coordinator` **and** be listed on
that network's coordinators. No "no network yet, carry on" branch.

📋 **John:** Idempotency the same way `deal_won` does it, `X-Idempotency-Key`. The portal
retries.

🧪 **Quinn:** Revoke must be idempotent too: revoking twice returns the same revoked record,
not a 404.

📊 **Mary:** And every API call records the acting partner user (`on_behalf_of`) as well as
the API key's user, so the audit trail names a person, not just "the portal".

## Round 8: what we are *not* doing

📋 **John:** Out of scope for phase 1: partner payouts or commissions, a webhook to the portal
on conversion, QR codes.

🎨 **Sally:** QR is a one-liner on the client from the URL we already return. Push it to
phase 2, but don't design it out.

🛡️ **Kofi:** Webhook goes on the open list. When it lands it's HMAC-signed, with a
timestamp, the same pattern as SES inbound.

---

## Decisions (binding for the architecture)

| # | Decision | Owner voice |
|---|---|---|
| D1 | Three entities: Network (who), **Partner Coupon** (revocable entitlement), **Referral Link** (revocable delivery + attribution). A link may carry a coupon. | Winston |
| D2 | The CRM mints every token. The Partner Portal carries links and never holds signing keys. | Kofi |
| D3 | Token: `v1.<kid>.<link_id>.<exp>.<sig>`, HMAC-SHA256 over the Partner ID and those fields, keyring with `kid`, constant-time compare. No JWT. | Kofi / Winston |
| D4 | The CRM landing is fixed (`/facility-onboarding?ref=`). The CRM never redirects to a URL from the request. A `share_url` is emitted only for an exact-match registered https host. | Winston |
| D5 | Revocation is a server-side status check on claim **and** at submit. | Kofi |
| D6 | Errors: generic for bad signatures and unknown codes. Specific (expired/withdrawn) only after a valid signature. Onboarding always continues without the bonus. | Mary (synthesis) |
| D7 | Attribution is last-click until identity is verified, then locked to the session. The server-side claim beats the client-sent `partner_id`. | Kofi / Amelia |
| D8 | Typed codes are 12-char Crockford base32 + check character, rate limited per client and per network. Vanity codes only from CRM staff, and only with a cap and an expiry. | Kofi / John |
| D9 | The legacy six-digit Partner ID coupon stays behind `allow_legacy_partner_id_coupon` (on), with each use logged. Default flips later. | Winston / John |
| D10 | New scoped access helper. Never `_assert_portal_access` (it admits Guests). Fix `_client_ip` trusted-proxy parsing. | Kofi |
| D11 | Partners see aggregates only. Keyed IP hash, UA family, 90-day purge of rows that never converted. | Mary / Kofi |
| D12 | Journey contract holds: conversions are the customer-linked membership row, `partner_coupon = 1`, plus coupon/link references. | Quinn |

## Left open for the user

See `architecture.md` §12 (Q1–Q4).

## Reviewer ruling (2026-10-30), supersedes parts of D5, D8 and D9

- **D5 (revocation):** not retroactive. A revoke blocks new uses. Unconfirmed orders are
  re-checked before invoice generation, and the user continues without the bonus or enters a
  new coupon from the partner.
- **D8 (custom codes):** CRM staff only, through maker-checker. The Partner Portal submits a
  request, and a different CRM staff user approves or rejects it.
- **D9 (legacy):** the six-digit Partner ID coupon is retired now. No setting.
- Webhook stays in phase 2. Click logging proceeds as proposed, with counsel to confirm.
