import { ref, provide, inject } from 'vue'

const NAV_KEY = Symbol('fc_navigation')

export const DOCTYPE_ROUTES = {
  'Sales Invoice': { section: 'invoices', doctype: 'Sales Invoice' },
  'Sales Order': { section: 'orders', doctype: 'Sales Order' },
  Quotation: { section: 'quotes', doctype: 'Quotation' },
  'Payment Entry': { section: 'payments', doctype: 'Payment Entry' },
  'Purchase Invoice': {
    section: 'payables',
    tab: 'invoices',
    doctype: 'Purchase Invoice',
  },
  'Purchase Order': {
    section: 'payables',
    tab: 'orders',
    doctype: 'Purchase Order',
  },
  Supplier: {
    section: 'payables',
    tab: 'suppliers',
    doctype: 'Supplier',
  },
  Customer: {
    section: 'invoices',
    doctype: 'Customer',
  },
  'Expense Claim': {
    section: 'expenses',
    tab: 'claims',
    doctype: 'Expense Claim',
  },
  'Employee Advance': {
    section: 'expenses',
    tab: 'advances',
    doctype: 'Employee Advance',
  },
  'Journal Entry': {
    section: 'general_ledger',
    tab: 'journal',
    doctype: 'Journal Entry',
  },
  'GL Entry': {
    section: 'general_ledger',
    tab: 'gl',
    doctype: 'GL Entry',
  },
  'Period Closing Voucher': {
    section: 'general_ledger',
    tab: 'closing',
    doctype: 'Period Closing Voucher',
  },
  'Bank Account': {
    section: 'banking',
    tab: 'accounts',
    doctype: 'Bank Account',
  },
  'Bank Transaction': {
    section: 'banking',
    tab: 'transactions',
    doctype: 'Bank Transaction',
  },
  'CRM Partner Rebate Voucher': {
    section: 'partner_commission',
    tab: 'rebates',
    doctype: 'CRM Partner Rebate Voucher',
  },
  'CRM Sales Commission': {
    section: 'partner_commission',
    tab: 'commissions',
    doctype: 'CRM Sales Commission',
  },
  Asset: {
    section: 'assets',
    doctype: 'Asset',
  },
  Subscription: {
    section: 'liabilities',
    tab: 'subscriptions',
    doctype: 'Subscription',
  },
  Account: {
    section: 'setup',
    tab: 'accounts',
    doctype: 'Account',
  },
  'Cost Center': {
    section: 'setup',
    tab: 'cost-centres',
    doctype: 'Cost Center',
  },
  'Accounting Dimension': {
    section: 'setup',
    tab: 'dimensions',
    doctype: 'Accounting Dimension',
  },
  'Sales Taxes and Charges Template': {
    section: 'setup',
    tab: 'taxes',
    doctype: 'Sales Taxes and Charges Template',
  },
  'Payment Terms Template': {
    section: 'setup',
    tab: 'terms',
    doctype: 'Payment Terms Template',
  },
  'Mode of Payment': {
    section: 'setup',
    tab: 'methods',
    doctype: 'Mode of Payment',
  },
  'Fiscal Year': {
    section: 'setup',
    tab: 'fiscal-year',
    doctype: 'Fiscal Year',
  },
  'Currency Exchange Settings': {
    section: 'setup',
    tab: 'currency',
    doctype: 'Currency Exchange Settings',
  },
  'CRM Opt-In Network': {
    section: 'partner_commission',
    tab: 'rebates',
    doctype: 'CRM Opt-In Network',
  },
  'CRM Pre-Qualified Facility': {
    section: 'quotes',
    doctype: 'CRM Pre-Qualified Facility',
  },
  'CRM Opt-In Submission': {
    section: 'quotes',
    doctype: 'CRM Opt-In Submission',
  },
  'CRM Contract': {
    section: 'quotes',
    doctype: 'CRM Contract',
  },
  'CRM Deal': {
    section: 'quotes',
    doctype: 'CRM Deal',
  },
}

