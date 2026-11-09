# Opt-in mobile and signatory reliability

## Scope

This change is limited to the mobile CRM shell and the contract co-signatory
editing path. Desktop routes and desktop-specific layout classes are unchanged.

## Mobile behavior

- Deal Quote is promoted next to Details and is also available as a persistent
  Quote action in the mobile deal toolbar.
- Mobile tab rails scroll horizontally without exposing a clipped Apply/active
  state, while the selected panel owns vertical scrolling for touch navigation.
- The mobile shell uses the dynamic viewport height and prevents nested page
  scrolling, which avoids address-bar jumps and clipped content on phones.
- The same tab rail treatment is applied to mobile Lead, Contact, and
  Organization pages.

## Signatory behavior

- Contract child row names are used as UI keys and API targets, so repeated
  role/email rows can be removed one at a time.
- Removing an unsigned co-signatory records a per-contract exclusion. Source
  network/Tiberbu settings remain intact for future contracts, but sync cannot
  re-add the removed identity to the current contract.
- Explicitly adding that identity again clears the exclusion. Signed rows remain
  immutable.

## Verification

- `yarn test:run`: 135 frontend tests passed.
- `bench --site crm.io run-tests --app crm --module crm.tests.test_optin`: 47
  opt-in backend tests passed.
- `yarn build`: production build passed. Existing non-blocking Vite/PWA warnings
  remain unrelated to this change.
