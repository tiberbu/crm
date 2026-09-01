# Negotiated price lists

The Item Catalogue gives Sales Managers a CRM-level workflow for negotiated
pricing. It hides the ERPNext `Item` → `Item Price` → `Price List` relationship:

- **New Catalogue Item** creates a sellable, non-stock service item.
- **New Price List** creates an enabled KES selling list. Existing lists can be
  duplicated, including their current prices.
- **Quick price setup** configures several item prices for the selected list in
  one save. Prices are entered as monthly KES amounts exclusive of VAT.

The backend still uses native ERPNext records so quotations, network overrides,
and facility overrides resolve through the standard Item Price lookup. The API
accepts only enabled negotiated selling lists and requires Sales Manager,
System Manager, or Administrator access. The Item Catalogue route and sidebar
entry are also hidden from users without the manager role.

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

Facility contact edits intentionally do not expose or change a facility price-list
override. The contact form preserves an existing override when its payload omits
pricing. Sales Managers change the price list or negotiated rates from the Deal's
Quotation panel instead; the server allows that only while the facility has not
signed and records the quotation change in the Deal timeline. CSV/admin payloads
may still send an explicit `price_list_override` for controlled imports and
backward-compatible data maintenance.

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
