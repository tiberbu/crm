# Party record — Customer 360 facility scope (2026-11-09)

Room: 📊 Mary (analyst), 📋 John (PM), 🏗️ Winston (architect), 🎨 Sally (UX), 💻 Amelia (dev).
Mode: session, research. Research inputs: the current `Customer360.vue` / `crm/api/customer_360.py`,
the CX portal's facility attribution rule (`crm.utils.portal_commercial.attribute_facilities`,
SPEC 4.1), the facility-ID rule, and frappe-ui 1.0.0-beta.24 docs via Context7
(`TextInput` `#suffix` slot for a clear button; `TabButtons` `options` + `v-model` segmented control).

Maintainer's ask: the search box can't be cleared; the results pop-up can't be closed; picking a
facility opens the owner's whole 360 instead of that facility. Facility first, with a way to the
owner's full picture.

---

📊 **Mary:** Before anyone draws a toggle — what makes an invoice "this facility's"? Because if
we get that wrong the facility view lies, and the admin on the phone tells a clinic it owes nothing.

🏗️ **Winston:** We already answered that once. The CX portal attributes every order and invoice
with one rule: header facility stamp, then item-line facility codes, then the Opt-In Submission's
facility snapshot, then — only if the account has exactly one facility — that facility. Same rule
here, imported, not re-invented.

💻 **Amelia:** The portal helpers read child rows with `ignore_permissions`. This module's contract
is no `ignore_permissions`. I'll read item codes through `frappe.get_list` on the parent with child
fields, and only import the pure `attribute_facilities` function.

📊 **Mary:** And the records nobody can attribute? Two facilities, one account-level invoice. If the
facility view just drops it silently, someone files a "missing invoice" bug by lunch.

🎨 **Sally:** Then say it. One quiet line under the scope bar: "2 records aren't tied to one
facility" with a link that switches to the whole organisation. No warning colour — it's not an error.

📋 **John:** Fine, but the default is the facility. That's the whole request. If I chose a facility,
I don't want the org's noise first.

🎨 **Sally:** Toggle shape. Tabs say "different content"; this is the same page with a filter. A
segmented control — frappe-ui `TabButtons` — "This facility" | "All facilities". It sits in a scope
bar with the facility's name, Facility ID and MFL, so you always know which lens you're in.

🏗️ **Winston:** Client-side filter or server-side? I want the server to scope. The summary tiles —
paid, pending, outstanding — have to be computed on the scoped rows, and that math is tested in
Python today.

💻 **Amelia:** Server-side costs a round-trip per toggle.

🏗️ **Winston:** One request, a few hundred ms, and the URL carries `scope`, so back/refresh keep the
lens. I'll take correct over instant.

📋 **John:** URL — yes. Make `?facility=…&scope=organization` shareable.

📊 **Mary:** In the *organisation* view, I still can't tell which facility an invoice belongs to.

🎨 **Sally:** Add a Facility column there — name, from the same attribution. Hidden in facility
scope, where it's redundant.

📋 **John:** The ask lists quotes too. We don't show quotes at all.

🏗️ **Winston:** Add a Quotes section — by deal and by billing customer. And orders by billing
customer: Value Express draft orders are raised against the customer, not an OIS or quote, so today
they never appear. That's a gap in the "all" view as much as the facility one.

📋 **John:** That widens the org view. Is that a regression?

📊 **Mary:** It's the org view finally being "all". The facility view must be a subset of it, or
nobody trusts either.

💻 **Amelia:** Search fixes are mechanical: a clear button in the `#suffix` slot, Esc closes, click
outside closes, a close button in the panel. And a real bug — `showResults` is `!selected`, so after
your first pick, new searches never show results.

🎨 **Sally:** Clear empties the box and closes results. It does **not** unload the 360 you're
looking at — you cleared the search, not the customer.

📋 **John:** I'd have reset everything.

🎨 **Sally:** And lost the screen you were on mid-call. No.

📋 **John:** …Fine. Clear = text only.

📊 **Mary:** Facility ID. Results show only the MFL today. House rule: Facility ID everywhere, MFL
beside it, "Not linked yet" when missing. Search should match the FID too.

🏗️ **Winston:** And a facility with no owner organisation still opens in facility scope; the
toggle just isn't offered. No more bouncing to the facilities list.

---

## Outcome — decisions (recorded in `planning-artifacts/customer-360-facility-scope-spec.md`)

D1 clear button · D2 closable results dropdown (button, Esc, outside click; reopen on focus) ·
D3 facility pick → facility scope, URL-backed · D4 scope bar + `TabButtons` toggle · D5 server-side
scoping with the shared attribution rule · D6 unattributed-records note · D7 payments follow their
invoices · D8 facility deals/onboarding/partners · D9 Quotes section · D10 orders by billing customer ·
D11 Facility ID in search, scope bar and facility list · D12 Deal tab unchanged.

Open disagreement kept on record: Amelia preferred an instant client-side toggle; Winston's
server-side scope won on summary correctness.
