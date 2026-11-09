#!/usr/bin/env bash
set -euo pipefail

SITE="${1:-}"
if [ -z "$SITE" ]; then
	echo "usage: scripts/run-crm-tests.sh <site> [extra bench run-tests args...]" >&2
	exit 1
fi
shift

# Never let a caller override the --app scope: without --app crm, Frappe's
# runner executes every installed app's before_tests hook (see below).
for arg in "$@"; do
	if [ "$arg" = "--app" ] || { [ ${#arg} -gt 6 ] && [ "${arg:0:6}" = "--app=" ]; }; then
		echo "refusing: pass your test scope via --module/--doctype, not --app." >&2
		echo "this wrapper always scopes runs to the crm app." >&2
		exit 2
	fi
done

ALLOWED="$(bench --site "$SITE" show-config -f json 2>/dev/null | SITE="$SITE" python3 -c '
import json, os, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(3)
cfg = data.get(os.environ["SITE"]) or data
v = cfg.get("allow_tests")
print("true" if v in (True, "true", "1", 1) else "false")
' 2>/dev/null)" || true
if [ -z "$ALLOWED" ]; then
	echo "error: could not read site config for '$SITE' — refusing to run." >&2
	exit 3
fi
if [ "$ALLOWED" != "true" ]; then
	echo "refusing to run tests on '$SITE': allow_tests is not enabled." >&2
	echo "enable it deliberately first:  bench --site $SITE set-config allow_tests true" >&2
	echo "(and remember to set it back to false afterwards)" >&2
	exit 2
fi

# WHY THIS EXISTS: `bench run-tests` without `--app crm` makes Frappe's test
# runner execute EVERY installed app's before_tests hook. ERPNext's hook
# (erpnext/setup/utils.py) runs `delete from tabItem Price`, wiping all item
# prices on the site, and its test defaults also clobber Selling/Stock
# settings. On 2026-11-05 that blanked the public facility-onboarding package
# catalogue on the dev site.

exec bench --site "$SITE" run-tests --app crm "$@"
