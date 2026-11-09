# Opt-In pricing controls

## Price-list templates

Item Catalogue lists enabled selling price lists for Opt-In. `Standard Selling`
is intentionally excluded because it is ERPNext's generic default; all other
selling lists can be named naturally for the network, facility, or commercial
arrangement they represent. Select a list and use **Duplicate list** to copy
every selling Item Price into a new list. The source list is never changed.
Empty lists can still be created with **New Price List**.

## Network and facility pricing

The network **Price List Override** remains the default for its facilities. A
facility can opt out of that default by setting **Facility price list** on its
membership. This override is scoped to the facility/network membership, so the
same facility can use different negotiated prices in different networks.

Leaving the facility field blank falls back to the network override, then the
global Opt-In default. CSV imports accept an optional `price_list_override`
column using the same fallback behavior.

The public Opt-In pricing endpoint resolves the effective list server-side and
stores it with each accepted pricing row. For a submission containing several
lists, the quotation keeps one header list (the network/default list) while the
accepted per-facility line rates remain authoritative.
