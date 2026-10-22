# CX Portal — Professional Admin UI: Audit & Phased Plan

- Date: 2026-10-20
- Branch: `feat/professional-admin-ui` (from `develop` @ `v1.0.109` / `f7cec4e`)
- Current scope (expanded by user 2026-10-20): **the complete customer-facing CX surface** — signed-in facility portal, facility identity onboarding, network opt-in enrollment, and owner-visible opt-in requests. Internal CRM sales/admin dashboards remain outside this customer-facing scope.
- Baseline: includes the P0–P3 UX rebuild (`3845695`), the typography normalization pass, and the InterVar/`.cx-portal` font pin in `frontend/src/index.css`.

## 1. Audit findings

Severity: **H** = perceived professional-grade blocker, **M** = consistency/quality, **L** = polish.

### F1 — Design tokens (the accent is a three-way patchwork)

| # | Sev | Finding |
|---|-----|---------|
| 1.1 | H | **Three mechanisms produce the brand red.** (a) Tailwind `blue-*` classes remapped to red via `--blue-*` overrides in `index.css` (dominant: sidebar active, primary CTAs, focus rings, checkboxes); (b) arbitrary inline hex `#bc1823` / `#a3141d` in 8+ spots (brand mark, dashboard Top Up button + link, KPI hero number, token counts in table & cards, pricing token pill, Top-Up modal confirm, support email); (c) raw Tailwind `red-50/red-200` (pricing token pill). No single source of truth; (b) bypasses theme entirely. |
| 1.2 | H | **Off-brand indigo** in 3 places: group-by-network toggle (`bg-indigo-50 border-indigo-300 text-indigo-700`), group header chip (`bg-indigo-100 text-indigo-700`), dashboard network pill (`border-indigo-200 bg-indigo-50 text-indigo-700`). |
| 1.3 | M | **Neutral ramp = raw `slate-*`** throughout, plus root `bg-[#f8fafc]` (an arbitrary hex that equals slate-50) and hard-coded `bg-white` on sidebar/header/drawer — outside the app's token system and not dark-theme capable. |
| 1.4 | M | **Radius drift**: `rounded` / `-md` / `-lg` / `-xl` / `-2xl` all in use for similar elements (checkbox, icon buttons, primary buttons, cards). |
| 1.5 | M | **Shadow drift**: `shadow-2xs` / `-xs` / `-sm` / `-xl` / `-2xl` in use. |

### F2 — Icon language (biggest "unprofessional" signal)

| # | Sev | Finding |
|---|-----|---------|
| 2.1 | H | **Emoji used as UI icons in 30+ places**: all 8 sidebar items, header, table action cells, badges, drawer, modals, empty states, toast. Emoji rendering differs per OS (Android/iOS/Windows) so the same screen looks different per device. A few inline SVGs already exist (search, close, chevrons, sign-out, table/card toggles) → two icon languages coexist. |

### F3 — Missing component system

| # | Sev | Finding |
|---|-----|---------|
| 3.1 | H | **No button primitive.** 5+ hand-rolled variants with inconsistent radius/padding: `rounded-lg px-2.5 py-1`, `rounded-xl px-3 py-1.5`, `px-3.5 py-2`, `px-4 py-2`, `px-5 py-2.5`; fills `bg-blue-600` / `bg-slate-900` / `bg-[#bc1823]` / outline / link. |
| 3.2 | M | **No badge primitive.** 6+ hand-rolled pill variants (Live/Verifying, KEPH level, network, counts, contract, status). |
| 3.3 | M | **Duplicated table markup**: the grouped and flat facility tables are two complete `<table>` blocks with identical cell markup; same duplication for grouped vs flat card views. Already drifting (grouped view lacks the "Showing X of Y" footer). |
| 3.4 | M | **FacilityDrawer is a hand-rolled fixed overlay**: no ESC-to-close, no focus trap, hard-coded white surfaces, `z-40`. Not frappe-ui's Drawer. |
| 3.5 | M | **Toast is a sticky full-width bar** (emoji + underlined "Dismiss") that pushes page layout down instead of floating. |
| 3.6 | M | **Dead affordances**: header select-all checkbox (no `v-model`) and row checkboxes (no bulk action) render but do nothing; `aria-expanded="isUserMenuOpen"` is a literal string (missing `:` binding) on the user menu button. |

