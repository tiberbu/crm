# Party review: HMIS setup service provisioning API v2.1 / v2.2

**Date:** 2026-11-01
**PR:** #126 (`docs/hmis-setup-service-crm-spec-v2` → `develop`)
**Input:** "External Facility Provisioning API — Contract, Version 2.1" from the HMIS setup service team, with its v2.1 and v2.2 change notes (shared 2026-11-01). Identifiers in its examples are not copied here.
**Room:** Mary (analyst), John (PM), Winston (architect), Amelia (dev), Sally (UX), Murat (test architect)
**Baseline reviewed:** the v2.0 work on PR #126 ([party-review-provisioning-api-v2-0-2026-11-01.md](party-review-provisioning-api-v2-0-2026-11-01.md), D-A to D-L), the owner password one-time view ([party-review-owner-password-one-time-view-2026-11-01.md](party-review-owner-password-one-time-view-2026-11-01.md)), and `crm/api/hfr.py` as staged.

## Round-table highlights

- **Mary:** v2.1 only deletes four billing fields and v2.2 only flips a default. Most of this document is v2.0 again, and we already built v2.0. The work is in the corners.
- **Winston:** The default flip is a no-op for us *because* we always send `auto_deploy` explicitly. Keep it explicit: once the service defaults to true, an explicit `false` is the only thing that makes manual review work.
- **Amelia:** §4.5 is the corner. "A re-post does not re-trigger deployment." If our POST comes back `idempotent: true` with a `Draft` record, we currently tell the facility "Deployment starts automatically within a few minutes". It never will.
- **John:** How do we even re-post? We only POST after the status call says "No Facility Setup found."
- **Amelia:** A race between two refreshes, or a record someone created in the Setup app between our GET and our POST. Rare, but when it happens the copy is wrong forever.
- **Sally:** Then reuse the copy we already have for a failed enqueue: "did not start automatically, the implementation team will start it." No new string for customers.
- **Murat:** And the status endpoint now documents a 400 for a malformed FID. Today that becomes "status request rejected" plus a support Error Log on every refresh for that facility. That's noise from a CRM data problem.
- **Winston:** Check the FID locally with the service's own pattern before calling. Same helper as the POST validation, so the two rules can't drift.
- **Murat:** One more: the contract says 400 everywhere. Frappe 15 raises `ValidationError` as 417 (checked in `frappe/exceptions.py`). We already handle both; keep it that way.
- **Mary:** The version naming ask from the v2.0 review is answered: v2.0, v2.1 and v2.2 are now numbered in the document itself.
- **John:** The password. The document still returns `login.password` while `email_sent` is false. We've since decided to show it once to the owner, so we no longer ask them to drop it.
- **Winston:** What still worries me: the contract lists no `token_source`, `token_purchase_url` or `metering_site_key`, yet the OpenMeter path sends them. Ask them to confirm those are accepted and never written to the deployment log.

## Gaps found

| v2.1 / v2.2 item | CRM before this change | Gap |
|---|---|---|
| v2.1: `tokens_awarded`, `token_expiry_date`, `billing_model`, `license_expiry_date` removed | Already not sent (v2.0 work) | None; a test now pins it |
| v2.1: `licence` is the regulatory licence number | HFR licence or registration number, backfilled from HFR by FID | None |
| v2.2: `auto_deploy` defaults to true | CRM always sends it (`true`, or `false` under manual review) | None; explicit value must stay |
| §4.5: idempotent re-post never starts deployment | Idempotent `Draft` shows "Deployment starts automatically" | **Fixed (V22-B)** |
| §5 errors: malformed FID is a 400 on the status call | Called on every refresh; logged for support | **Fixed (V22-C)** |
| `owner_user_queued` on the POST | Ignored | Out of scope: the deployment's "Owner User (retry)" step covers it and status reports it |
| `workflow` block, forcing `hmis_instance` | Not used | Out of scope (unchanged from v2.0 review) |

## Decisions

| # | Decision | Owner of the argument |
|---|---|---|
| V22-A | Keep sending `auto_deploy` explicitly. `false` is now the only way manual review (CRM HFR Settings → Review HMIS deployments before they start) keeps a Draft. No billing field is sent; a test pins the four v2.1 removals. | Winston |
| V22-B | An idempotent POST that requested auto-deploy and returns a queued status (`Draft` and the other queued wordings) sets `submission.deploy_queued: false` and the 7-day per-FID not-queued flag, so the queued phase says the implementation team will start deployment. Under manual review, or when the record is already deploying, nothing is flagged. | Amelia, Sally |
| V22-C | `_is_valid_fid` holds the service's pattern (`^FID-\d{2}-[\w-]+$`, case-insensitive). The status call is skipped for a malformed FID and returns `unavailable` with `error_code: invalid_fid` (not retryable), and the "requires support" Error Log is not written for it. The POST validation uses the same helper. | Murat, Winston |
| V22-D | 400 and 417 stay equivalent for validation responses (Frappe 15 maps `ValidationError` to 417). | Murat |
| V22-E | Docs: a v2.2 section in `docs/hmis-external-provisioning-v2-1-crm-changes.md`. The v2.0 ask "name the versions consistently" is closed; "stop returning `login.password`" is withdrawn (owner one-time view decision). | Mary, John |

## Asks back to the HMIS setup service team

1. Confirm `token_source`, `token_purchase_url` and `metering_site_key` (sent when CRM's token source is OpenMeter) are accepted, and that the site key is never written to the deployment log or the Facility Setup document.
2. Return 400 consistently as documented, or document 417 (Frappe's default for `ValidationError`).
3. Still open from v2.0: an `error_code` for the Inactive-instance block and the owner-user failure, and `X-Correlation-Id` on responses.

## Out of scope

- `owner_user_queued`, the `workflow` block, forcing `hmis_instance`.
- Contract v2 CRM-P1/P2/P3/P7 (metering site key and gateway address): unchanged.
