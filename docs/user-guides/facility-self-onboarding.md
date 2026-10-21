# Facility Self-Onboarding and Token Selection

**Who this is for:** facility owners and the CRM/onboarding staff who help them\
**Start here:** `/facility-onboarding`\
**What you will complete:** verify the owner, choose eligible facilities, select one package per facility, confirm the Network and terms, and submit an Opt-In request.

This walkthrough uses the demonstration facility **Alpha Community Clinic**, the **Example Health Network**, and sample prices. The records and prices shown in the screenshots are synthetic and are not an offer or invoice.

## The journey at a glance

1. Estimate package needs (optional).
2. Verify identity and access to the one-time code.
3. Confirm facilities returned for that identity.
4. Confirm the correct Network.
5. Select a token package for each facility.
6. Review the total and accept terms.
7. Submit once and keep the confirmation.

## Step 1 — Start and size a package

Open the onboarding page. The welcome page explains the steps and includes an optional sizing calculator. Choose a clinic profile, enter an approximate average number of patient encounters, and review the monthly demand and package runway estimate. The estimate helps compare packages; it does not set the final price or reserve tokens.

![Onboarding welcome and token sizing calculator](images/onboarding-01-welcome.png)

*The sizing calculator is optional. You can begin identity verification without choosing a recommendation first.*

Select **Start secure onboarding** when ready. If someone has already invited you and provided a Network context, use that invitation link. If you already have Customer Experience access, choose **Sign in** rather than starting another onboarding request.

## Step 2 — Verify the facility owner

Choose the requested identification type and enter the number exactly as issued. The screenshot uses a synthetic number. Do not include spaces unless the form asks for them. Select **Find my facilities** once.

![Identity entry](images/onboarding-02-identity.png)

The system checks identity before returning a facility list. It should not reveal whether an identifier belongs to a record before verification succeeds. If the request is still processing, leave the page open and follow the on-screen status; do not repeatedly submit the same identifier.

## Step 3 — Enter the one-time code

The code is delivered to the masked email address or phone number displayed by the page. Enter all six digits, then select **Verify and continue**. A code may be pasted into the first box; the form moves between digits automatically.

![One-time code entry](images/onboarding-03-otp.png)

If the code is wrong or expired, the page shows an inline message. Request another code after the resend countdown ends. Check the displayed destination and your message inbox before requesting a resend. Never share the code with a caller or support agent.

## Step 4 — Confirm the facilities

The facility list is returned for the verified owner. Compare the facility name, level, type, and registry identifier against your records. Tick each eligible facility you want to onboard under the same Network. You can select more than one facility; each selected facility needs its own package selection in the next step.

![Facilities returned for the verified owner](images/onboarding-04-facility-selection.png)

A facility that is already onboarded or not eligible is identified on the card and cannot be selected. Registry facts are not editable in this flow. If a name, level, or ownership detail is wrong, stop and request correction through the registry support route.

Select **Continue to pricing** after reviewing every selected facility. If the facility you expect is missing, do not add a substitute facility by typing an identifier into the page. Contact the support channel and quote the identity-verification attempt time.

## Step 5 — Confirm the Network and compare packages

The package page shows the facility currently being priced and the Network associated with the onboarding context. If you were referred by a Network, use **Referred by a partner?** to enter the Network Partner ID. If the flow already has a configured default or invitation context, verify the displayed Network name before you continue. A Partner ID identifies a Network; it is not a password or proof that you own a facility.

![Token package catalogue with facility, Network, VAT, and package quantities](images/onboarding-05-token-packages.png)

Compare the package name, monthly amount, VAT, total, token quantity, and coverage description. The sizing calculator is available from this screen if you want to revise your estimate. The price and package are loaded from the configured catalogue; you cannot enter a custom token quantity or price.

For each selected facility:

1. Select **Choose plan** on the package that fits expected activity.
2. Confirm the chosen card is selected and the facility summary reflects the package.
3. If multiple facilities are selected, switch through each facility and choose its package separately.
4. Review the combined quantity and total before moving on.

![Selected token package](images/onboarding-06-package-selected.png)

