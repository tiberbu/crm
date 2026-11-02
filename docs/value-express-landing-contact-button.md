# Value Express landing — quick access to the contact details

Status: implemented · Reviewed in BMAD Party Mode (2026-11-02, room: John, Mary, Winston,
Amelia, Sally)

## Problem

The contact details — two phone numbers, office hours, email — live in section 08
("Talk to the Value Express team"), the bottom of an eight-section landing page.
Facility owners on phones want the numbers mid-funnel (pricing, calculator), but
reaching them means scrolling the whole page or using the "Support" nav link, which
on mobile is the last item in a scrollable nav strip and only anchors to the top of
section 08.

## Options considered

### Option A — button to the right of the hero eyebrow (declined)

A "Talk to us" button beside the `01` eyebrow ("Tiberbu CareverseHIMS Value Express").

Declined:

- The eyebrow is a section marker (small-caps label + `secno` chip), not an action row;
  a CTA beside it reads as a stray pill.
- The hero already carries the conversion pair (Get started primary + See how it works
  ghost); a third contact CTA competes for the first click on a sales page.
- It is invisible the moment the visitor scrolls past the hero — exactly when the
  numbers matter.

### Option B — floating button (chosen)

A floating "Talk to us" button, bottom-right, that expands in place into a compact
contact card.

### Header upgrade (declined — out of scope)

The sticky header already has a persistent "Support" link to `#contact`. Redesigning
the header was not requested and would add a third door for a job one door does.

## Design (Option B)

- **Placement** — fixed, bottom-right: `right: 20px`, `bottom: 20px +
  safe-area-inset-bottom`, `z-index: 40` (header is 20, the safe-area strip 30).
- **Visibility** — appears only after the hero has scrolled out of view; hides while
  the `#contact` section is in view (redundant there). Two `IntersectionObserver`s,
  no scroll handlers. Silently does nothing where `IntersectionObserver` is missing.
- **Interaction** — tap expands the card in place (no navigation). Closes via the ×
  button, Escape, or tapping outside.
- **Card content** — the same settings data section 08 renders: both `tel:` links,
  office hours, email, plus a "Send a message →" link that jumps to `#contact`.
- **Styling** — tokens only, so dark mode, the global `prefers-reduced-motion` rule,
  and the `.vx :focus-visible` outline apply unchanged. FAB is the brand red
  (`--btn`) with white text (6.4:1). Card is `min(300px, 100vw − 40px)` so nothing
  overflows or causes horizontal scroll.

## Implementation

| File | Change |
|---|---|
| `crm/www/index.html` | `.talkwrap` markup after `</main>` (FAB + card reusing `landing.phones` / `landing.hours` / `landing.email`); ~30 lines of vanilla JS in the existing IIFE (open/close, observers) |
| `crm/public/css/value-express-landing.css` | `.talkwrap` / `.talk-fab` / `.talk-card` styles, token-based |
| `e2e/value-express/landing.spec.ts` | New test: hidden at top, visible past the hero, card opens with `tel:` links and the form jump, × closes it (runs in desktop + mobile projects) |

Constraints honored by the existing suite:

- The FAB is a `<button>`, and the card's "Send a message" is a plain link — not an
  `a.btn.primary`, so the invariant "every primary button reads Get started and opens
  onboarding" holds.
- No `.secno` chips are added, so the "sections 01–08 in page order" test holds.
- `data-testid`: `talk-us-fab`, `talk-us-card`, `talk-us-close`.

## Verification

- `npx playwright test --config e2e/value-express/playwright.config.ts landing.spec.ts`
  against the dev site (`BASE_URL` set to the site) — desktop and mobile projects.

## No other impact

No API, data, migration or configuration changes — the card reuses the existing
landing settings. No new dependencies, no build step (the page is server-rendered
Jinja + inline vanilla JS).
