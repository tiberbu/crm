# Facility self-onboarding: duplicate OTP and submitting without a Network

Status: first fix merged in PR #111; follow-up fix on `fix/otp-single-send-and-no-network-check` (2026-10-23). See [Follow-up after retest](#follow-up-after-retest).

## Reported problems

1. After entering identification details, the owner received the OTP email twice.
2. An owner with no Network ID could not submit, even after accepting the Terms and Conditions.

## Findings

### Duplicate OTP

The crm-dev request log for the reported run (2026-10-23, UTC) showed:

| Time | Request |
|---|---|
| 10:47:12 | `start_identity` → first OTP email |
| 10:47:27 | `verify_otp` → **403**, the page recovered through `retry_hfr` |
| 10:47:48 | Terms loaded; the review step showed the "We couldn't find a Network" blocker |
| 10:48:22 | Page reloaded |
| 10:48:39 | `start_identity` → second OTP email |

- The browser sends one `start_identity` per submission. A Playwright regression test confirms this with repeated clicks and Enter while the request is in flight.
- The server queues one email per call.
- The second email came from restarting the flow after the Network blocker.

Two defects contributed:

- **Session read-after-write (Frappe 15).** `frappe.cache().set_value(..., expires_in_sec=...)` writes to Redis without updating the request-local cache, and `get_value()` serves later reads from that local cache. Within one request, the onboarding session could not see its own latest save.
  - `verify_otp` marked the session verified, read back the stale copy and threw "This onboarding session has expired" (403) on every verification.
  - The page recovered with a second request (`retry_hfr`).
  - The same stale read affected every other step that saves the session and then reads it again in the same request.
- **Restarting always sent a new code.** Reloading the page during the resend window sent another OTP, even though the first code was still valid.

### Network required

- `submit_onboarding` rejected the request when no Network ID was given and no default Network was configured: "That Network ID does not exist or is not available".
- The review step showed a blocker instead of the submit button.
- Facility membership requires a Network (`CRM Facility Membership.network` is mandatory and read in many places). Making it optional would change every reader.

## Fix

### OTP

- Session reads use `get_value(key, expires=True)`, which bypasses the request-local cache, so a request always sees its own latest save. `verify_otp` returns the facilities directly.
- A repeat `start_identity` for the same identity within the resend window does not send another email:
  - The new session inherits the code already sent, its attempt count, expiry and delivery details.
  - The previous unverified session is deleted.
  - The response reports `reused: true` and the remaining resend wait.
  - The person still needs the code from their inbox. The previous session token is never handed out, so a restart cannot take over another person's session.
  - The pointer is cleared once the code is verified, so a restart cannot end a verified session.
  - Resend still works after the wait.

### No Network

- A blank Network ID resolves to the configured default Network when one exists.
- Otherwise the request is recorded against a dedicated **No Network** record:
  - slug `no-network`, display name "No Network";
  - disabled, so the public Network ID lookup can never select it;
  - created on first use.
- The facility membership, Deal and Lead point at that record, and onboarding evidence records "no Network ID provided". Staff can find these requests and link a Network later.
- A Network ID that was typed but does not exist is still rejected.
- The review step shows "No Network" with a neutral note instead of the blocker, and the request can be submitted once the terms are accepted.

## Verification

- Playwright (`frontend/e2e/regression/facility-onboarding-network.spec.ts`, built bundle with the Frappe API mocked):
  - one OTP request per identity submission;
  - submit without a Network ID;
  - submit with Network ID `623161`.
- Python tests:
  - session read-after-write;
  - repeat start within the resend window reuses the code without sending, and a later restart sends again;
  - submit without a Network uses the No Network record;
  - a typed unknown Network ID is rejected.
- crm-dev end to end, without a real identity: a verified session was created server-side and submitted through `submit_onboarding` with and without a Network ID. The records were checked and then removed.

## Not in this change

- Linking a No Network request to a real Network later (staff workflow).
- Rate limit on `ensure_provisioning_draft` (stakeholder answer Q-SEC-1).
- Caching HFR licence lookup failures so facilities without a licence do not log an error on every page load (PR #109 follow-up).
- Sweeping `develop` for other Frappe 16-only behaviour on this Frappe 15 deployment (see also PR #108).

## Follow-up after retest

After PR #111 was deployed, the retest still showed two OTP emails, and submitting without a Network ID failed with "The configured default Network ID is not available" (HTTP 417 from `check_onboarding_conflicts`).

### Duplicate OTP: one queue row, two deliveries

- The crm-dev request log showed one `start_identity` call and one Email Queue row (one recipient, Sent) per test, yet two emails arrived.
- `schedule_email_queue_redaction` (`crm/api/_email.py`) wraps the queue's after-commit send so the OTP is scrubbed from Email Queue after delivery. It was written for Frappe 16, where `frappe.sendmail(now=True)` defers the send to after commit.
- On Frappe 15, `sendmail(now=True)` sends immediately and records "Sent" only in the database. There is no after-commit send to replace, so the helper appended its own `queue_doc.send()`. The in-memory `queue_doc` still said "Not Sent", so the same message went to SES a second time.
- This affected every OTP email that uses the helper: facility self-onboarding, opt-in, contract signing and checkout.
- Evidence on crm-dev, sending one real facility-onboarding OTP to the SES mailbox simulator and counting `send_raw_email` calls:

| Code | Email Queue rows | SES messages |
|---|---|---|
| `develop` (PR #111) | 1 | **2** (two MessageIds) |
| This fix | 1 | **1** |

**Fix:** the after-commit callback sends only while the queue row is still "Not Sent" or "Partially Sent" in the database, using a freshly loaded copy. Frappe 16's deferred send still happens once, and a Frappe 15 email that was already delivered is not sent again.

### No Network: the pre-submit check still required a Network

PR #111 made `submit_onboarding` accept a blank Network ID, but the browser first calls `check_onboarding_conflicts`, which still threw when there was no Network ID and no default Network. The mocked Playwright test returned success for that call, so it did not catch this.

**Fix:** `check_onboarding_conflicts` rejects only a Network ID that was typed and is not available. A blank ID is checked against the No Network record that `submit_onboarding` uses, without creating it.

### Verification

- Python:
  - `crm.tests.test_email_redaction`: a real `frappe.sendmail(now=True)` in SES mode, with the redaction helper, reaches the transport once (it reached it twice before the fix); a Frappe 16 style deferred send still runs once.
  - `crm.tests.test_facility_onboarding_session`: the conflict check accepts a blank Network ID (checked against No Network), uses a typed Network ID, and still rejects an unknown one.
  - `crm.tests.test_facility_onboarding`: the same 15 pre-existing fixture failures with and without the change.
- Playwright against the live crm-dev server: two sessions were seeded server-side with known codes. Only `start_identity` was stubbed, because it needs a real national ID and sends a real email. `verify_otp`, terms, packages, `check_onboarding_conflicts` and `submit_onboarding` all ran on the real server.
  - Without a Network ID: all calls HTTP 200; the membership and Deal point at No Network; the evidence row is recorded.
  - With Network ID `623161`: all calls HTTP 200; the membership and Deal point at that Network.
  - The test records were deleted afterwards, except the append-only evidence rows and the No Network record.

### Still open

- `link_facility` in `crm/api/customer_experience.py` (signed-in customers adding a facility) still requires a Network ID or a configured default.
