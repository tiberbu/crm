# Opt-In price lists

The Item Catalogue gives Sales Managers a CRM-level workflow for negotiated
pricing. It hides the ERPNext `Item` → `Item Price` → `Price List` relationship:

- **New Catalogue Item** creates a sellable, non-stock service item.
- **New Price List** creates an enabled KES selling list. Existing lists can be
  duplicated, including their current prices. Names do not need a `Negotiated`
  prefix; the generic ERPNext `Standard Selling` list is excluded.
- **Add missing item prices** is a secondary, collapsed setup tool for adding
  several item prices to the selected list in one save. It shows only sellable
  items that do not already have a price in that list. The configured Item
  Prices for the selected list remain the primary view. Prices are entered as
  monthly KES amounts exclusive of VAT.

The catalogue selector includes every selling Price List, including
`Standard Selling` and disabled historical lists, so managers can inspect the
actual ERPNext Item Prices without mixing records from another list. Those
lists are explicitly read-only in the catalogue. Changes can be written only to
an enabled, non-`Standard Selling` list, and the API still requires Sales
Manager, System Manager, or Administrator access. The Item Catalogue route and
sidebar entry are also hidden from users without the manager role.

## Catalogue context and quote previews

Selecting a price list shows its creation and last-edit timestamps, the users who
created and last changed it, and counts of the facilities and networks using its
effective configuration (facility override, network override, or Opt-In default).
The attached-facility list is selectable and opens a non-persisted sample quote;
the same preview is available from each facility row on a network's Contacts tab.
Both previews use the selected/effective price list, the facility's KEPH item,
and the configured VAT calculation, so they cannot change a quotation or create
an ERPNext document.

The attached-facilities section is collapsed by default and loads only when
expanded. Facilities are fetched in pages of 50 with a **Load more** action, so a
price list linked to 1,000 facilities does not mount or transfer all rows during
the initial catalogue load.

## Moving and removing item prices

Each configured item price has a **Destination** control. Keep it in the current
list, move it to another enabled negotiated list, or choose **Remove from this
list**. Saving a move updates the existing ERPNext `Item Price` record; removing
it deletes only that record, so the catalogue no longer offers that rate to new
quotes (already-created quotes are unchanged). The server verifies that the
record belongs to the selected list, prevents duplicate item/list combinations,
and requires a manager or Administrator.

Every move writes an audit Comment to both the source and destination Price List.
Every removal writes a Comment to the source Price List. The change and its audit
entry are committed together, so a failed audit cannot leave an unlogged price
change.

The facility contact form exposes a facility-specific override for new and
pre-Opt-In contacts, including an option to use the network price list. When a
network has yearly price lists configured, the form exposes one override per
configured year (including Year 1); each row can fall back to that year's
network list. Once a facility opts in, all yearly selectors are visibly locked
and their values are preserved when the contact is edited. The server also
rejects direct/API attempts to change an Opted-In override map. Sales Managers
change the price list or negotiated rates from the Deal's Quotation panel
instead; the server allows that only while the facility has not signed and
records the quotation change in the Deal timeline.
CSV/admin payloads may still send an explicit `price_list_override` for
controlled imports and backward-compatible data maintenance, subject to the
same Opt-In lock.

## Quote price-list changes

A Sales Manager may change a draft or sent quotation's price list after an
Opt-In summary is submitted, provided the facility signatory has not signed the
linked contract. The change re-baselines line rates, recalculates VAT/totals,
and records a Deal timeline comment identifying the quotation and both lists.
After a facility signature (including legacy contracts where signature data is
present but the status label is stale), the server rejects the change. This
guard is server-side and is independent of the UI control state. If the
signature state cannot be read, the server also refuses the change until it can
verify the state, rather than risking a post-signature edit.

## Price-list provenance on quotes and contracts

Each quotation now keeps two read-only fields: **Initial Price List** (the list
selected when the quote was first created) and **Price List History** (an
append-only JSON audit of the initial selection and every pre-signature switch,
including the timestamp and actor). The current quotation list is the
**Negotiated Price List**. This preserves the commercial story even when a quote
is later re-priced.

When a contract is generated, the initial list, negotiated list, and history are
copied to the contract. Sales users see the summary prominently in the CRM Quote
and Contracting panels. Every authenticated contract signer sees the same
read-only summary before the signature pad, and the PDF includes it near the
agreement header. It is informational only; the
existing server-side rule still prevents price-list changes after the facility
signs.

The migration backfills legacy quotations from their current selling price list
as a single truthful **Initial price list** event and copies that snapshot to
linked contracts where possible. It never invents prior changes or overwrites
existing history, and it is safe to run more than once.

## Level 6 migration

`crm.patches.v1_0.seed_level_6_prices` adds `CV-HIMS-KEPH-6` and the five
negotiated-year prices from the approved rate card. It is idempotent and
create-only: existing items, price lists, and Item Prices are never overwritten.
The patch safely exits on CRM-only sites without ERPNext or without an Item
Group available for the new service item.

## Duplicate compatibility

Duplicating a negotiated list reads the installed `Item Price` metadata through
the cross-version `Meta.fields` surface. This works on Frappe v15 and v16; it does
not depend on the removed `Meta.get_fieldnames()` method. Optional Item Price
columns are copied only when present on the target site's schema.
