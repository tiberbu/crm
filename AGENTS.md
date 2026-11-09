# CRM — Project Context

## What this project is

Frappe CRM frontend. Vue 3 + frappe-ui. The backend is Frappe Python. Scripts in
`frontend/` only; Python in `crm/` (Frappe app). No build step for Form Scripts —
they run as evaluated strings in the browser.

---

## Where to read before working

| Task | Read first |
|---|---|
| What are we building next | [PLAN.md](./.pi/PLAN.md) |
| Stable API contracts (setFieldProperty, formDialog, helpers) | [SPEC.md](./.pi/SPEC.md) |
| Why code is the way it is (decisions, bugs fixed, history) | [ARCHIVE.md](./.pi/ARCHIVE.md) |
| Form scripting user guide | [feats/form-scripting/guide.md](./.pi/feats/form-scripting/guide.md) |
| formDialog() API reference | [feats/form-scripting/form-dialog.md](./.pi/feats/form-scripting/form-dialog.md) |

---

## Key files

### Scripting engine
| File | Role |
|---|---|
| `frontend/src/data/document.js` | `useDocument` — loads doc, wires script, patches `save.submit`, exposes triggers |
| `frontend/src/data/script.js` | `getScript` — fetches Form Script records, evaluates class via `new Function`, injects helpers, `setupHelperMethods` |
| `frontend/src/utils/scriptHelpers.js` | `createDocProxy`, `getClassNames` — extracted pure helpers |

### Field rendering
| File | Role |
|---|---|
| `frontend/src/components/FieldLayout/FieldLayout.vue` | Tab/section/column layout. Accepts `context` prop for standalone mode (no useDocument) |
| `frontend/src/components/FieldLayout/Field.vue` | Renders a single field. Calls `useDocument` unless `fieldLayoutContext` is injected |
| `frontend/src/components/FieldLayout/Section.vue` | Section with CollapsibleSection |
| `frontend/src/components/FieldLayout/Column.vue` | Column wrapper |

### Form dialog system
| File | Role |
|---|---|
| `frontend/src/components/Modals/FieldLayoutDialog.vue` | Dialog shell + standalone FieldLayout + local reactive doc |
| `frontend/src/components/Modals/FieldLayoutDialogContainer.vue` | Renders dialog entries from reactive array |
| `frontend/src/utils/renderFieldLayoutDialog.js` | `formDialog()` — pushes to array, returns Promise |
| `frontend/src/components/Modals/GlobalModals.vue` | Mounts FieldLayoutDialogContainer + other app-wide modals |

### Field transforms & validation
| File | Role |
|---|---|
| `frontend/src/utils/fieldTransforms.js` | `processField()`, `findMissingMandatory()`, `parseLinkFilters()` — pure, tested |
| `frontend/src/utils/expressions.js` | `evaluateDependsOnValue()`, `evaluateExpression()` |

### Meta & stores
| File | Role |
|---|---|
| `frontend/src/stores/meta.js` | `getMeta(doctype)` — fetches DocType meta, exposes `getFields()`, formatters |
| `frontend/src/stores/global.js` | `$dialog`, `$socket`, `makeCall` |

---

## Tests

```bash
cd frontend
yarn test:run      # single run
yarn test          # watch mode
```

- **118 tests · ~250ms** — all must pass before committing
- Location: `frontend/tests/unit/`
- Only pure utility functions are unit-tested (no Vue component tests yet)
- Add tests in `tests/unit/` when adding pure logic to `src/utils/`

### Python (Frappe) tests

Run with `scripts/run-crm-tests.sh`, which always passes `--app crm`:

```bash
scripts/run-crm-tests.sh <site> --module crm.tests.test_optin
```

> **Hard rule:** never run `bench run-tests` on a site without `--app crm`.
> Without it, Frappe's test runner runs **every** installed app's `before_tests`
> hook — and ERPNext's hook runs `delete from tabItem Price`, wiping all item
> prices on the site, and also resets Selling/Stock test defaults (this happened
> on 2026-11-05 and blanked the public facility-onboarding package catalogue).
> On the reference/dev site prefer not running the suite at all; the site's
> `allow_tests` config must stay `false` outside of an explicit, approved test run.