The quantity shown here belongs to the selected package/order. It is not a live remaining-token balance and does not confirm that a Go Live setup has received or consumed tokens. Any free package shown in the live catalogue has a zero charge; a paid package shows its configured price and VAT. The available choices depend on the Network's current configuration.

## Step 6 — Review, accept, and submit

The review page brings the key decisions together: Network, facility list, package for each facility, Customer Experience email, terms, and the server-calculated total. Check every row. Use **Edit** beside Network, facilities, or package to correct a selection before submitting.

![Review page showing Network, facility, selected package, terms, and VAT total](images/onboarding-07-review.png)

Read the terms in the page. Tick the acceptance box only after reviewing them. The submit button remains unavailable until required information and acknowledgement are complete. The total shown by the server is the amount to use when reviewing the resulting commercial records; do not rely on the sizing estimate for the final amount.

Select **Submit facility onboarding** once. Do not refresh or resubmit because the page takes a moment to respond. Keep the submission reference shown on completion.

## Step 7 — Understand the confirmation

![Onboarding submission confirmation](images/onboarding-08-submitted.png)

The confirmation means the onboarding request was accepted and the selected facility was linked to the Network workflow. Check the listed next step and email instructions to sign in to Customer Experience. Submission does not mean all signatures are complete, an invoice has been issued, payment has settled, tokens are currently available, or the HMIS site is live.

## What happens to the package and payment?

| What you see | What it means | What to do |
|---|---|---|
| Package selected, no invoice | The selected service package is recorded for the onboarding request. Billing may happen later under the Network's configured billing schedule. | Keep the submission reference; check Customer Experience for the invoice when one is issued. |
| Invoice with an amount due | Finance has issued an invoice for the linked order. | Open the invoice, confirm the facility and amount, then use a payment option shown for that invoice. |
| Payment awaiting verification | A payment attempt or submitted payment reference has not yet been matched/confirmed. | Do not start another payment until the page tells you the prior attempt is resolved. Use Network Support if it remains pending. |
| Paid invoice | The accounting record reports the balance settled. | Keep the receipt/reference. Token entitlement and Go Live readiness remain separate statuses. |
| Go Live not started or in progress | HMIS implementation has its own setup workflow and status source. | Review the facility view and follow the named next action; contact implementation support if status cannot be refreshed. |

## If the journey does not go as expected

| Situation | Safe next step |
|---|---|
| Code not received | Confirm the masked destination, check junk/spam or SMS messages, wait for the countdown, then resend once. |
| Code rejected | Check all six digits and expiry. Request a fresh code if necessary; do not share it. |
| Facility missing or details disagree | Stop before submission. Request an HFR ownership/data correction and provide the safe attempt reference. |
| Wrong Network is shown | Do not submit. Return to the Partner ID step or ask the inviter to confirm the intended Network ID. |
| Package or total is unexpected | Do not submit. Recheck the package, quantity, VAT, and selected facility; contact the Network if the configured offer is wrong. |
| Submit appears stuck | Keep the page and confirmation/reference. Ask support to look up the request before attempting another submission. |
| Invitation link is expired or incorrect | Ask the inviter for a fresh link. Do not reuse another facility owner's link. |

## Notes for CRM and onboarding staff

- Confirm an enabled Network and its Partner ID before sending an invitation. A Partner ID is a public routing identifier, not an access credential.
- Confirm the Network contact and customer-facing instructions are current.
- HFR supplies ownership eligibility and facility facts. Preserve the registry source; route corrections instead of editing HFR values in the onboarding case.
- The configured package catalogue supplies eligible package items and pricing. The owner may select from offered options only.
- Reconcile duplicates by the original submission reference. Do not create a replacement request until the original outcome is known.
- Pass the canonical Opt-In submission, Network, facility, selected package, and signature state to the next CRM/Finance workflow. Do not treat the welcome screen, package selection, or owner confirmation as a signed or paid state.

## Handoff

**Facility owner → CRM:** verified owner session, selected HFR facilities, resolved Network, package choice, terms acknowledgement, and Opt-In submission reference.\
**CRM → Accounts:** signed commercial records and any invoice work eligible under the Network's billing schedule.\
**CRM/Accounts → Customer Experience:** the authorized facility view of progress, invoices, payments, and reported implementation status.
