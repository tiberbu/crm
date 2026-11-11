# Express onboarding: making the "on behalf of the owner" path prominent (P-136)

**Status:** built 2026-11-11 · **Input:** business review feedback, 2026-11-10
**Roundtable:** decisions D10–D12 in `_bmad-output/usage-report/implementation-artifacts/party-2026-11-11-usage-report-and-on-behalf.md` (added with the P-135 PR)

## Problem

Self-onboarding starts with the owner's ID. Facilities are linked to the ID of their registered owner, so administrators and staff who enter their own ID find nothing. The way forward, setting up on the owner's behalf, was offered in two weak ways:

- a text link under the ID form ("I'm not the registered owner — set up on behalf of a facility →"), and
- after the code was verified with no facilities found, one grey sentence ("We couldn't find eligible facilities…") with no on-behalf option at all, under a heading that still said "Select the facility you want to onboard".

## What changed

| Where | Before | After |
|---|---|---|
| ID step | Text link | **Option card**: icon, the heading "Not the registered owner?", one sentence on how the owner stays protected, and a "Set up on behalf of the owner →" button |
| Verified ID with no facilities | Grey note under a "Select the facility" heading; a disabled Continue button | The page heading becomes **"No facilities are registered to this ID"**. A **decision panel** explains why, shows the three steps of the on-behalf path, and offers a primary **"Set up on behalf of the owner →"** and a secondary **"Use a different ID"**. The disabled Continue button is hidden; onboarding assistance stays. |

Either button opens the existing administrator form, with a fresh session and the cursor in the facility reference field. The on-behalf flow itself is unchanged: find the facility by MFL or registration number, the registered contact receives the one-time code, then the corporate email, plan and payment.

## Design rules followed

- Value Express landing tokens and button classes only (`--red-wash`, `--red-line`, `--red-ink`, `.btn.primary` = brand `#bc1823`). No CX Portal tokens, no new colours.
- New text is at most weight 600. The headings are scoped under `.vx`, so the landing's own `h2` weight does not override them.
- Existing test ids are kept (`admin-path-toggle`, `admin-path-back`, `admin-reference-input`). New ids: `admin-path-card`, `no-facilities-panel`, `no-facilities-on-behalf`, `no-facilities-different-id`.

## Impact

Frontend only: `FacilityOnboardingLanding.vue` and `valueExpressOnboarding.css`. No API, data, migration or configuration changes.

## Verification

- `e2e/regression/onboarding-on-behalf.spec.ts` in the portal UI suite, at phone, tablet, laptop and desktop widths:
  - the ID-step card opens the administrator form with the reference field focused, and Back returns
  - a verified ID with no facilities shows the panel: heading, three steps, a brand-red primary button and no Continue button
  - the primary button opens the administrator form, and "Use a different ID" returns to the ID step
  - an owner with facilities sees no panel
  - layout audit and weights ≤ 600
