# Finance Cockpit roles patch — deploy failure fix

**Date:** 2026-10-31 · **Branch:** `fix/finance-cockpit-patch-hardening` → `develop`
**Primary file:** `crm/patches/v1_0/restrict_finance_cockpit_to_accounts.py`

## What DevOps saw

During `bench migrate`, `crm.patches.v1_0.restrict_finance_cockpit_to_accounts` crashed at
`page.save()` with `AttributeError: 'dict' object has no attribute 'is_new'`. The site never
received the later code, which is why the OpenMeter changes did not show up.

## Root cause

| Ref | Patch body | Result |
|---|---|---|
| `0f2dd7f2` (tags `v1.0.90`–`v1.0.103`) | `page.roles = [{"role": r} ...]`: raw dicts | `Document.save()` calls `row.is_new()` on each child row, so it crashes |
| `7a0f9cb4` (PR #104, first tag `v1.0.104`) | `page.set("roles", [])` + `page.append(...)` | Rows are `HasRole` documents, so the save works |
| `develop` / `v1.0.159` (includes the metering merge `c6fe5599`) | same as above | Works |

The deployment ran a ref from **before `v1.0.104`** (or a stale image). Current `develop` already
has the line DevOps suggested. We reproduced the exact error by running the `0f2dd7f2` patch body on
the test site.

## Party-mode review (Winston, Amelia, Murat, John)

- **Winston:** this is a provenance problem first. The deploy note matters as much as the diff.
  `do_not_update_json` also skips role creation, so the patch must create any missing roles itself.
- **Amelia:** in developer mode, `page.save()` → `Page.on_update` → `export_module_json` rewrites
  `finance_cockpit.json` and creates `crm/fcrm/page/__init__.py` in the app source (observed).
  Skip the save when the roles already match; suppress the export otherwise.
- **Murat:** add regression tests: no-op when roles match, replacement when they differ, child rows
  are `Document`s and the export is suppressed. Prove it with a real migrate and a Patch Log check.
- **John:** the PR should open with the deploy instruction.

## Change

- `restrict_page_roles()`: return early when the page already has exactly the Accounts roles (model
  sync normally imports them from the page JSON). Otherwise create any missing roles, rebuild the
  rows with `append`, set `page.flags.do_not_update_json` and save.
- The DocType-permission part of the patch is unchanged.
- New test: `crm/tests/test_finance_cockpit_roles_patch.py` (3 tests).

## Verification (2026-10-31)

| Check | Result |
|---|---|
| Old patch body (`0f2dd7f2`) on `crm-test.local` | `AttributeError: 'dict' object has no attribute 'is_new'` (reproduced) |
| New tests + `test_finance_access` | 15/15 pass |
| Real `bench migrate` on `crm-test.local` with roles set to `System Manager` and the Patch Log row removed | patch ran; roles = Accounts Manager, Accounts User; Patch Log row written; app source unchanged |
| `bench migrate` on the CRM dev site | exit 0; roles correct; Patch Log row present |
| Full CRM Python suite | 729 run; 55 fail. The **same 55** fail on clean `develop` (test-site data: missing KES→USD exchange rate, VAT template, package pricing). No new failures |
| Frontend `yarn test:run` | 241/241 pass |

## Deploy instructions for DevOps

1. Build from **`develop` at or after this PR's merge** (minimum `v1.0.159` for the OpenMeter work).
   Do not deploy `v1.0.90`–`v1.0.103`.
2. Rebuild the image without cache so old app code is not reused.
3. Run `bench --site <site> migrate`. The failed patch has no Patch Log row, so it runs again
   automatically. Then run `bench build --app crm` (if the image does not build assets) and restart.
4. Check: `select patch from \`tabPatch Log\` where patch like '%restrict_finance_cockpit%'`
   returns one row, and the Deal page shows the Metering tab.
