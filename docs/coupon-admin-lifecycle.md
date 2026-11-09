# Coupon admin: lifecycle, search and audit

Settings › Coupons. Date: 2026-11-09.

## Lifecycle

| Status | How it gets there | Effect |
|---|---|---|
| Inactive | Default for every new coupon; **Disable** on an Active coupon | New orders cannot use it. Reservations already made still grant (disable is a pause). Facilities can still be assigned while it is a draft. |
| Active | **Enable** on an Inactive coupon | Live. Enabling runs the normal validation, so it is refused if another live coupon of the same network covers an overlapping window. |
| Revoked | **Revoke** from Inactive or Active, with an optional reason | Terminal. New orders and unpaid reservations stop using it; granted tokens are never taken back. |

`derived_status` order: Revoked > Inactive > Scheduled > Expired > Exhausted > Active.

Existing coupons are not migrated: whatever was Active stays Active.

## API (`crm.api.coupons`)

- `enable_coupon(name)` / `disable_coupon(name)`: toggle Inactive ↔ Active. Refused on a revoked coupon.
  Each real change stamps `enabled_on`/`enabled_by` or `disabled_on`/`disabled_by` (the latest of each;
  a no-op toggle does not move them). Earlier toggles remain in the document's Version history.
- `revoke_coupon(name, reason)`: unchanged; the UI now sends the reason.
- `list_coupons` / `get_coupon` also return `network_name` (the network's display name),
  `owner`, `creation`, `created_by_name`, `enabled_on`, `enabled_by_name`, `disabled_on`,
  `disabled_by_name`, `revoked_on`, `revoked_by`, `revoked_by_name`, `revocation_reason`.
- `assign_coupon` accepts Inactive coupons; only Revoked ones are refused.

## UI

- Search box filters by partner network name, network ID, coupon title or code. The tab counts follow the search.
- Tabs: All, Active, Inactive, Revoked.
- Each card shows **Created** (who · date), **Last enabled** / **Last disabled** (who · date) once
  they have happened, and, once revoked, **Revoked** (who · date) and **Reason**.
- The actions menu shows Enable or Disable, plus Revoke, for any coupon that is not revoked.

## Plans: Flex, Fixed or Both (2026-11-09, P-107 to P-115)

Every coupon says which plans it is for (**Applies to**):

| Applies to | What a facility gets | Fields |
|---|---|---|
| Flex | Complimentary tokens on a Flex token package order (as before) | Value type, value, token cap |
| Fixed | A percentage off the Fixed package price on that order. No tokens | Fixed plan discount (%) |
| Both | Flex orders get the tokens; Fixed orders get the discount | Both of the above |

- Coupons created before this change are **Flex**. The plan and the discount cannot change once a coupon has been used.
- The plan is checked three times: the order only picks up a coupon that fits its plan; confirming an order refuses a coupon for the other plan; the metering app never grants tokens for a Fixed-only coupon.
- A Fixed discount is ERPNext's `discount_percentage` on the package line, marked with the coupon. It is copied to the invoice. Its redemption (plan Fixed, discount % and amount, 0 tokens) is Reserved when the order is confirmed and Granted once the invoice is fully paid.
- A confirmed discounted order keeps its price if the coupon is later revoked or expires. Drafts lose the discount at the daily reconcile.
- A facility still uses one coupon once, whichever plan.
- **Bonus tokens need a Flex purchase:** the welcome bonus and coupon tokens go only to a facility with a Flex package order that is not cancelled. The Deal › Metering **Dispense** button is disabled otherwise and explains why.
- **Customers:** the CX Portal order review shows the discount ("Coupon: 5% off … −KES 750"). A Fixed facility's page shows a **Subscription** card (active since, expires).

Design: `_bmad-output/coupon-plan-scope/planning-artifacts/adr-coupon-plan-scope.md`.
