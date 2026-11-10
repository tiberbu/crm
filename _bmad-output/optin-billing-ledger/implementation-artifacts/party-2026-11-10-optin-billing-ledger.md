# Party Mode (research): the Opt-In billing ledger and paying ahead (2026-11-10)

**Led by:** 🎨 Sally (UX Designer), with 🏗️ Winston (Solutions Architect)
**Also in the room:** 📊 Mary (Business Analyst), 📋 John (Product Manager), 💻 Amelia (Developer), walk-ons 😤 Grumbal (The Adversary) and 🌶️ Boundary (Edge-Case Hunter)
**Mode:** research first (code and dev-site data on the table), then design, implementation and Playwright review
**Brief (owner):** On the CX Portal, *Opt-In Requests* shows `[object Object]` top right. Quotations are badly arranged, Orders & Invoices don't look live. On an Opt-In facility the quotes are not clickable. A client should be able to come today and pay Q1, come tomorrow and pay the next two quarters, without waiting for the cron job. On first view show the expected payment dates and a clear call to action with instructions for paying ahead. Make Opt-In as predictable as Express (see order → generate invoice → pay). Clear visibility for the customer and the CRM admin.

## Evidence on the table (research)

| # | Observation | Source |
|---|---|---|
| E1 | `[object Object]` is the network: `partnerName(ois.network)` gets the whole network dict from `_portal_network()`. The Facilities list does it right with `network.display_name`. | `FacilityPortal.vue` `optinRequests`, `website_redirect._portal_network` |
| E2 | The "Orders & Invoices" tile is two counts of *open* records only (`per_billed < 100`, `outstanding > 0`). Paid invoices and payments vanish, so the card never moves after a payment. | `customer_experience._order_rows`, `checkout._invoice_rows` |
| E3 | Quotations render as `names.join(' · ')`: five yearly quote numbers run together in one tile, no year, no amount, no link. | `OptInRequests.vue` |
| E4 | An OIS-only facility page gets `payments: []` and only outstanding invoices. Quote rows on the facility page are plain text. | `FacilityPortal.vue` `allFacilities`, `BillingJourney.vue` |
| E5 | The schedule is 20 rows (5 years × 4 quarters) in `billing_schedule_json`. Every row's `period_label` is "Quarter N", so Year 1 Q1 and Year 3 Q1 both read "Quarter 1" and the PlanPanel keys collide. | dev OIS-2026-00001, `PlanPanel.vue` |
| E6 | Signature creates the Y1-Q1 Sales Order (invoice deferred). The hourly worker invoices a row only on or after its `invoice_date` (3 months after submission). No path lets the customer or staff issue a period early. | `optin_billing.handoff_facility_signed`, `process_due_optin_billing` |
| E7 | A worker failure marks a row `Failed` and the worker never retries it (it only takes `Scheduled`). Nobody sees the error outside the JSON. | `process_due_optin_billing` |
| E8 | Yearly quotes 2–5 are docstatus 0; the portal labels them "Planned". The signed contract already commits to them. | dev data, `quote_status_label` |
| E9 | Orders created with `ignore_validate` keep `status = Draft` while `docstatus = 1`. | dev Sales Orders |
| E10 | The Deal Quoting tab shows the yearly quotations and commitment total but nothing about the quarterly schedule, orders, invoices or payments. | `QuotingTab.vue`, `lifecycle.get_deal_lifecycle` |
| E11 | Express already has the pattern the owner wants: draft order → "Review order and pay" → invoice → "Choose payment" → Payments tab. Customer-linked facilities page their full history from `facility_documents`. | `BillingJourney.vue`, `facility_documents.py` |

## The session

🎨 **Sally:** Before anyone designs anything: the top-right `[object Object]` is a *trust* bug, not a cosmetic one. It sits where a customer looks for "who am I paying". Mary, what were they meant to see there?

📊 **Mary:** The partner network's name. E1. The Facilities list already reads `network.display_name`; this card passed the dict. One-line fix, but it tells you nobody ever looked at this page with a real Opt-In.

😤 **Grumbal:** And the "live" complaint is real too. E2. You pay, the invoice leaves the "due" count, the card says "0 open · 0 due". Looks like nothing ever happened. A finance person reads that as *my payment disappeared*.

🏗️ **Winston:** So the card needs a ledger, not counters. And the ledger already exists: `billing_schedule_json` has every period with its date and amount. ERPNext has the orders, invoices and payment entries. We join them at read time. No new DocType, no second source of truth.

📋 **John:** One read endpoint per submission, then. And one write endpoint for the owner's real ask: *pay ahead*. Today Q1, tomorrow Q2 and Q3.

🌶️ **Boundary:** Pay ahead *which* quarters? If I can pick Y2-Q3 while Y1-Q2 is unissued, the ledger has holes and the worker invoices around them.

🏗️ **Winston:** In order only. "Issue the next N periods." The next unissued row is always the earliest, so there are no holes, and the worker's own loop simply skips rows that already carry a `sales_invoice`. The cron keeps running untouched.

😤 **Grumbal:** Then I click "next 20" and drop five years of invoices on the books. Finance hates me, and the customer hates the overdue reminders.

📋 **John:** Up to four per action, one year ahead. And no new invoice while four are already unpaid on the submission. You can pay ahead as far as you want, a year at a time, but you can't stack up unpaid paper.

🌶️ **Boundary:** Due dates. If I issue Y1-Q3 today, is it due in 30 days? It isn't due on the contract until next August.

📊 **Mary:** Then issuing early must never make it due *sooner* than the contract says. Posting date today, due date the later of today and the scheduled due date. Paying ahead is a choice, not a trap.

