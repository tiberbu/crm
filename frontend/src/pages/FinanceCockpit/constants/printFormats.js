export const FINANCE_PRINT_FORMATS = Object.freeze({
  Quotation: 'CRM Finance Quotation',
  'Sales Order': 'CRM Finance Sales Order',
  'Sales Invoice': 'CRM Finance Invoice',
  'Payment Entry': 'CRM Finance Payment Receipt',
})

export function printFormatFor(doctype) {
  return FINANCE_PRINT_FORMATS[doctype] || ''
}

export function printUrl(doctype, name) {
  const params = new URLSearchParams({
    doctype,
    name,
    trigger_print: '1',
    no_letterhead: '0',
  })
  const format = printFormatFor(doctype)
  if (format) params.set('format', format)
  return `/printview?${params.toString()}`
}
