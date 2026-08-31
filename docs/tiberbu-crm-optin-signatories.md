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