### F4 — View-specific

| # | Sev | Finding |
|---|-----|---------|
| 4.1 | M | **Facilities**: no zero-results state when filters match nothing (only the empty-portfolio state exists); grouped table has no result-count footer. |
| 4.2 | M | **Pricing**: the comparison table hard-codes 4 columns with literal tier names ("Free Trial / Starter / Growth / Scale") and hard-coded 4-tuples in `featureComparisonCategories` — decoupled from the real `context.token_packages`; misleading if packages or tier names change. CTA hierarchy: every tier card carries a solid dark button; only Growth is highlighted. |
| 4.3 | L | **Billing**: the M-Pesa "How to pay" steps are hard-coded with `<br/>` in markup. |
| 4.4 | L | **Dashboard**: attention-band uses emoji icons; drill-in links use three different colors (`text-blue-600`, `text-[#bc1823]`, `text-slate-800`). |
| 4.5 | L | **Support**: placeholder phone `+254 700 000 000` shown as if real. |
| 4.6 | H | **Mobile**: the sidebar has no responsive behaviour — always `w-64`, collapse toggle is `hidden sm:inline-block`; tables do not switch to the card view on small screens. The portal is cramped on phones (to be verified in a real viewport). |

### F5 — Structure

| # | Sev | Finding |
|---|-----|---------|
| 5.1 | M | 3,467-line `FacilityPortal.vue` (7 views + 5 modals + drawer orchestration). The P3 extraction was deliberately deferred pending visual QA — a design pass is exactly what justifies it. |
| 5.2 | L | i18n: `__()` used only for the 5 Dialog titles; all other copy is hard-coded English. |
| 5.3 | L | `TokenCalculator.vue` (746 lines, shared with onboarding) renders inside the calculator modal — it must be aligned to the portal language without breaking its other `context` values. |

## 2. Design decisions (confirmed 2026-10-20)

0. **Scope changes from user decisions**: (a) full emoji→SVG replacement; (b) mobile shell included in P2; (c) **dark theme is in scope** — the portal must track frappe-ui's `[data-theme='dark']`, so every token below is defined for light **and** dark, and every hard-coded `bg-white`/`slate-*` surface becomes token-driven. This is the single largest driver of P0 size.
1. **One brand mechanism.** Scoped `.cx-portal` tokens: `--cx-brand-50/100/200/500/600/700` (light 500 = `#bc1823`; dark 500 brightened to `#d23a41` to read on near-black), used via a small set of utility classes; retire arbitrary hex and raw `red-*`. Keep the existing `--blue-*` remap in `index.css` untouched (other surfaces depend on it) but stop using `blue-*` in portal code.
2. **Neutrals / surfaces / borders**: token-driven, both themes. Map the current `slate-*` usages onto a defined set with explicit light + dark values (see token table below); root background via token; no hard-coded `bg-white` in portal templates after P0.
3. **Radii**: 2 tiers — controls 8px (`--cx-r-sm`), cards 16px (`--cx-r-lg`); pills 999px.
4. **Shadows**: 2 tiers — `subtle` (cards) and `raised` (overlays/menus); stronger black shadow in dark.
5. **Icons**: single stroke-based inline-SVG icon set (1.5px stroke, `currentColor`, 16/20px) in a local `cxIcons` module. **No emoji as UI icons** (confirmed).
6. **Buttons**: one `CxCta` primitive, variants `brand` / `dark` / `outline` / `link` / `ghost-icon`, sizes sm/md. `dark` variant uses the theme surface-10 ink so it inverts correctly.
7. **Badges**: one `CxBadge` primitive, tones neutral / brand / success / warning / danger, optional status dot; all tones defined for both themes.
8. **Drawer**: keep the side-drawer pattern; add ESC-to-close, focus trap, and token-based surfaces (or migrate to frappe-ui `Drawer`).
9. **Toast**: floating, auto-dismissing notification (no layout shift); keep server-owned message text; themed.
10. **Copy**: no dead controls — remove the non-functional checkbox column unless a bulk action is added (remove for this pass).
11. **Support phone**: do not show a hotline until the real number is confirmed; never show a placeholder as a contact channel.

