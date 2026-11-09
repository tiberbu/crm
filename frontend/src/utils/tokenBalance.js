// Token counts follow docs/cx-portal-ux-design-pattern.md: a number only when the metering
// service reports one. Without a live balance the portal says so instead of showing 0,
// which would read as "out of tokens".
export function tokenBalance(facility) {
  const entry = facility?.token_balance
  if (entry?.status === 'ok')
    return { known: true, value: Number(entry.balance) || 0 }
  // Metered, but nothing has been granted yet: zero is accurate.
  if (entry?.status === 'not_metered') return { known: true, value: 0 }
  return {
    known: false,
    value: 0,
    label: entry?.status === 'unavailable' ? 'Unavailable' : 'Not reported',
  }
}

export function tokenBalanceText(facility, unit = '') {
  const balance = tokenBalance(facility)
  if (!balance.known) return balance.label
  return `${balance.value.toLocaleString(undefined, { maximumFractionDigits: 4 })}${unit}`
}
