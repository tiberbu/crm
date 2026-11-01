# Deal › Metering tab

OpenMeter Probe activities on the CRM Deal page, so an OpenMeter Admin doesn't have to open Desk.

## Who sees it

- The tab shows only when a metering app answers the `crm_metering_admin_access` hook and the user is an OpenMeter Admin (or System Manager).
- Only the Administrator user sees **Reveal full key**, and must enter their password each time. Each reveal is recorded on the metering site.
- Without a metering app, the tab never shows and CRM works as before.

## What it does

One card per deal facility, Facility ID first:

| Area | Actions |
|---|---|
| Onboarding | Status, sync status and access; **Sync to OpenMeter**; **Send probe event** (checks the round trip) |
| Site key | Masked prefix, issue date and delivery; **Issue site key**; **Reveal full key** (Administrator) |
| Welcome bonus | Whether the facility's one-time welcome bonus is out, when and how (by whom, auto-assigned with which order, or with which paid invoice); **Dispense N bonus tokens**, disabled for good once dispensed. See [welcome-bonus-dispense.md](./welcome-bonus-dispense.md) |
| Balances | Granted, used this period, remaining and overage; grants; **Re-issue expiring grants** |
| Delivery | Queued, delivered and failed counts; recent events; **Retry failed events** |

Tab header: **Test connection**, **Import sites from CRM**, and under **More**: **Site keys for existing facilities** (send keys to HMIS sites that predate metering) and **Scan paid token purchases**.

Meters, features and prices are not managed here. They are configured on the standalone OpenMeter dashboard.

## Contract

CRM never imports the metering app. `crm/api/metering_admin.py` calls these hooks:

| Hook | Called with | Returns |
|---|---|---|
| `crm_metering_admin_access` | — | `{can_manage, can_reveal}` |
| `crm_metering_admin_facility` | `fid` | `{fid, imported, ...probe data}` |
| `crm_metering_admin_action` | `action, fid=None, params={}` | the action's result |
| `crm_metering_admin_reveal_key` | `fid, password` | `{key, header, endpoint, status}` |
| `crm_welcome_bonus_status` | `fid` | `{fid, dispensed, status, tokens, dispensed_at, source_doctype, source_name, error}` |
| `crm_dispense_welcome_bonus` | `fid, tokens, source_doctype=None, source_name=None` | the status above plus `changed` and `reason` |

The two welcome-bonus hooks do no role check: CRM's `get_welcome_bonus` and `dispense_welcome_bonus` endpoints require an OpenMeter Admin, and the auto-assign job runs as the system.

The metering app enforces its own roles, the action allow-list, the password check and its rate limit. CRM's `reveal_key` endpoint is POST-only and rate limited too. The key stays in the tab's dialog and is cleared when it closes.
