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
- `revoke_coupon(name, reason)`: unchanged; the UI now sends the reason.
- `list_coupons` / `get_coupon` also return `network_name` (the network's display name),
  `owner`, `creation`, `created_by_name`, `revoked_on`, `revoked_by`, `revoked_by_name`, `revocation_reason`.
- `assign_coupon` accepts Inactive coupons; only Revoked ones are refused.

## UI

- Search box filters by partner network name, network ID, coupon title or code. The tab counts follow the search.
- Tabs: All, Active, Inactive, Revoked.
- Each card shows **Created** (who · date) and, once revoked, **Revoked** (who · date) and **Reason**.
- The actions menu shows Enable or Disable, plus Revoke, for any coupon that is not revoked.
