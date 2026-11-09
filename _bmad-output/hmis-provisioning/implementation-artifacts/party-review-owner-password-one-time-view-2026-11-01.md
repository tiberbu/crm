# Party review: one-time view of the temporary HMIS owner password

**Date:** 2026-11-01
**PR:** #126
**Room:** Mary (analyst), John (PM), Winston (architect), Amelia (dev), Sally (UX), Murat (test architect)
**Maintainer decision:** when `get_provision_status` returns `login.password`, CRM presents it to the facility's owner through a one-time view with a copy button. It is not available again after the window closes. Communication is backend to backend.

## Why the email-only path is not enough

- The v2.0 contract does not say whether the credentials email is sent by the setup service or by the new HMIS site.
- "Forgot password" is always sent by the target HMIS site, from its own mail settings. A site whose configuration is not finished may not send mail.
- `login.email_sent: false` is the signal that mail did not go out. That is also exactly when the setup service returns `login.password`.
- So with an undelivered email, both the credentials email and "Forgot password" can fail, and the owner cannot sign in without support.

## Decisions

| # | Decision |
|---|---|
| P-1 | The polled status carries only `password_available`. The password is never in it. |
| P-2 | Viewer: the signed-in portal user whose verified email equals the HMIS owner `login.email` (the Opt-In signatory or the OTP-verified self-onboarded owner). Nobody else, System Managers included. |
| P-3 | Offered only when the site is live, `login.status` is Created, `email_sent` is false and a password is present. |
| P-4 | One view per FID and setup record. The sequence is: per-FID lock → refuse if a `Viewed` record exists → fetch → insert `CRM HMIS Credential View` → commit → return. A System Manager can set the record to `Re-armed` to allow one more view. |
| P-5 | POST only, rate-limited, fetched fresh server to server. Never stored, cached or logged; errors never carry the password. |
| P-6 | Confirm step, then a dialog with Copy. Close needs "I have copied and saved this password". Escape and the backdrop do not close it. A leave-page warning shows while it is open. Cleared from memory on close. |
| P-7 | After viewing, the card says when it was viewed, that it cannot be shown again, and links to Network Support. |
| P-8 | Contract v2 §6.1 is amended. Asks to the HIMS team: say who sends the credentials email; let CRM acknowledge a view so the password stops being returned; mark the password temporary (forced change at first sign-in) if HMIS supports it. |
| P-9 | Email sent, or no password returned: unchanged instructions (credentials email, "Forgot password", Network Support). |

## Risks accepted

- If the reveal response is lost after CRM commits the view record, the owner did not see the password, but it counts as viewed. Support re-arms it.
- The password is visible on the owner's screen while the dialog is open.
- A partner or other portal user who onboarded the facility, but is not its HMIS owner, cannot view it (P-2). The maintainer can widen this later.
