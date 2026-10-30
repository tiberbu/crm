---
title: Partner referral links and revocable coupon codes — technical research
type: technical (BMAD Deep Recon, run mode, explore shape)
date: 2026-10-30
decision: How the CRM issues, verifies and revokes Partner Coupon codes and referral links that partners share from the Partner Portal (a non-CRM domain)
feeds: architecture.md, epics-and-stories.md
---

# Research summary

Each claim cites its source and the access date (2026-10-30). Project code shaped which
questions we asked. It was not used as evidence for external practice. Codebase findings are
in a separate section and marked as such.

## 1. Redirects and links that leave the domain

| # | Claim | Source |
|---|---|---|
| R1 | The first recommendation is to avoid redirects. If a redirect is needed, the destination must not come from user input. An interstitial that shows the destination is a further mitigation. Mapping IDs to destinations can allow enumeration. | OWASP, *Unvalidated Redirects and Forwards Cheat Sheet* |
| R2 | Endpoints must not forward the browser to an arbitrary URI taken from a query parameter. Redirect URIs are compared by exact string match against pre-registered values. | IETF RFC 9700 (BCP 240, Jan 2025), §4.11 |

**Applied:** the CRM landing never redirects to a URL that comes from the request. The
destination is fixed server-side (`/facility-onboarding`). Partner Portal share hosts are
registered per network, and the CRM checks them by exact host match before it emits a
`share_url`.

## 2. Signed tokens: expiry, key rotation, comparison

| # | Claim | Source |
|---|---|---|
| R3 | Signed-URL schemes carry a key id (`kid`), so several keys can verify at once and rotating keys does not break URLs already issued. An unknown `kid` is rejected, with no fallback to another key. | `broadcast-auth` crate source (library practice, not a standard) |
| R4 | Compare MACs in constant time. Python's `hmac.compare_digest` is the usual primitive. A short-circuiting `==` leaks timing. | Same; also PyPI `philiprehberger-webhook-signature` docs |
| R5 | Use HMAC keys of at least 32 bytes. Expiry is an absolute `exp`, set when the token is minted. | `broadcast-auth` |
| R6 | **Gap:** none of the sources cover revoking a single signed URL before it expires. Common practice is a server-side status check or short TTLs. | Absence of evidence in the search set |

**Applied:** the token is HMAC-SHA256 with a `kid` keyring (key ≥ 32 bytes) and
`hmac.compare_digest`. The `exp` is part of the signed string. Revocation is a **server-side
status lookup on every claim and again at submit**, because a signature cannot be revoked (R6).

## 3. Code entropy and online guessing

| # | Claim | Source |
|---|---|---|
| R7 | Look-up secrets with less than 64 bits of entropy require a rate-limiting mechanism at the verifier. Length rules for memorized secrets assume rate-limited online attacks. | NIST SP 800-63B rev 3 §5.1.2 / App. A (usnistgov 800-63-3 repository); rev 4 moves this to §3.2.2 |
| R8 | Verifiers cap consecutive failed attempts. Recommended mitigations are CAPTCHA and growing delays. | Same |

**Applied:** a human-typable coupon is 12 Crockford base32 characters (60 bits) plus a check
character. It is under 64 bits, so it is **rate limited per client and per network**. A
referral `link_id` is 128 bits and is never meant to be typed. Today's coupon is the six-digit
Partner ID: about 20 bits, public, and impossible to revoke. It fails R7 and becomes a legacy
path behind a setting.

## 4. Coupon lifecycle (industry reference: Stripe Promotion Codes)

| # | Claim | Source |
|---|---|---|
| R9 | A promotion code points to an underlying coupon. Its controls are `active`, `max_redemptions`, `expires_at` (Unix time) and `restrictions` (for example `first_time_transaction`). It can be tied to one customer. | Stripe API reference, `promotion_codes/object`; stripe-ruby docs |
| R10 | Deactivating with `active=false` is plausible but was **not verified** in the retrieved sources. | Unverified |

**Applied:** coupons carry `status` (Active, Revoked, Expired), `max_redemptions`,
`expires_at` and an optional `first_order_only`. The underlying benefit is the existing
Partner Coupon bonus (`CRM Opt-In Settings.partner_coupon_tokens`), granted once per facility.

## 5. Referral fraud

These are vendor blogs, so treat them as rules of thumb, not standards.

