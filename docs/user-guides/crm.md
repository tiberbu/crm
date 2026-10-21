# CRM User Guide

**Audience:** CRM sales, Network operations, and onboarding support\
**Start in:** CRM\
**Your outcome:** keep the Network and facility record accurate, complete the Opt-In and signature workflow, and hand eligible commercial work to Finance.

## A quick map of the work

1. Confirm the Network and its Partner ID are ready for the facility.
2. Find the facility by its name or open the incoming Opt-In submission.
3. Check identity, facility, Network, package, and contact details.
4. Complete the required facility and Network signature steps.
5. Review the linked Deal and commercial documents.
6. Hand eligible work to Accounts and confirm Customer Experience reflects the permitted status.

## Prepare the Network

Before sending an invitation or processing a facility request, open the Network record and confirm:

- The Network is enabled and the displayed name is the one the facility owner should see.
- The Partner ID is correct. It is a routing identifier that owners can enter during onboarding; it is not a password or access grant.
- The Network contact and signatory details are current and monitored.
- The facilities and package catalogue match the intended offer.
- The billing schedule is understood by the team. Package selection does not by itself create an invoice.

If a contact, Partner ID, price, or schedule is wrong, ask the Network administrator to correct the Network configuration before the owner submits. Do not compensate by editing the owner's submission after the fact.

## Process a facility request

### Open the right record

Use the CRM facility name, owner, Network, and submission reference to locate the request. Use MFL, FID, or registration number when you are reconciling a registry identity or investigating a mismatch. For normal local CRM work, search by facility name.

Open the Opt-In submission and verify that it points to the intended facility and Network. Keep the canonical submission reference available for questions and duplicate checks.

### Review the details

Check each section before using a workflow action:

| Check | What to confirm |
|---|---|
| Facility | Facility name, level, and registry-sourced identity match the owner's selection. |
| Owner | The contact information belongs to the person who completed verification and can receive the next instruction. |
| Network | The Partner ID resolved to the intended enabled Network. |
| Package | The selected package is available for the Network and attached to the correct facility. |
| Terms | The required version was accepted and the acceptance is recorded. |
| Duplicate | Search for an earlier submission for the same facility and owner before creating another. |

If the facility's registry facts are wrong, pause and route the correction through registry support. CRM should preserve the source and report the mismatch instead of silently replacing a registry value.

### Complete signatures and Opt-In

Follow the record's available workflow actions in order. Confirm that the required facility owner and Network signatories have completed the signature process and that the CRM record shows the resulting native status. A request being submitted, a package being selected, or a confirmation email being sent does not mean the agreement is fully signed.

When a signature is missing:

1. Confirm which party's action is outstanding.
2. Confirm the correct email/contact and resend through the available workflow if appropriate.
3. Ask the intended signer to use their own link; do not sign on their behalf.
4. Keep the same submission reference and resolve a delayed status against the existing record.

Do not manually mark an Opt-In complete to get past a missing signature or accounting handoff.

## Review the commercial handoff

Open the linked Deal and review its facility, Network, package, and values. Follow the native quotation and Sales Order links when they exist. Confirm that the commercial records refer to the same facility and Network as the signed Opt-In.

The facility signatory can trigger the Year 1 quotation and Q1 Sales Order handoff. Invoice creation follows the Network's configured billing schedule. Therefore:

- A selected package can exist before there is an invoice.
- A Sales Order does not always mean an invoice should already exist.
- A checkout attempt is not the accounting record of a settled receipt.
- Accounts records and allocates receipts using ERPNext Payment Entries.

When the signed record is eligible, hand it to Accounts with the Opt-In submission, Deal, customer, facility, Network, and linked quotation/order references. If there is no invoice, check the billing schedule and record explanation before raising an exception.

## Resolve common exceptions

| Situation | CRM action |
|---|---|
| The facility is missing from the owner's verified list | Keep the attempt reference and ask for registry/ownership review. Do not choose a similarly named facility. |
| The Partner ID resolves to the wrong Network | Stop the workflow and correct the invitation or Network configuration before signature. |
| A second Opt-In exists | Compare the original submission and its state. Continue the canonical request; do not duplicate the commercial handoff. |
| Signature is pending | Identify the signer and resend or follow up through the existing signature workflow. |
| Facility or owner data conflicts with the registry | Preserve the source value and route a registry correction. |
| A signed submission has no accounting documents | Check the Network schedule and existing linked records, then hand off with references if eligible. |
| Customer Experience displays stale or unavailable setup status | Keep CRM and billing records intact; route the setup-status issue to implementation support. |

## Stakeholder responsibilities

CRM owns Network setup, Opt-In submissions, facility membership context, signature state, and commercial handoff references. HFR supplies authoritative registry facts. ERPNext owns quotations, Sales Orders, Sales Invoices, and Payment Entries. The implementation service owns HMIS deployment state and any site-health details it publishes.

CRM staff should use only the records and workflow actions granted to their role. Customer Experience is the facility owner's permitted view; do not change CRM state to simulate an upstream result.

## Handoff to Finance and the facility owner

**CRM → Finance:** signed Opt-In and the linked customer, facility, Network, Deal, quotation, Sales Order, and schedule context. Accounts reviews eligibility and processes native accounting records.

**CRM → Customer Experience:** the authorized facility and Network relationship plus the latest available customer-safe workflow state. The owner sees permitted invoices, payments, token orders, and implementation status from their facility view.
