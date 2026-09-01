# Opt-In signatory defaults

The Opt-In Settings page is the source of truth for the default Tiberbu contract
signer. The preferred fields are **Default signatory name**, **Default signatory
email**, and **Default signatory mobile number**. They support an external signer
who does not have a CRM User account and are pulled automatically into the
Quoting page preview and every newly generated contract.

The older **Legacy signatory User (fallback)** field remains supported. It is
used only when the contact fields are blank, so existing installations continue
to resolve the same signer and live User email/mobile number after migration.

The approval contact remains a separate name/email/phone triplet. It receives the
internal approval notification after all contract signatories complete; it is not
silently substituted for the contract signer.

## Contract-only overrides

The Quoting page retains **Add Tiberbu Signatory**. This creates or edits a
signatory on the current contract only and does not overwrite the global Opt-In
default. That is useful for a one-off contract or a legacy contract generated
before the default was configured.

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
still rotates the token and sends a new message. Network signer configuration is
also normalized by email when contracts are generated, protecting older imports
that contain the same signer more than once.

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