### Token table (P0 foundation, light + dark)

| Token | Light | Dark | Replaces today |
|---|---|---|---|
| `--cx-bg` | `#f8fafc` | `#0f1115` (near slate-950) | root `bg-[#f8fafc]` |
| `--cx-surface` | `#ffffff` | `#16181d` | `bg-white` (sidebar/header/cards/drawer) |
| `--cx-surface-2` | `#f1f5f9` (slate-100) | `#1e2126` | inset wells, `bg-slate-50/100` |
| `--cx-border` | `#e2e8f0` (slate-200) | `#2a2e35` | `border-slate-200` |
| `--cx-border-soft` | `#eef2f6` (slate-100) | `#23262b` | `border-slate-100` |
| `--cx-ink` | `#0f172a` (slate-900) | `#f1f5f9` | `text-slate-900` |
| `--cx-ink-2` | `#334155` (slate-700) | `#cbd5e1` | `text-slate-700/800` |
| `--cx-ink-3` | `#64748b` (slate-500) | `#94a3b8` | `text-slate-500/600` |
| `--cx-ink-4` | `#94a3b8` (slate-400) | `#64748b` | `text-slate-400` |
| `--cx-brand` | `#bc1823` | `#d23a41` | all `#bc1823`, `blue-600` accent |
| `--cx-brand-strong` | `#a3141d` | `#e0545a` | hover `#a3141d` |
| `--cx-brand-soft-bg` | `#fdf2f3` | `#2a0d10` | `bg-blue-50`/`bg-red-50` accent tints |
| `--cx-brand-soft-ink` | `#8f111b` | `#ff8f93` | `text-blue-700/800` accent text |
| `--cx-r-sm` / `--cx-r-lg` | `8px` / `16px` | same | radius drift |
| `--cx-shadow-subtle` / `-raised` | light values | darker black values | shadow drift |

Status tokens (success/warning/danger) reuse frappe-ui's existing semantic ramps (emerald/amber/rose) which already invert — the portal will reference them, not re-declare.

## 3. Phased plan

### P0 — Token foundation + primitives (foundation, zero behaviour change)

- Add the `.cx-portal` token block to `frontend/src/index.css` (brand ramp, neutral set, 2 radius tiers, 2 shadow tiers).
- Replace all `#bc1823` / `#a3141d` / `#f8fafc` arbitrary hex and the 3 indigo / raw-red sites with tokens.
- Extract primitives in `frontend/src/pages/FacilityPortal/components/`: `CxCta.vue`, `CxBadge.vue`, `CXEmpty.vue`, `CXCopiedButton.vue`, `CXSectionHeading.vue`; convert all portal buttons/badges/empty states to use them.

**Acceptance**: zero `#[0-9a-f]{6}`, zero `indigo`/raw `red-` classes in portal files; `yarn test:run` green; side-by-side screenshot shows no unintended visual shift.

### P1 — Icon system + shell (biggest perceived uplift)

- Add `cxIcons` (stroke SVG set); replace all 30+ emoji usages across sidebar, header, tables, cards, drawer, modals, empty states, toast.
- Fix `aria-expanded` binding on the user menu.
- Drawer: ESC-to-close + focus trap (or frappe-ui Drawer).
- Toast → floating transient notification.

**Acceptance**: no emoji in any portal template; drawer closes on ESC and traps focus; visual QA on all 7 views (desktop).

### P2 — View refinement + mobile shell

- **Facilities**: single table template for flat + grouped (group header conditional); remove dead checkbox column (per decision 10) or wire it to a real bulk action if requested; add zero-results state; result-count footer in both modes.
- **Pricing**: make the comparison table data-driven from `token_packages` (columns + names from data, drop the hard-coded literals); CTA hierarchy — Growth = brand primary, other tiers outline.
- **Billing**: `<ol>` for the paybill steps; align the three paybill info cards.
- **Dashboard / Opt-In / Profile / Support / HFR Sync**: apply primitives; unify drill-in link colour to brand; replace the placeholder support phone (needs real value — open question).
- **Mobile shell**: sidebar → bottom tab bar (or overlay drawer) below `md`; default facility list to card view below `sm`; verify at 390px and 1280px.
- **TokenCalculator**: align palette/icons inside the portal via its existing `context` prop without changing onboarding behaviour.

