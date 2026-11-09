import { describe, expect, it } from 'vitest'
import {
  cockpitNewRecordHref,
  cockpitRecordHref,
  cockpitReportHref,
  cockpitSectionHref,
  parseCockpitHash,
} from '@/pages/FinanceCockpit/composables/useFinanceNavigation'

describe('useFinanceNavigation', () => {
  it('builds in-cockpit record hashes without redirecting to /app or /desk', () => {
    const href = cockpitRecordHref('Sales Invoice', 'ACC-SINV-2026-00001')
    expect(href).toBe('#/invoices?doctype=Sales+Invoice&name=ACC-SINV-2026-00001')
    expect(href).not.toContain('/app/')
    expect(href).not.toContain('/desk')
  })

  it('routes CRM and setup doctypes to their matching Finance Cockpit sections', () => {
    expect(cockpitRecordHref('CRM Quotation', 'CRM-QUO-0001')).toBe(
      '#/dashboard?doctype=CRM+Quotation&name=CRM-QUO-0001',
    )
    expect(cockpitRecordHref('CRM Opt-In Network', 'NET-001')).toBe(
      '#/partner-commission?tab=rebates&doctype=CRM+Opt-In+Network&name=NET-001',
    )
    expect(cockpitRecordHref('Account', 'Debtors - T')).toBe(
      '#/setup?tab=accounts&doctype=Account&name=Debtors+-+T',
    )
  })

  it('builds new-record and report hashes inside the cockpit', () => {
    expect(cockpitNewRecordHref('Journal Entry')).toBe(
      '#/general-ledger?tab=journal&doctype=Journal+Entry&mode=new',
    )
    expect(cockpitReportHref('Trial Balance')).toBe('#/reports?report=Trial+Balance')
    expect(cockpitSectionHref('payables', { tab: 'suppliers' })).toBe(
      '#/payables?tab=suppliers',
    )
  })

  it('rejects unsafe path characters in record names', () => {
    expect(cockpitRecordHref('Customer', '../etc/passwd')).toBe('')
  })

  it('parses cockpit hashes back into section, doctype, name, mode, and params', () => {
    const parsed = parseCockpitHash(
      '#/payables?doctype=Purchase+Invoice&name=ACC-PINV-001&mode=edit',
    )
    expect(parsed).toEqual({
      section: 'payables',
      doctype: 'Purchase Invoice',
      name: 'ACC-PINV-001',
      mode: 'edit',
      report: '',
      tab: '',
      params: {
        doctype: 'Purchase Invoice',
        name: 'ACC-PINV-001',
        mode: 'edit',
      },
    })
  })
})
