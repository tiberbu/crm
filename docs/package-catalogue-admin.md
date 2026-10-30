# Settings › Packages — guide for Sales Managers

Settings › **Packages** is where the Value Express catalogue is run: what facilities can buy
on the landing page and in self-onboarding. Sales Managers and System Managers see it; Sales
Users do not. Changes show on the next page load; there is no deploy.

## Plans

| Plan | What the facility buys | What you set |
|---|---|---|
| **Flex** | A prepaid token package | Tokens, price (excl. VAT), billing period, "Most popular", optional patient-journeys figure |
| **Fixed** | Platform access for a set fee, no tokens | Price per billing period (Monthly, Quarterly, Semi-annual or Annual) and the facility levels it applies to |
| **Custom** | Any amount from the price of 1,000 tokens, priced at the Flex rates | Only the wording; at most one, and it needs an active Flex package |

Prices are the Item Prices on the token selling Price List (set by an administrator in
Settings › Opt-In Process). A new package creates its own service item and price.

## Actions (the ⋯ menu on each card)

- **Edit**: wording, price, period, levels, Most popular. Orders already raised keep their price.
- **Duplicate**: a new package pre-filled from this one, with its own item.
- **Move earlier / later**: cards appear on the landing page and in onboarding in this order.
- **Disable / Enable**: hide a package for a while and bring it back.
- **Discontinue**: retire it for good. It stays for history and existing orders, cannot be
  switched back on, and is listed under the Discontinued filter. Duplicate it to sell it again.

## Rules the page enforces

- A package already on an order keeps its item, plan and tokens: changing the tokens would
  change what an unpaid order grants. Duplicate it to sell a different size.
- One active Fixed package per facility level, so onboarding knows which fee applies.
- Every active Flex and Fixed package needs a price; Flex needs at least one token.
- If someone else changed the catalogue while you had it open, your change is refused and the
  page reloads the latest version.

Every change is recorded as a comment on CRM Opt-In Settings.

## Layout

Card grids hold up to four cards a row and keep rows even (5 cards → 3 + 2, 7 → 4 + 3);
Fixed tiers hold up to two a row on the landing page and three in onboarding. Tablets show
two a row and phones one.