**Acceptance**: visual QA all views at 390px / 768px / 1280px; loading, empty, no-results, error, and permission states checked per the frontend skill's verification list; `yarn test:run` green.

### P3 — Structural extraction (after visual QA, may be a follow-up branch)

- Extract the 7 views + 5 modals into `FacilityPortal/views/*.vue` and `FacilityPortal/modals/*.vue`; `FacilityPortal.vue` keeps state/orchestration only.
- i18n pass: wrap user-facing strings in `__()`.
- Full a11y/contrast sweep (focus order, tab order, contrast tokens).

## 4. Decisions (user-confirmed 2026-10-20)

1. **Emoji → icons**: full replacement. Every emoji used as a UI icon becomes the 1.5px-stroke inline-SVG set (`currentColor`), platform-consistent rendering. No emoji in UI.
2. **Mobile**: included in this branch, in P2 (bottom tab bar / overlay below `md`; card-first facility list below `sm`; verified at 390px and 1280px).
3. **Dark theme**: the portal **must track frappe-ui's dark theme**. Consequence for P0: every new `.cx-portal` token is defined for **both** `:root` (light) and `[data-theme='dark']`, and the hard-coded `bg-white` / `slate-*` surfaces are replaced by token-driven classes so the whole portal inverts. This makes P0 larger than the light-only recommendation; it is now the foundation for all later phases.
4. **Support phone**: keep unconfirmed channels out of the customer UI. Add a hotline only after the real number is confirmed.

Note for P0: because dark parity is in scope, the neutral ramp, surfaces, borders, and shadows all need dark variants, and `index.css` dark-block parity must be checked for every token added.

## 5. Scope boundary

- Customer-facing identity, public Self-Onboarding, invitation-only Network Opt-In, signed-in portal, and owner-visible request status are in scope. Self-Onboarding ends at Terms acceptance and request submission; it has no signature step. Network Opt-In remains a separate invited quotation/agreement/signature route.
- Internal CRM sales/admin screens (Leads, Deals, FinanceCockpit, Opt-In dashboard/submissions) are not part of the customer portal surface.
- Shared components such as TokenCalculator must preserve their existing onboarding behavior when styled for portal contexts.


Future portal work should follow [CX Portal UX Design Pattern](cx-portal-ux-design-pattern.md).


## 6. Expanded-scope review and implementation (2026-10-20)

The scope now covers the full customer journey, not only the signed-in facilities screen.

- **Signed-in facility portal:** removed workflow actions from the global header and duplicate navigation from the avatar menu; made registry discovery route to the actual discovery view; corrected search scope; removed inactive bulk selection and row-level calculator controls; removed fabricated encounter estimates and fixed package popularity/comparison claims; added persistent registry empty/error results; distinguished “On file” from authoritative “Verified”; removed the placeholder WhatsApp number; added keyboard/focus handling to the facility drawer.
- **Owner identity and registry lookup:** corrected Salim’s development profile from the supplied ID; stopped inferring a National ID from an arbitrary deal; do not log the full ID on HFR errors. The ID already stored on Salim’s User profile was the value the portal returned. Registry lookup with the corrected profile returned four facilities, three already linked.
- **Network Opt-In enrollment:** retained partner-specific branding, added restrained glass surfaces to the wizard shell, and replaced mouse-only facility card selection with native checkboxes. This is the invitation-only route and remains distinct from Self-Onboarding.
- **Facility onboarding:** reviewed the public identity/onboarding journey; its progress, retry, verification, eligibility, and mobile states already follow the revised interaction pattern.
- **Future guidance:** see [CX Portal UX Design Pattern](cx-portal-ux-design-pattern.md). Real National IDs are excluded from examples.

The table consolidation, full localization pass, and view extraction listed in P2/P3 remain structural follow-up work; they were not prerequisites to fixing the reviewed broken and misleading interactions.