---

## Brand guide and UI/UX spec — strict adherence

The brand guide and the UI/UX specs are binding, not inspiration. No change may
introduce colours, fonts, font sizes or weights that they do not define.

**Sources of truth**

| Rule | Source |
|---|---|
| Brand red `#bc1823` (hover `#a3141d`), neutrals, status colours | `crm/public/css/tiberbu-brand.css`, `docs/tiberbu-crm-centralized-theme-spec.md` |
| Font: local InterVar only (no Google Fonts); weights 400–600, **nothing above 600**; frappe-ui type scale | `docs/tiberbu-crm-typography-perf-spec.md` |
| CX Portal tokens (`--cx-*`, `text-cx-*`): **CX Portal only** | `docs/cx-portal-ux-design-pattern.md` |
| Opt-in journey (invite email → `/opt-in` wizard → contract → checkout) | `docs/optin-executive-ux-prd.md` |

**Rules**

- One surface, one design language. Never borrow another surface's material
  (e.g. CX glass, gradients or `--cx-*` tokens on the opt-in wizard). This is how
  the 2026-10-20 opt-in colour regression happened.
- Every fallback brand colour (Vue, Python, email HTML) is `#bc1823`. Python
  uses `crm.api._email.DEFAULT_BRAND_COLOUR` / `valid_brand_colour`; do not add
  new hex literals for the brand.
- A partner `primary_colour` is used only if it is a strict `#rgb`/`#rrggbb`
  literal; anything else falls back to the brand red.
- Status colours (error/warning/success) are semantic only, never decorative.

**Post-implementation check (required before claiming any UI change is done)**

1. Run the Playwright UI suite. It must pass at all four viewports:
   `cd frontend && SCREENSHOT_DIR=<dir> npx playwright test -c playwright.portal-ui.config.ts`.
   `optin-brand.spec.ts` asserts the brand rules for every opt-in step.
2. Look at the screenshots of every changed screen and confirm the colours,
   font family, font sizes and weights match the sources above.
3. When you add or restyle a surface, extend a brand spec to cover it.
4. In the PR description, state that the brand check was done and give its result.

---

## Commit style

```
feat: short description
fix: short description
refactor: short description
test: short description
docs: short description
```

Multiple logical commits per PR — one commit per coherent change, not one giant commit.
Pre-commit hooks run prettier + eslint + oxlint automatically. If they modify a file,
`git add` the file again and re-commit.

---

## Pull requests

- Use the existing `feature_branch`; do not create another feature branch unless the
  maintainer explicitly asks.
- Open or update the pull request from `feature_branch` **against `develop`**. Do
  not push feature work directly to `develop`.
- When asked to commit or push, also update the pull request description. It must
  state the user-visible changes, API/data or migration impact, configuration
  requirements, and the verification commands/results.
- Keep the PR review-ready: summarize follow-up or deployment work explicitly
  rather than leaving reviewers to infer it from commits.

---

## Docs structure

```
PLAN.md          — future only (phases 3B, 4, 5, 6)
SPEC.md          — stable contracts
ARCHIVE.md       — completed phases + decision rationale
feats/           — user-facing feature docs
archives/        — old docs preserved verbatim
```

When a phase completes: move its spec from PLAN.md to ARCHIVE.md, update SPEC.md if
the API surface changed.

---

# CRM agent working notes

- Treat the user's request as the implementation scope and keep the change
  focused. Preserve unrelated worktree changes.
- Product and technical knowledge lives in `docs/`; retain existing planning
  artifacts when changing the development workflow.
- Use Context7 MCP for current framework or library documentation when relevant.
- Verify changes with the smallest useful build or command checks. Do not claim
  end-to-end behavior is verified without exercising the actual flow.
