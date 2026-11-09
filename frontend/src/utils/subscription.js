// The customer's view of a Fixed subscription (CRM P-114, openmeter_mediator ADR-007).
// `subscription` is { status, package, billing_period, activated_at, expires_at, cancelled_at },
// dates in ISO-8601 UTC. Pure, so it is unit-tested.

export function formatDay(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

// The Subscription summary card: a short value and a note, or null when there is no term.
export function subscriptionCard(subscription, format = formatDay) {
  if (!subscription?.status) return null
  const until = format(subscription.expires_at)
  const since = format(subscription.activated_at)
  const values = {
    active: `Active until ${until}`,
    scheduled: `Starts ${since}`,
    expired: `Expired ${until}`,
    cancelled: `Cancelled ${format(subscription.cancelled_at) || until}`,
  }
  const notes = {
    active: `Active since ${since}`,
    scheduled: `Paid · runs until ${until}`,
    expired: 'Pay the next invoice to renew',
    cancelled: 'Contact support to start again',
  }
  const pkg = subscription.package ? ` · ${subscription.package}` : ''
  return {
    value: values[subscription.status] || subscription.status,
    note: `${notes[subscription.status] || ''}${pkg}`,
  }
}
