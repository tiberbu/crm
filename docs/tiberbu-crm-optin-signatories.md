# Opt-In signatory defaults

The Opt-In Settings page is the source of truth for Tiberbu signing and approval
contacts. The **Tiberbu signing and approval contacts** table supports one row per
external or internal contact with a role, name, email, and optional mobile number.
Rows are pulled automatically into the Quoting page preview and every newly
generated contract. The **Tiberbu signing rule** controls whether **All must sign**
or **At least one must sign**; facility, witness, and network signatories remain
required in either mode.

The older **Legacy signatory User (fallback)** field remains supported. It is
used only when the contact fields are blank, so existing installations continue
to resolve the same signer and live User email/mobile number after migration.

The legacy approval name/email/phone triplet remains supported as a fallback. Each
configured Approver row receives the internal approval notification after all
required contract signatories complete; it is not silently substituted for a
contract signer.

Existing flat fields are retained as migration-safe fallbacks. The migration
patch seeds the table only when it is empty (including resolving the legacy User
link), so an administrator's configured rows are never overwritten.

## Contract-only overrides

The Quoting page retains **Add Tiberbu Signatory**. This creates or edits a
signatory on the current contract only and does not overwrite the global Opt-In
default. That is useful for a one-off contract or a legacy contract generated
before the default was configured.

The Contracting panel also provides **Sync from settings**. It adds current
network and Tiberbu rows to the open contract and updates unsigned rows. Signed
rows are deliberately skipped and cannot be edited or removed, even when the
settings table changes. The quote-page Add/Remove controls remain available for
one-off unsigned Tiberbu contacts. Tiberbu Approver rows are shown separately on
the same quote panel for a visible hand-off; they are not added as signing rows.

When the required signature rule is satisfied, the workflow marks the contract
**Fully Executed** and sends the facility one immediate email containing the
`CRM Contract Standard` PDF. A sent timestamp prevents duplicate delivery; a
failure is logged without undoing captured signatures so an operational retry can
be added safely later.

## Dashboard wording and duplicate handling

Signatory leaders are grouped by role and normalized email (or normalized name
when no email exists). Duplicate child rows from retries or legacy data count
once per contract. The list now reads **N of M signed** when complete, or **N of M
signed · P pending** when work remains. The API also returns `assigned` and
`pending` for downstream consumers.

Regression coverage includes external-contact resolution, legacy User fallback,
Quoting-page auto-resolution, and duplicate dashboard child rows.

## Invitation delivery idempotency

The first Facility Signatory signature unlocks the remaining signing invitations
in one wave. That transition takes a database row lock on the contract before it
checks `invite_token`, so duplicate requests or browser retries wait for the
first wave and then observe the already-issued tokens. A signatory therefore
receives one invitation per automatic trigger; a deliberate **Resend link**
still rotates the token and sends one new message with a `[Reminder]` subject
prefix. Editing a signatory after an invitation was issued also uses that prefix
when a fresh link is required. Network signer configuration is also normalized by
email when contracts are generated, protecting older imports that contain the same
signer more than once.

## Removing an unsigned co-signatory

The Quoting page's Contracting panel includes a **Remove** action for Network and
Tiberbu co-signatories whose current contract row is still unsigned. The action is
manager-only, asks for confirmation, and targets the exact child row so repeated
Network Signatory rows cannot remove the wrong person.

The server is authoritative: it refuses removal when the row is Signed (or has a
signature timestamp or captured signature data), even if the browser shows a stale
Pending status. Removal deletes the invitation-bearing row from this contract,
which makes its old link inactive, records a deal activity event, and re-evaluates
the normal contract transition. The configured network or global Tiberbu contact is
not deleted, so it remains available as the default for future contracts and can be
added again when needed.

## Network-scoped records and CRM signatories

Every opt-in pipeline record carries an **Opt-In Network** Link when the site
has run the network-link migration. The field is present on the submission,
deal, contract, quotation, Sales Invoice, Payment Entry, onboarding request,
rebate voucher, and sales commission records. Existing `network_slug` values
remain in place for public URLs and compatibility. The migration is idempotent,
skips doctypes that are not installed (including ERPNext doctypes on a CRM-only
site), and backfills only empty Link fields.

To scope a network user, create a Frappe **User Permission** for that user on
`CRM Opt-In Network` and select the permitted network. Because the pipeline
records use real Link fields, standard Frappe list and document permission
checks filter records belonging to other networks. Contacts and organizations
are intentionally not stamped with one network: they can be shared by several
facilities or networks and are not the access boundary.

When a Network Signatory or Tiberbu Signatory is also a CRM User, the Quote
page shows **Your signature is required** only when that signed-in user's email
matches a pending signatory on a network-scoped contract and the facility
signatory has completed their step. The user can review the contract and sign
from the CRM page with the existing signature pad; this authenticated branch
does not issue a second email OTP. The public invitation URL remains protected
by its existing HMAC invitation token, email/SMS OTP, and short-lived signing
token, so external signatories are unchanged.

Internal approvers who are CRM Users receive a sign-in nudge rather than a
public contract URL. Its link opens Opt-In Requests with `Pending my action`
selected. The filter matches pending network/Tiberbu signers and configured
approvers while respecting the records returned by Frappe permissions.

CRM-user Network and Tiberbu Signatories follow the same login-only rule. They
do not receive a contract invitation email, public signing URL, OTP, or signing
SMS. Once the facility signature unlocks the contract, the first hand-off is
recorded on the Deal activity timeline and the signer uses the authenticated
Quote/Opt-In signing action. A scheduler runs every two hours and sends each
still-pending CRM user a separate, facility-named reminder email linking to the
permission-scoped `Pending my action` list. The reminder timestamp is stored on
the signatory row, and every successful reminder is recorded on Deal activity;
failed sends are logged without advancing the timestamp.