| # | Claim | Source |
|---|---|---|
| R11 | Self-referral is the most common fraud by volume. Matching on address, IP or payment fingerprint catches it. | ReferralCandy blog; DEV Community (Stripe affiliate fraud) |
| R12 | Require a real click rather than a cookie being present. Shorter windows (7–14 days) are common. No single control stops cookie stuffing, so layer controls. | ReferralCandy; Post Affiliate Pro glossary |
| R13 | Conversions seconds after a click, or exactly at the end of the window, are suspicious. | Refgrow |
| R14 | Holding the reward and tying it to a funded outcome beats detecting fraud after payout. | Talkable; Hamstergarage |
| R15 | Last-click is the usual default. The sources disagree on first-click versus last-click. | TechInterview LLD; conflicting vendor sources |

**Applied:** the reward is already held until the invoice is paid (openmeter_mediator grants
the Partner Coupon bonus on payment), which covers R14. Attribution comes from a **JS-executed
claim** bound to the onboarding session, not from a cookie (R12). Claim timing and IP-hash
signals are logged for review (R13). Attribution locks once the visitor's identity is verified
(see architecture §6).

## 6. Privacy (Kenya Data Protection Act, 2019)

| # | Claim | Source |
|---|---|---|
| R16 | Personal data means any information relating to an identified or identifiable natural person. An IP address that can be linked to a person likely falls under this. The retrieved texts do not name IP addresses explicitly. | Data Protection Act No. 24 of 2019 (ODPC PDF); DLA Piper summary |
| R17 | Consent has to be voluntary and given by a clear act. The Act also applies to processing outside Kenya of data about people in Kenya, and restricts transfers abroad. | Data Protection (General) Regulations 2021; PwC Kenya bulletin |

**Applied:** store only a keyed hash of the IP, truncated, plus the user-agent family. Purge
click rows that never converted after 90 days. Partners see aggregate counts, never data about
visitors who did not convert. **Have counsel confirm the lawful basis**, which is open
question Q4.

## 7. Framework facts (Frappe)

| # | Claim | Source |
|---|---|---|
| R18 | `@frappe.whitelist(allow_guest=True, methods=["POST"])` exposes a guest endpoint restricted to POST. | context7 `/frappe/frappe/v15.86.0` |
| R19 | `frappe.rate_limiter.rate_limit(key=None, limit=5, seconds=86400, methods="ALL", ip_based=True)` rate-limits one endpoint in Redis and returns HTTP 429. | **Installed source** `apps/frappe/frappe/rate_limiter.py:105`, Frappe v15.107.5. The context7 snippets and the Frappe rate-limiting docs describe `user_based` and do not mention `methods`/`ip_based`, so the installed source wins (Rule 11 cross-check). |
| R20 | `frappe.cache.set_value(..., expires_in_sec=)` provides TTL keys for claim state. | context7 `/frappe/frappe/v15.86.0` |

## 8. Codebase findings

These come from the code, not from research, and they constrain the design.

- **C1.** The current Partner Coupon is the network's public six-digit `partner_id`
  (`crm/api/facility_onboarding.py` `_public_network`, `PARTNER_ID_RE`). Anyone who knows a
  network's ID can claim the bonus. It cannot be revoked short of disabling the network.
- **C2.** `crm/partner_portal/pricing.py:_assert_portal_access` returns True for **Guest**
  callers whenever the network is enabled, and lets any Network Coordinator through when no
  network is resolved. The new referral and coupon APIs must not reuse it (Story 2.3).
- **C3.** `_client_ip()` trusts the **leftmost** `X-Forwarded-For` value, which the client
  controls. Rate limits keyed on it can be bypassed by rotating that header. Story 2.3 adds a
  trusted-proxy helper.
- **C4.** The onboarding session is an opaque bearer token with HMAC-keyed Redis storage
  (`_session_key`, `_save_session`). The referral claim binds to that session.
- **C5.** The bonus grant reads `CRM Facility Membership.partner_coupon` by Customer and
  facility (`crm/utils/token_bonus.py:_coupon_network`), and the one-per-facility rule already
  exists. The new coupon references on the membership row extend this. They do not replace it.
- **C6.** The journey separation contract (`docs/optin-and-partner-coupon-journeys.md`)
  holds: referral and coupon conversions are always the **customer-linked** row. They never
  touch an Opt-In row.

## Open questions

- Q1. Revoking a coupon: should it also stop bonuses on orders already created but not yet
  paid? Recommendation: yes for orders not yet confirmed, no clawback once confirmed.
- Q2. Legacy `?partner_coupon=<Partner ID>`: when does it switch off? Recommendation: keep it
  on behind a setting until partners have reissued their links, then default it to off.
- Q3. Partner Portal webhook for conversions: in scope now, or a later phase?
- Q4. Lawful basis and retention for click logging: needs counsel sign-off.
