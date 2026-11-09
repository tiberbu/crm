# Party record — Customer 360 tabbed layout (2026-11-09, round 2)

Led by: 🎨 Sally (UX), 📊 Mary (business analyst), 🧪 Quinn (QA). Also in the room: 🏗️ Winston, 💻 Amelia.
Trigger: the maintainer reviewed PR #172 and asked why Orders, Quotes, Billing, Facilities and
Deals are stacked vertically. With 20 records each, the page becomes a very long scroll. They asked
whether tabs would present it better, and whether this is the best design possible.

---

🎨 **Sally:** They're right, and I'll own it. The roundtable fixed *what* the page shows and never
asked *how much* of it. Five unbounded lists stacked on one page means the twentieth order sits
below the fold of the fold. Tabs.

📊 **Mary:** Tabs hide things. On an inquiry call the admin needs "do they owe us, is anything
stuck" without clicking through five tabs to find out.

🎨 **Sally:** Then the headline stays above the tabs: the four KPI tiles, always visible. And the
first tab is an **Overview** that answers the call: customer, partner, and a short "Needs attention"
list of up to three outstanding invoices and three open orders, each with "View all".

📊 **Mary:** Counts on every tab label. "Billing 3" tells me there's something there before I click.
And make the KPI tiles jump to their tab — "Outstanding" opens Billing.

🧪 **Quinn:** My conditions. One: tabs never disappear when they're empty. Stable positions, a zero
count, and an empty state inside. Two: the open tab goes in the URL, `?tab=billing`, and survives the
facility/all-facilities toggle, reload and back. Three: 20 records must not just move the long
scroll into a tab. Paginate at 10 rows with "1–10 of 20" and previous/next, and reset to page 1 when
the data changes. Four: the Deal page's own Customer 360 tab reuses the component. That's nested
tabs, so its tab state stays local, not in the URL.

🏗️ **Winston:** Which tabs component? The Deal and Organization pages use frappe-ui `Tabs`. Same
component, same underline indicator. One surface, one design language.

💻 **Amelia:** One catch: the page re-fetches whenever the selection object changes. If `?tab=` joins
the query, every tab click re-fetches. I'll key the loader on the selection params only.

🎨 **Sally:** Tab order follows the call: Overview · Orders · Quotes · Billing · Facilities · Deals.
Billing keeps invoices and payments together, because that's one question. Each list is paginated
on its own.

📊 **Mary:** And phones?

🧪 **Quinn:** The tab list scrolls sideways (frappe-ui does that already). I'll assert that no tab
pushes the page wider than the viewport, at all four widths.

🎨 **Sally:** Is it the best design possible? It's the best one for this job. A summary that's always
visible, an overview that answers the call, and bounded lists. A dashboard of charts would be
prettier and answer fewer questions.

---

## Decisions (T1–T7)

| # | Decision |
|---|---|
| T1 | KPI tiles stay above the tabs; each tile opens its tab (Package Paid / Outstanding → Billing, Pending Orders → Orders, Site Provisioning → Facilities). |
| T2 | frappe-ui `Tabs`: Overview · Orders · Quotes · Billing · Facilities · Deals, each label with its count. Empty tabs stay, with an empty state. |
| T3 | Overview = Customer, Partner Details, Needs attention (≤3 outstanding invoices, ≤3 open orders, each with "View all"). |
| T4 | Every list is paginated at 10 rows ("1–10 of 20", previous/next) and resets to page 1 when the data changes. |
| T5 | Nav page: `?tab=` in the URL. It is kept across the scope toggle, reload and back, and reset to Overview when a different customer or facility is picked. Changing tab does not re-fetch. |
| T6 | Deal › Customer 360 reuses the component with local tab state. |
| T7 | QA: Playwright covers a tab switch, counts, the KPI jump, pagination with more than 10 rows, tab kept across the scope toggle and reload, and tab-list fit at four viewports. |
