# Party-mode review — 2026-11-12

Cast: Mary (analyst), John (PM), Winston (architect), Sally (UX), Amelia (dev). Session mode, non-interactive.

Verdicts
- #1 Rename: labels only; keep `/finance-cockpit` route (deep links, Customer 360, Desk page name).
- #2 Link: remove the Opt-In row; absolute coupon URL from `window.location.origin`. Open point: header "Open Opt-In" preview link kept — maintainer decides.
- #3 Responsiveness: two distinct root causes (flex-shrink squeeze on Network page; viewport breakpoints inside the fixed-width opt-in card). Fix structurally, not with zoom-specific CSS.
- #4 Access email: never wired to signature on develop; PR #162 closed unmerged. Revive with trigger = facility signatory + witness; brand colour fix required (#162 used blue).
- #5 Optional services: configurable (network → settings → Standard Selling); dev site shows token packages because Standard Selling holds every Item — use a dedicated price list.

Risks
- OIS rows already `Sent` from the old processing-time welcome are skipped (idempotency); they already received a set-password link.
- New Select option needs `bench migrate` on each site (applied on the dev site).
- Contracts created manually from a Deal (no OIS) send no access email (unchanged decision from 2026-11-05).
