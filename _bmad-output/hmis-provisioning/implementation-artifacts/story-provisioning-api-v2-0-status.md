# Story: Work with setup service provisioning API v2.0 and show deployment progress

**Status:** done (2026-11-01)
**Decisions:** [party-review-provisioning-api-v2-0-2026-11-01.md](party-review-provisioning-api-v2-0-2026-11-01.md) (D-A to D-L)
**PR:** #126

As a facility administrator waiting for my HMIS site, I want the portal to show the real deployment step and to say the site is ready only when I can sign in, so that I know what is happening and open the right address.

## Acceptance criteria

1. **Live gate (D-A).** With `completion` in the status response, the phase is `live` only when `completion.fully_provisioned` is true. `Deployed` + `fully_provisioned: false` is `configuring`. Without `completion`, the existing `login.status` rule applies unchanged.
2. **Provisioning (D-B).** `Provisioning` or `In Progress` with `completion.deployment_complete: true` is `configuring` with the headline "Creating your administrator account". Without that flag, it stays `deploying`.
3. **Site address (D-C).** The site URL is `login.url`, else `target.frontend_url`, else `target.url`. An explicit top-level `site_url` still wins.
4. **Auto-deploy (D-D).** The POST carries `auto_deploy: true` unless CRM HFR Settings → Review HMIS deployments before they start is on, in which case `auto_deploy: false`. The setting is shown and saved in the CRM settings page (HFR Settings) and returned by `get_hfr_settings`.
5. **Enqueue failure (D-E).** `submission.deploy_queued` is set from `auto_deploy_queued`. When auto-deploy was requested and was not queued, the queued-phase detail says the implementation team will start deployment. A `WARNING:` service message is not used as customer copy.
6. **Registry outage (D-F).** A 400/417 whose message contains "registry lookup failed" leaves the submission `unknown` and retryable, and caches no rejection.
7. **Step line (D-G).** With `steps[]`, the journey carries `deploy_step = {index, total, name, label, state}` for the running step (or the first pending step after done ones), or the failed step. The portal shows "Step N of T · label" in the setup card, or "Stopped at step N of T · label" on failure. No step error text is returned to non-System Managers.
8. **Owner failure (D-H).** `Failed` + `deployment_complete: true` + `owner_user_complete: false`, or a `Failed` step named "Owner User (retry)", marks the configure step as the error.
9. **Live since (D-I).** The live card shows "Live since <date>" when `deployed_on` is reported.
10. **Polling (D-J).** `journey.poll_after_seconds` is 60 for deploying/configuring and 300 for preparing/queued; the portal schedules its next check from it and its footer says how often it checks.
11. **Cancelled / instance blocked (D-K).** `Cancelled` shows "Setup was cancelled". An error containing "deployment is blocked until the instance is set to active" shows "HMIS server paused" copy. Both are `needs_attention`.
12. **No password (D-L).** Parsing the full v2.0 example payload (with `login.password`) leaves the password nowhere in the status or journey.

## Tasks

- [x] `crm/api/hfr.py`: parse `completion`, `steps`, `deployed_on`, `facility_setup`; fix the URL order; phase and copy changes; `deploy_step`; `poll_after_seconds`; `auto_deploy` on the payload; `deploy_queued`; registry-outage retry.
- [x] CRM HFR Settings: `external_provisioning_manual_review` Check; `get_hfr_settings` / `update_hfr_settings`; `HFRSettings.vue` toggle.
- [x] `FacilitySingleView.vue`: step line, "Live since", poll interval from the journey.
- [x] Python tests in `crm/tests/test_hmis_provisioning_journey.py` and `crm/tests/test_hfr_provisioning_status.py`.
- [x] Playwright cases in `frontend/e2e/regression/facility-single-view.spec.ts`.
- [x] Docs: `docs/hmis-external-provisioning-v2-1-crm-changes.md` (v2.0 section), contract v2 §8 status for CRM-P4/P5/P6.

## Deployment

`bench migrate` (new Check field). No data patch: the field defaults to off, which keeps auto-deploy on.
