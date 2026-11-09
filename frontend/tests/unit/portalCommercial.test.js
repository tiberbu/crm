import { describe, expect, it } from 'vitest'
import {
  accountLevelRows,
  balanceOrNextLabel,
  balanceOrNextText,
  canTopUp,
  capRows,
  commercialOf,
  dedupeByName,
  facilityPayments,
  facilityPlanText,
  formatDate,
  isProjected,
  mergeFacilityInvoices,
  mergeFacilityOrders,
  money,
  orderStatus,
  orderTitle,
  portfolioColumnLabel,
  portfolioPlanSummary,
  rowFacilityMfls,
  rowsForFacility,
  showsTokens,
  sortInvoices,
  stageStates,
} from '@/utils/portalCommercial'

const network = {
  mfl_code: 'FBE2E-001',
  commercial: {
    journey: 'network_optin',
    journey_label: 'Network Opt-In',
    plan_type: 'time_bound',
    has_tokens: false,
    unavailable: false,
    plan: {
      name: 'Network subscription',
      source: 'optin_contract',
      status: 'Active',
      cycle: 'Quarterly',
      cycle_label: 'Billed quarterly',
      term_years: 5,
      term_label: '5 years',
      currency: 'KES',
      facilities_on_plan: 2,
      next_invoice: {
        label: 'Year 1 · Quarter 1',
        date: '2027-01-30',
        amount_incl_vat: 6960,
        projected: true,
      },
      schedule: [],
    },
    quotes: [
      { name: 'SAL-QTN-1', label: 'Year 1', status_label: 'Accepted', amount: 27840, currency: 'KES' },
    ],
  },
}

const tokenFacility = {
  mfl_code: 'FBE2E-002',
  token_package: 'Starter',
  token_quantity: 100,
  commercial: {
    journey: 'self_onboarding',
    journey_label: 'Self-Onboarding',
    plan_type: 'token',
    has_tokens: true,
    unavailable: false,
    plan: { name: 'Starter', source: 'token_package', cycle: '', cycle_label: '', next_invoice: null },
    quotes: [],
  },
}

const unknownFacility = {
  mfl_code: 'FBE2E-003',
  commercial: {
    journey: 'unknown',
    journey_label: '',
    plan_type: 'unknown',
    has_tokens: false,
    unavailable: false,
    plan: { name: '', source: 'none', cycle: '', cycle_label: '', next_invoice: null },
    quotes: [],
  },
}

const mixedOrders = [
  { name: 'SAL-ORD-1', facility_mfls: ['FBE2E-001'], transaction_date: '2026-11-01' },
  { name: 'SAL-ORD-2', facility_mfls: ['FBE2E-001', 'FBE2E-002'], transaction_date: '2026-11-02' },
  { name: 'SAL-ORD-3', transaction_date: '2026-11-03' },
  { name: 'SAL-ORD-4', crm_token_facility_mfl: 'FBE2E-002', transaction_date: '2026-11-04' },
]