export function hasUnsafePathCharacters(value) {
  if (typeof value !== 'string') return true
  const trimmed = value.trim()
  if (!trimmed) return true
  return (
    trimmed.includes('/') ||
    trimmed.includes('\\') ||
    [...trimmed].some((character) => character.charCodeAt(0) < 32)
  )
}

function normalizeOptions(companyOrOptions) {
  if (!companyOrOptions) return {}
  if (typeof companyOrOptions === 'string') {
    return { company: companyOrOptions }
  }
  if (typeof companyOrOptions === 'object') {
    return companyOrOptions
  }
  return {}
}

export function sectionToSlug(section) {
  return String(section || 'dashboard')
    .trim()
    .replace(/_/g, '-')
}

export function slugToSection(slug) {
  return String(slug || 'dashboard')
    .trim()
    .replace(/-/g, '_')
}

export function cockpitRecordHref(doctype, name, companyOrOptions = '') {
  if (hasUnsafePathCharacters(doctype) || hasUnsafePathCharacters(name)) {
    return ''
  }
  const cleanDoctype = doctype.trim()
  const cleanName = name.trim()
  const opts = normalizeOptions(companyOrOptions)
  const route = DOCTYPE_ROUTES[cleanDoctype] || {
    section: opts.section || 'dashboard',
    doctype: cleanDoctype,
  }
  const sectionSlug = sectionToSlug(opts.section || route.section)
  const params = new URLSearchParams()
  const tab = opts.tab || route.tab
  if (tab) params.set('tab', tab)
  params.set('doctype', cleanDoctype)
  params.set('name', cleanName)
  if (opts.company && typeof opts.company === 'string' && opts.company.trim()) {
    params.set('company', opts.company.trim())
  }
  if (opts.mode && typeof opts.mode === 'string') {
    params.set('mode', opts.mode)
  }
  const prefix = opts.absolute ? '/finance-cockpit' : ''
  return `${prefix}#/${sectionSlug}?${params.toString()}`
}

export function cockpitNewRecordHref(doctype, options = {}) {
  if (hasUnsafePathCharacters(doctype)) return ''
  const cleanDoctype = doctype.trim()
  const route = DOCTYPE_ROUTES[cleanDoctype] || {
    section: options.section || 'dashboard',
    doctype: cleanDoctype,
  }
  const sectionSlug = sectionToSlug(options.section || route.section)
  const params = new URLSearchParams()
  const tab = options.tab || route.tab
  if (tab) params.set('tab', tab)
  params.set('doctype', cleanDoctype)
  params.set('mode', 'new')
  for (const [k, v] of Object.entries(options.params || {})) {
    if (v != null && v !== '') params.set(k, String(v))
  }
  if (options.company) params.set('company', String(options.company))
  const prefix = options.absolute ? '/finance-cockpit' : ''
  return `${prefix}#/${sectionSlug}?${params.toString()}`
}

export function cockpitReportHref(reportName, filters = {}, options = {}) {
  if (hasUnsafePathCharacters(reportName)) return ''
  const params = new URLSearchParams()
  params.set('report', reportName.trim())
  for (const [k, v] of Object.entries(filters || {})) {
    if (v != null && v !== '') params.set(k, String(v))
  }
  const prefix = options.absolute ? '/finance-cockpit' : ''
  return `${prefix}#/reports?${params.toString()}`
}

export function cockpitSectionHref(section, params = {}, options = {}) {
  const sectionSlug = sectionToSlug(section)
  const search = new URLSearchParams()
  for (const [k, v] of Object.entries(params || {})) {
    if (v != null && v !== '') search.set(k, String(v))
  }
  const prefix = options.absolute ? '/finance-cockpit' : ''
  const qs = search.toString()
  return qs ? `${prefix}#/${sectionSlug}?${qs}` : `${prefix}#/${sectionSlug}`
}

