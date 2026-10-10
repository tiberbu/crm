import { describe, expect, it } from 'vitest'
import {
  FINANCE_PRINT_FORMATS,
  printFormatFor,
  printUrl,
} from '../../src/pages/FinanceCockpit/constants/printFormats.js'

describe('Finance print formats', () => {
  it('maps every quotation-to-payment document to a native format', () => {
    expect(Object.keys(FINANCE_PRINT_FORMATS)).toEqual([
      'Quotation',
      'Sales Order',
      'Sales Invoice',
      'Payment Entry',
    ])
    expect(printFormatFor('Sales Invoice')).toBe('CRM Finance Invoice')
  })

  it('builds a printview URL with the selected ERPNext format', () => {
    expect(printUrl('Payment Entry', 'ACC-PAY-0001')).toContain(
      'format=CRM+Finance+Payment+Receipt',
    )
    expect(printUrl('Payment Entry', 'ACC-PAY-0001')).toContain(
      'trigger_print=1',
    )
    expect(printUrl('Payment Entry', 'ACC-PAY-0001')).toContain(
      'no_letterhead=0',
    )
  })
})
