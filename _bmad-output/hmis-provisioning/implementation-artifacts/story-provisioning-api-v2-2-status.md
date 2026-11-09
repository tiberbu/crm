# Story: Align with setup service provisioning API v2.1 / v2.2

**Status:** done (2026-11-01)
**Decisions:** [party-review-provisioning-api-v2-2-2026-11-01.md](party-review-provisioning-api-v2-2-2026-11-01.md) (V22-A to V22-E)
**Builds on:** [story-provisioning-api-v2-0-status.md](story-provisioning-api-v2-0-status.md)
**PR:** #151

As a facility administrator waiting for my HMIS site, I want the portal to tell me the truth when deployment will not start by itself, and as support I want no repeated error logs for a facility whose ID CRM holds in the wrong format.

## Acceptance criteria

1. **Explicit auto-deploy (V22-A).** The POST always carries `auto_deploy` (`true`, or `false` under manual review). It never carries `tokens_awarded`, `token_expiry_date`, `billing_model` or `license_expiry_date`.
2. **Idempotent Draft (V22-B).** An idempotent POST with `auto_deploy: true` whose returned status is queued (e.g. `Draft`) records `submission.deploy_queued: false`, sets the 7-day not-queued flag for the FID, and the journey says deployment did not start automatically. With manual review on, or a status already deploying, nothing is flagged.
3. **FID format (V22-C).** A FID not matching `^FID-\d{2}-[\w-]+$` (case-insensitive) is not sent to the status API; the result is `unavailable`, `error_code: invalid_fid`, not retryable, and no "requires support" Error Log is written. The POST payload check uses the same rule.

## Tasks

- [x] `crm/api/hfr.py`: `_is_valid_fid`; status call guard; `invalid_fid` copy in `_external_provisioning_unavailable`; skip the support log for it; idempotent Draft handling in `_auto_submit_external_provisioning_impl`.
- [x] Tests: `crm/tests/test_hmis_provisioning_api_v2_2.py` (9).
- [x] Docs: v2.2 section in `docs/hmis-external-provisioning-v2-1-crm-changes.md`.

## Deployment

No migration, no setting. Python change only: restart the web workers.