export function parseCockpitHash(rawHash) {
  const hash = String(rawHash || '').trim()
  if (!hash.startsWith('#/')) {
    return {
      section: 'dashboard',
      tab: '',
      doctype: '',
      name: '',
      mode: '',
      report: '',
      params: {},
    }
  }
  const withoutPrefix = hash.slice(2)
  const qIndex = withoutPrefix.indexOf('?')
  const pathPart = qIndex >= 0 ? withoutPrefix.slice(0, qIndex) : withoutPrefix
  const queryPart = qIndex >= 0 ? withoutPrefix.slice(qIndex + 1) : ''
  const section = slugToSection(pathPart || 'dashboard')
  const searchParams = new URLSearchParams(queryPart)
  const params = {}
  for (const [k, v] of searchParams.entries()) {
    params[k] = v
  }
  return {
    section,
    tab: params.tab || '',
    doctype: params.doctype || '',
    name: params.name || '',
    mode: params.mode || '',
    report: params.report || '',
    params,
  }
}

const fallbackState = ref({
  section: 'dashboard',
  tab: '',
  doctype: '',
  name: '',
  mode: '',
  report: '',
  params: {},
})

function fallbackNavigate(target) {
  if (typeof target === 'string') {
    if (target.startsWith('#/')) {
      if (typeof window !== 'undefined') window.location.hash = target
      fallbackState.value = parseCockpitHash(target)
      return
    }
    const href = cockpitSectionHref(target)
    if (typeof window !== 'undefined') window.location.hash = href
    fallbackState.value = parseCockpitHash(href)
    return
  }
  if (target && typeof target === 'object') {
    if (target.report) {
      const href = cockpitReportHref(target.report, target.filters || {})
      if (typeof window !== 'undefined') window.location.hash = href
      fallbackState.value = parseCockpitHash(href)
      return
    }
    if (target.doctype && target.name) {
      const href = cockpitRecordHref(target.doctype, target.name, target)
      if (typeof window !== 'undefined') window.location.hash = href
      fallbackState.value = parseCockpitHash(href)
      return
    }
    if (target.doctype && target.mode === 'new') {
      const href = cockpitNewRecordHref(target.doctype, target)
      if (typeof window !== 'undefined') window.location.hash = href
      fallbackState.value = parseCockpitHash(href)
      return
    }
    if (target.section) {
      const href = cockpitSectionHref(target.section, target.params || {})
      if (typeof window !== 'undefined') window.location.hash = href
      fallbackState.value = parseCockpitHash(href)
    }
  }
}

export function provideFinanceNavigation(customNavigate) {
  const navState = ref(
    typeof window !== 'undefined'
      ? parseCockpitHash(window.location.hash)
      : { ...fallbackState.value },
  )
  const navigateTo = (target) => {
    if (customNavigate) {
      customNavigate(target)
    } else {
      fallbackNavigate(target)
      navState.value = { ...fallbackState.value }
    }
  }
  const clearRecordParams = () => {
    const current = navState.value
    const nextParams = {}
    if (current.tab) nextParams.tab = current.tab
    const href = cockpitSectionHref(current.section, nextParams)
    if (typeof window !== 'undefined') window.location.hash = href
    navState.value = parseCockpitHash(href)
  }
  const ctx = {
    navState,
    navigateTo,
    clearRecordParams,
    cockpitRecordHref,
    cockpitNewRecordHref,
    cockpitReportHref,
    cockpitSectionHref,
  }
  provide(NAV_KEY, ctx)
  return ctx
}

export function useFinanceNavigation() {
  return inject(NAV_KEY, {
    navState: fallbackState,
    navigateTo: fallbackNavigate,
    clearRecordParams: () => {},
    cockpitRecordHref,
    cockpitNewRecordHref,
    cockpitReportHref,
    cockpitSectionHref,
  })
}
