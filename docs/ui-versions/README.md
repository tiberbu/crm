# UI versions: public landing page and facility onboarding

Major redesigns of the guest-facing pages are versioned with annotated git tags, so
an older UI can be inspected or brought back without digging through history.

| Version | Tag | Commit | Status | Summary |
|---|---|---|---|---|
| v1 | `ui/value-express/v1-legacy` | `0e5901b7` | Superseded by v2 | "Tiberbu Express" landing page and the original token-package onboarding wizard |
| v2 | (this branch, tagged on release) | — | In review | CareverseHIMS Value Express redesign: Flex, Fixed and Custom plans |

## v1: what the tag covers

The tag points at `develop` immediately before the Value Express redesign. The UI of
that version lives in these files:

| Surface | Route | Files |
|---|---|---|
| Public landing page | `/` | `crm/www/index.html`, `crm/www/index.py`, `crm/api/landing.py` |
| Facility onboarding | `/facility-onboarding` | `crm/www/facility-onboarding.html`, `frontend/src/pages/FacilityOnboarding/FacilityOnboardingLanding.vue` |
| Token calculator | onboarding, package step | `frontend/src/components/TokenCalculator.vue` |
| Onboarding API | — | `crm/api/facility_onboarding.py` |
| Brand assets | — | `crm/public/images/tiberbu-wordmark.png`, `crm/public/images/tiberbu-mark.svg` |

v1 behaviour worth knowing before restoring it:

- Landing: hero with "Start onboarding", a three-step strip, token package cards read
  from CRM Opt-In Settings, a contact form that creates a CRM Lead, and contact details
  from the Landing Page section of CRM Opt-In Settings.
- Onboarding: ID + OTP verification, facility selection, one token package per
  facility (Starter, Growth, Scale), terms, then a draft token order per facility.
- There is no Fixed (monthly) plan and no Custom amount in v1.

## Looking at an old version

```bash
git show ui/value-express/v1-legacy:crm/www/index.html | less
git diff ui/value-express/v1-legacy -- crm/www/index.html
```

To see it running, check the tag out in a separate worktree and build the frontend
there (`cd frontend && yarn install && yarn build`), or restore it on a branch as below.

## Restoring an old version

Restore on a branch and open a pull request against `develop`; never push a restore
straight to `develop`.

```bash
git checkout -b revert/ui-v1 upstream/develop
git checkout ui/value-express/v1-legacy -- \
  crm/www/index.html crm/www/index.py crm/api/landing.py \
  crm/www/facility-onboarding.html \
  frontend/src/pages/FacilityOnboarding/FacilityOnboardingLanding.vue \
  frontend/src/components/TokenCalculator.vue
```

Then check what later versions changed in the API and schema before building:

- v2 adds `plan` and `facility_levels` to CRM Token Package and a Custom token item to
  CRM Opt-In Settings. These fields are additive, so the v1 UI keeps working with
  them; it simply ignores Fixed and Custom.
- v2 accepts a Custom amount or a Fixed package in `submit_onboarding`. The v1 UI only
  sends token package item codes, which v2 still accepts.

Run `cd frontend && yarn test:run`, the Python onboarding tests and the landing and
onboarding Playwright suites before merging a restore.

## Adding a version

1. Before merging a redesign, tag the last commit of the old UI:
   `git tag -a ui/<area>/v<N>-<name> <commit> -m "<summary>"` and push the tag.
2. Add a row to the table above and a short "what the tag covers" section.
3. Note any schema or API change that a restore would have to account for.