describe('portalCommercial', () => {
  it('normalizes commercial and applies the legacy fallback (SPEC 5.4)', () => {
    expect(commercialOf(network).plan_type).toBe('time_bound')
    expect(commercialOf(network).quotes).toHaveLength(1)
    expect(commercialOf({ token_package: 'X' }).plan_type).toBe('token')
    expect(commercialOf({}).plan_type).toBe('unknown')
    expect(commercialOf(null).journey).toBe('unknown')
    expect(commercialOf({ token_quantity: 5 }).has_tokens).toBe(true)
  })

  it('implements SPEC 5.5 predicates', () => {
    expect(showsTokens(tokenFacility)).toBe(true)
    expect(showsTokens(network)).toBe(false)
    expect(showsTokens(unknownFacility)).toBe(false)
    expect(canTopUp(tokenFacility)).toBe(true)
    expect(canTopUp(unknownFacility)).toBe(true)
    expect(canTopUp({ ...unknownFacility, commercial: { ...unknownFacility.commercial, journey: 'network_optin' } })).toBe(
      false,
    )
    expect(canTopUp(network)).toBe(false)
    // SPEC 5.5: canTopUp = showsTokens || unknown-not-network. A time-bound plan with a
    // live token meter still showsTokens, so it can top up (SPEC 6 "Time-bound with tokens").
    const hybrid = { ...network, commercial: { ...network.commercial, has_tokens: true } }
    expect(canTopUp(hybrid)).toBe(true)
    expect(showsTokens(hybrid)).toBe(true)
  })

  it('deduplicates by name keeping the first row and order', () => {
    const rows = [
      { name: 'A', extra: 1 },
      { name: 'B' },
      { name: 'A', extra: 2 },
      { name: 'A' },
    ]
    const deduped = dedupeByName(rows)
    expect(deduped.map((row) => row.name)).toEqual(['A', 'B'])
    expect(deduped[0].extra).toBe(1)
  })

  it('reads facility attribution from facility_mfls first, then the legacy tag', () => {
    expect(rowFacilityMfls({ facility_mfls: ['X', 'Y'] })).toEqual(['X', 'Y'])
    expect(rowFacilityMfls({ crm_token_facility_mfl: 'z' })).toEqual(['z'])
    expect(rowFacilityMfls({})).toEqual([])
  })

  it('splits rows into facility rows and account-level rows', () => {
    expect(rowsForFacility(mixedOrders, 'fbe2e-001').map((row) => row.name)).toEqual([
      'SAL-ORD-1',
      'SAL-ORD-2',
    ])
    expect(rowsForFacility(mixedOrders, 'FBE2E-002').map((row) => row.name)).toEqual([
      'SAL-ORD-2',
      'SAL-ORD-4',
    ])
    expect(accountLevelRows(mixedOrders).map((row) => row.name)).toEqual(['SAL-ORD-3'])
  })

  it('covers every order in a facility merge or the account-level notice (I1)', () => {
    const facilities = ['FBE2E-001', 'FBE2E-002', 'FBE2E-003'].map((mfl) => ({ mfl_code: mfl }))
    const merged = new Set()
    for (const facility of facilities) {
      for (const order of mergeFacilityOrders(facility, mixedOrders)) merged.add(order.name)
    }
    for (const order of accountLevelRows(mixedOrders)) merged.add(order.name)
    expect([...merged].sort()).toEqual(['SAL-ORD-1', 'SAL-ORD-2', 'SAL-ORD-3', 'SAL-ORD-4'])
    expect(merged.size).toBe(4)
  })

  it('merges facility history with the unified list, unique and newest first', () => {
    const facility = { mfl_code: 'FBE2E-001', orders: [{ name: 'SAL-ORD-9', transaction_date: '2026-11-05' }] }
    const merged = mergeFacilityOrders(facility, mixedOrders)
    expect(merged.map((row) => row.name)).toEqual(['SAL-ORD-9', 'SAL-ORD-2', 'SAL-ORD-1'])
    const mergedInvoices = mergeFacilityInvoices({ mfl_code: 'FBE2E-001' }, [
      { name: 'ACC-INV-1', facility_mfls: ['FBE2E-001'] },
      { name: 'ACC-INV-2', facility_mfls: [] },
    ])
    expect(mergedInvoices.map((row) => row.name)).toEqual(['ACC-INV-1'])
  })

  it('adds pending verification reports to facility payments without duplicates', () => {
    const invoices = [{ name: 'ACC-INV-1' }]
    const payments = [
      { name: 'PE-1', invoice: 'ACC-INV-1', status: 'Pending Verification' },
      { name: 'PE-2', invoice_names: ['ACC-INV-1'], status: 'Pending Verification' },
    ]
    const merged = facilityPayments({ mfl_code: 'X', payments: [{ name: 'PE-1', invoice: 'ACC-INV-1' }] }, payments, invoices)
    expect(merged.map((row) => row.name)).toEqual(['PE-1', 'PE-2'])
  })

  it('sorts open invoices by due date first, then paid newest first', () => {
    const invoices = [
      { name: 'P2', amount: 0, posting_date: '2026-01-02' },
      { name: 'O2', amount: 100, due_date: '2026-05-01' },
      { name: 'P1', amount: 0, posting_date: '2026-01-10' },
      { name: 'O1', amount: 50, due_date: '2026-04-01' },
    ]
    expect(sortInvoices(invoices).map((row) => row.name)).toEqual(['O1', 'O2', 'P1', 'P2'])
  })

  it('falls back for order titles and statuses (F4)', () => {
    expect(orderTitle({ display_title: 'Year 1 · Quarter 1 subscription' }, [])).toBe(
      'Year 1 · Quarter 1 subscription',
    )
    expect(orderTitle({ crm_token_package_item: 'TOK-A' }, [{ item_code: 'TOK-A', display_name: 'Core' }])).toBe(
      'Core',
    )
    expect(orderTitle({}, [])).toBe('Order')
    expect(orderStatus({})).toBe('Awaiting invoice')
    expect(orderStatus({ is_draft: true })).toBe('Needs your review')
    expect(orderStatus({ display_status: 'Confirmed' })).toBe('Confirmed')
  })

  it('uses record_counts when the context row only carries actionable records (S4)', () => {
    const keys = (result) => result.map((stage) => `${stage.key}:${stage.state}`)
    // Fully paid history: no rows in context, counts show it exists.
    expect(
      keys(
        stageStates({
          showQuote: false,
          quotes: [],
          orders: [],
          invoices: [],
          payments: [],
          counts: { order: 4, order_draft: 0, invoice: 4, invoice_due: 0, payment: 4, payment_pending: 0 },
        }),
      ),
    ).toEqual(['order:done', 'invoice:done', 'payment:done'])
    // One invoice due and paid ones in history: invoices are current.
    expect(
      keys(
        stageStates({
          showQuote: false,
          quotes: [],
          orders: [],
          invoices: [{ amount: 500 }],
          payments: [],
          counts: { order: 3, invoice: 3, invoice_due: 1, payment: 2 },
        }),
      ),
    ).toEqual(['order:done', 'invoice:current', 'payment:upcoming'])
    // No counts: the old row-based behaviour is unchanged.
    expect(
      keys(stageStates({ showQuote: false, quotes: [], orders: [], invoices: [], payments: [] })),
    ).toEqual(['order:current', 'invoice:upcoming', 'payment:upcoming'])
  })

  it('computes stage states per the SPEC 7.2 table', () => {
    const keys = (result) => result.map((stage) => `${stage.key}:${stage.state}`)
    // Quote done (accepted), order pending (draft), rest upcoming
    expect(
      keys(
        stageStates({
          showQuote: true,
          quotes: [{ status_label: 'Accepted' }],
          orders: [{ is_draft: true }],
          invoices: [],
          payments: [],
        }),
      ),
    ).toEqual(['quote:done', 'order:current', 'invoice:upcoming', 'payment:upcoming'])
    // Quote pending (unaccepted), order done; the later pending invoice shows upcoming
    expect(
      keys(
        stageStates({
          showQuote: true,
          quotes: [{ status_label: 'Planned' }],
          orders: [{ is_draft: false }],
          invoices: [{ amount: 10 }],
          payments: [],
        }),
      ),
    ).toEqual(['quote:current', 'order:done', 'invoice:upcoming', 'payment:upcoming'])
    // All stages done: nothing becomes current
    expect(
      keys(
        stageStates({
          showQuote: false,
          quotes: [],
          orders: [{ is_draft: false }],
          invoices: [{ amount: 0 }],
          payments: [{ status: 'Recorded' }],
        }),
      ),
    ).toEqual(['order:done', 'invoice:done', 'payment:done'])
    // Pending report keeps payment pending
    expect(
      keys(
        stageStates({
          showQuote: false,
          quotes: [],
          orders: [{ is_draft: false }],
          invoices: [{ amount: 0 }],
          payments: [{ status: 'Pending Verification' }],
        }),
      ),
    ).toEqual(['order:done', 'invoice:done', 'payment:current'])
    // Later pending stages render upcoming behind the first current
    expect(
      keys(
        stageStates({
          showQuote: true,
          quotes: [{ status_label: 'Planned' }],
          orders: [],
          invoices: [{ amount: 10 }],
          payments: [{ status: 'Pending Verification' }],
        }),
      ),
    ).toEqual(['quote:current', 'order:upcoming', 'invoice:upcoming', 'payment:upcoming'])
    // Nothing pending: the first upcoming stage becomes current
    expect(
      keys(
        stageStates({
          showQuote: true,
          quotes: [],
          orders: [],
          invoices: [],
          payments: [],
        }),
      ),
    ).toEqual(['quote:current', 'order:upcoming', 'invoice:upcoming', 'payment:upcoming'])
  })

  it('caps rows for the show-all toggle', () => {
    const rows = Array.from({ length: 7 }, (_, i) => ({ name: `R${i}` }))
    expect(capRows(rows, false)).toHaveLength(5)
    expect(capRows(rows, true)).toHaveLength(7)
  })

  it('formats dates as local dates so day 30 never shifts', () => {
    const text = formatDate('2027-01-30')
    expect(text).toMatch(/\b30\b/)
    expect(formatDate('')).toBe('')
    expect(formatDate(null)).toBe('')
    expect(formatDate('not-a-date')).toBe('not-a-date')
    expect(isProjected({ projected: true })).toBe(true)
    expect(isProjected({})).toBe(false)
  })

  it('renders the plan-aware helper rows (SPEC 8.1)', () => {
    expect(facilityPlanText(network)).toEqual(['Network subscription', 'Billed quarterly'])
    expect(facilityPlanText(tokenFacility)).toEqual(['Starter'])
    expect(facilityPlanText(unknownFacility)).toEqual(['No active plan'])
    expect(balanceOrNextLabel(network)).toBe('Next invoice')
    expect(balanceOrNextLabel(tokenFacility)).toBe('Available tokens')
    expect(balanceOrNextLabel(unknownFacility)).toBe('Plan')
    expect(balanceOrNextText(network)).toBe(`Projected ${formatDate('2027-01-30')}`)
    expect(balanceOrNextText({ ...network, commercial: { ...network.commercial, plan: { ...network.commercial.plan, next_invoice: null } } })).toBe(
      'Not scheduled',
    )
    expect(balanceOrNextText(unknownFacility)).toBe('Not set up yet')
    expect(balanceOrNextText(tokenFacility)).toBe('Not reported')
  })

  it('summarizes the portfolio for the KPI and table header (SPEC 8)', () => {
    const summary = portfolioPlanSummary([network, tokenFacility, unknownFacility])
    expect(summary).toEqual({
      tokenFacilities: 1,
      planFacilities: 1,
      nextInvoice: { date: '2027-01-30', amount: 6960, projected: true },
    })
    expect(portfolioColumnLabel([network, tokenFacility])).toBe('Tokens or next invoice')
    expect(portfolioColumnLabel([tokenFacility])).toBe('Available tokens')
    expect(portfolioColumnLabel([network, unknownFacility])).toBe('Next invoice')
  })

  it('formats money like the rest of the portal', () => {
    // Intl may insert a narrow or non-breaking space between code and number.
    expect(money(6960, undefined, 'KES').replace(/[\u00a0\u202f]/g, ' ')).toBe('KES 6,960')
    expect(money(1234.56, 'USD').replace(/[\u00a0\u202f]/g, ' ')).toBe('USD 1,235')
  })
})
