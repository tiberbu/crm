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
- Invitation email delivery remains immediate (`now=True`); SMS delivery and
  its existing retry/audit path are unchanged.

## Verification

The opt-in backend suite covers duplicate resend suppression, old timestamps,
automatic invitation behavior, and existing signing transitions. Migration on
`crm.io` produced an active Scheduled Job Type with the expected cron and a
persisted timestamp column.
