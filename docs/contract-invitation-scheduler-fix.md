# Contract invitation delivery and reminders

## Root cause

The resend endpoint loaded a contract without a row lock. Two requests from a
double-click, browser retry, or two open tabs could therefore read the same
pending signatory before either request committed. Each request rotated the
invitation token and called `frappe.sendmail(now=True)`, producing two messages
and immediately invalidating the link in the first message.

The internal reminder function was present in `hooks.py`, but `crm.io` had no
corresponding `Scheduled Job Type` row. The scheduler was enabled and workers
were online, but there was consequently no scheduled record for the daemon to
execute. The configured expression `0 */2 * * *` is correct: it runs at minute
zero every two hours.

Contract generation had a separate retry race. The UI prevents a normal
double-click, but a retried request, two browser tabs, or an integration retry
could still create a second contract for the same deal and send another
facility invitation before either view refreshed.

## Fix

- Resend and signatory-edit reads now use the parent contract row lock. A
  successful invitation records `crm_last_invitation_sent_at` on the child row.
- A second resend inside the 60-second duplicate window returns
  `already_sent`, logs the suppression on the Deal timeline, and does not send
  another email. Deliberate resends after the window still rotate the link and
  retain the `[Reminder]` subject prefix.
- The migration adds the timestamp field only when the signatory DocType exists
  and idempotently repairs the Scheduled Job Type with frequency `Cron` and
  `0 */2 * * *`. Existing `Stopped` choices are preserved.
- Contract generation now locks the deal while checking for an existing active
  contract. Retries return that contract (and its tracked invitation queue when
  available) instead of creating another contract or invitation.
- Invitation email delivery remains immediate (`now=True`); SMS delivery and
  its existing retry/audit path are unchanged.

## Verification

The opt-in backend suite covers duplicate resend suppression, old timestamps,
idempotent contract generation, automatic invitation behavior, and existing
signing transitions. Migration on `crm.io` produced an active Scheduled Job
Type with the expected cron and a persisted timestamp column.

## Internal reminder delivery

CRM-user Network and Tiberbu Signatories follow the same login-only rule. They
do not receive a contract invitation email, public signing URL, OTP, or signing
SMS. Once the facility signature unlocks the contract, the first hand-off is
recorded on the Deal activity timeline and the signer uses the authenticated
Quote/Opt-In signing action. A scheduler runs every two hours and sends one
facility-branded workload reminder per pending CRM user and network. The email
lists every pending contract (facility, role, and reference) and links to the
permission-scoped `Pending my action` list. Duplicate child rows are collapsed
for delivery, while each affected signatory row is timestamped and each unique
contract/role is recorded on its Deal activity timeline. Failed sends are logged
without advancing any reminder timestamp. Signatories without an enabled CRM
User account remain on the existing public invitation path.

The reminder is registered in both `hooks.scheduler_events` and the idempotent
migration bootstrap, using `0 */2 * * *` (minute zero, every two hours). The
bootstrap repairs a missing `Scheduled Job Type` row without changing an
administrator's stopped setting. The job reads child signatory state, so
legacy or transitional parent contract statuses cannot hide a row whose state
is `Pending`; fully executed and cancelled contracts are excluded. It uses
`frappe.sendmail(now=True)` and commits only after successful sends.

## Amazon Inspector dependency finding

Amazon Inspector reported six high-severity findings against the transitive
`brace-expansion` dependency in `frontend/yarn.lock`. The 5.x entry was already
fixed at 5.0.9; the vulnerable 2.x entry was upgraded from 2.1.0 to 2.1.4. No
application code accepts brace patterns from users, but keeping both lockfile
entries on their fixed releases removes the reported denial-of-service exposure.
