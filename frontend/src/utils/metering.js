// Pure helpers for the Deal page's Metering tab (OpenMeter Probe activities in the CRM UI).

// What the site-key area can offer: no key yet, a key issued before keys could be
// revealed, a key the Administrator can reveal, or a key shown by its prefix only.
export function keyState(site, canReveal) {
  if (!site?.site_key_prefix) return 'none'
  if (!canReveal) return 'masked'
  return site.key_revealable ? 'revealable' : 'legacy'
}

export function maskedKey(prefix) {
  return prefix ? `${prefix}…••••••••••••••••` : ''
}

const TONES = {
  status: { Active: 'green', Suspended: 'red' },
  sync: { Synced: 'green', Error: 'red' },
  connection: { Reachable: 'green', Unreachable: 'red' },
}

// frappe-ui Badge theme for a site status, sync status or connection status.
export function tone(kind, value) {
  if (!value) return 'gray'
  return TONES[kind]?.[value] || 'orange'
}

// Granted / Used / Remaining / Overage; null where OpenMeter gave no entitlement value.
export function balanceStats(data) {
  const ent = data?.entitlement
  const grants = data?.grants || []
  return [
    {
      label: 'Granted',
      value: data?.granted_total ?? 0,
      hint: `${grants.filter((g) => g.status === 'Granted').length} grant(s)`,
    },
    {
      label: 'Used this period',
      value: ent ? (ent.usage ?? 0) : null,
      hint: data?.site?.usage_period_interval || '',
    },
    {
      label: 'Remaining',
      value: ent ? (ent.balance ?? 0) : null,
      hint: `Package: ${Number(data?.site?.token_quantity || 0).toLocaleString()} tokens`,
    },
    { label: 'Overage', value: ent ? (ent.overage ?? 0) : null, hint: '' },
  ]
}

// Where the facility's one welcome bonus came from: a user (plain text) or a
// linkable document (the order that selected the package, or the paid invoice).
export function welcomeBonusVia(state) {
  if (!state?.dispensed) return null
  if (state.source_doctype === 'Sales Order' && state.source_name)
    return { kind: 'order', name: state.source_name }
  if (state.source_doctype === 'Sales Invoice' && state.source_name)
    return { kind: 'invoice', name: state.source_name }
  return { kind: 'user', label: state.source_label || state.source_name || '' }
}

// The Token purchase / Partner coupon lines of the facility card, straight from the
// grant ledger (the single source of truth). One entry per grant, never a sum.
export function tokenLines(grants) {
  const purchase = []
  const coupon = []
  for (const grant of grants || []) {
    if (grant.grant_source === 'Token Purchase') purchase.push(grant)
    else if (grant.grant_source === 'Partner Coupon' || grant.grant_source === 'CRM Coupon')
      coupon.push(grant)
  }
  return { purchase, coupon }
}

// Outcome of "Send probe event" before the round trip is checked.
export function probeOutcome(result) {
  const event = result?.event || {}
  if (event.status === 'Delivered')
    return { delivered: true, event: event.name }
  return {
    delivered: false,
    message:
      event.last_error ||
      result?.delivery?.skipped ||
      'Still queued; it will retry automatically.',
  }
}