🎨 **Sally:** Now the screen. The owner said "on first view, see the expected payment dates". So the ledger is the page, not a hidden "Upcoming invoices" toggle. Top: five tiles, same label and value style — Contract value, Invoiced, Paid, Outstanding, Next payment. Then the schedule, grouped by year, each quarter one row: dates, amount, state, and the document trail — order, invoice, payment — as links.

💻 **Amelia:** The state words. I want them fixed before I write a badge: *Scheduled*, *Order ready* (order exists, no invoice), *Due*, *Overdue*, *Paid*, *Paid ahead* (paid before its period starts), *Needs attention* (a failed row). Status colours only for Due/Overdue/Paid/Needs attention; everything else neutral.

🎨 **Sally:** And the call to action sits above the schedule, not below twenty rows. "Pay ahead" card: a plain-language "how it works" in three steps, a stepper for 1 to 4 quarters, the exact total, and one button: *Create invoices*. Once created, each row grows a *Pay* button that opens the existing payment choices. Same as Express.

😤 **Grumbal:** Same as Express means the button says what happens. "Create 2 invoices (KES 197,844)" not "Proceed".

🎨 **Sally:** Agreed. And when it's not allowed — contract not fully signed — the card says *why* and what unlocks it, instead of disappearing.

📊 **Mary:** Quotes. E3 and E8. Year 2 says "Planned" next to a signed five-year contract; that undersells the commitment. Label them by contract state: *Accepted* when the contract is fully executed, *Awaiting signatures* before. Each one opens its PDF.

🏗️ **Winston:** PDF through a portal endpoint that checks the quote belongs to one of the user's submissions (Network) or to the customer the user can see (Express), then renders "Careverse Quote Standard". Never a raw `/printview` link — the portal user has no Quotation read permission and shouldn't.

🌶️ **Boundary:** Labels. E5. "Quarter 1" five times. The ledger says "Year 2 · Q1", always.

📋 **John:** Admin side. The owner said both sides. The Deal's Quoting tab gets the same schedule for staff, with Desk links, the error text on failed rows, and the same "Issue next period" action for a Sales or Accounts Manager — that is also the retry for E7.

😤 **Grumbal:** Staff issuing on behalf of a customer: write down who did it. `issued_by`, `issued_on`, `issued_early`. When the customer disputes an invoice, Finance needs that row.

🎨 **Sally:** Express. The owner wants the same accounting clarity there. It already has the stages; what it lacks is the money at a glance. A three-tile account strip on the facility's billing journey — Billed, Paid, Outstanding — from the same counts call, and quote rows that open the PDF.

💻 **Amelia:** And the Opt-In facility page gets a *Payment schedule* tab with the ledger component, so the facility page and the requests page tell one story. Same component, two hosts.

🎨 **Sally:** One more: a refresh button with "Updated 10:42". After Paystack returns, the context reloads anyway, but a person who paid by M-Pesa wants to see it move.

## Decisions (P-124 to P-133)

| # | Decision |
|---|---|
| P-124 | The Opt-In ledger is derived at read time from `billing_schedule_json` + ERPNext Sales Order / Sales Invoice / Payment Entry. No new DocType. |
| P-125 | Customer (portal) and staff (Desk) may issue the **next N unissued periods, in order**, N = 1–4 per action. Requires OIS `Processed` and contract `Fully Executed`. |
| P-126 | No new invoice while 4 or more Opt-In invoices on the submission are unpaid. |
| P-127 | An early invoice posts today and is due on the later of today and its scheduled due date. Issuing early never brings a due date forward. |
| P-128 | Issued rows record `issued_early`, `issued_on`, `issued_by` and keep `scheduled_invoice_date`. The hourly worker is unchanged and skips them. `Failed` rows are eligible to issue (this is the retry). |
| P-129 | Period states: Scheduled, Order ready, Due, Overdue, Paid, Paid ahead, Needs attention. Labels always "Year N · QM". |
| P-130 | Yearly quotes show *Accepted* once the contract is fully executed, else *Awaiting signatures*; each opens a PDF via a permission-checked portal endpoint. |
| P-131 | Opt-In Requests page: network name fix, five-tile summary, pay-ahead card above the schedule, schedule grouped by year with order → invoice → payment links, quotes by year, facilities. Live refresh with "Updated hh:mm". |
| P-132 | Facility page: *Payment schedule* tab for Network Opt-In facilities (same component); quote rows clickable for both journeys. Express gets a Billed / Paid / Outstanding strip. |
| P-133 | Deal Quoting tab (OIS deals): staff billing schedule with Desk links, failed-row errors and "Issue next period" (Sales Manager / Accounts Manager / System Manager). |

## Open for the owner (not blocking)

- The 4-period cap and the 4-unpaid limit are constants (`MAX_ADVANCE_PERIODS`, `MAX_UNPAID_INVOICES`). Say if a network needs different numbers.
- Paying ahead does not discount. If early payment should earn a discount, that is a pricing decision for a later change.

## P-134 — Customers never invoice before the date (owner feedback, 2026-11-10)

Supersedes the customer half of P-125/P-126. The customer keeps the full breakdown (quotes, every period's invoice
and due dates) but cannot generate an invoice for a period whose contract invoice date has not arrived, on the
Opt-In journey or on Express fixed packages. Portal issuing is `due_only`: it only catches up a period that is
already due (worker lag or a failed row). The pay-ahead card becomes "How your payments work" with a Next invoice
panel. Staff early issue on the Deal stays. Express: future-dated orders cannot be invoiced (`is_future_dated`).
