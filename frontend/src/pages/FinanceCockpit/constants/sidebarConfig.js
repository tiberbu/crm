// Finance Workspace navigation. Labels describe the finance job, while the
// underlying CRM and accounting document sections remain unchanged.
// iconClass must be a full static lucide-* Tailwind class (JIT requires static strings).
export const SIDEBAR_SECTIONS = [
  {
    key: 'dashboard',
    label: 'Today',
    group: 'Workspace',
    iconClass: 'lucide-layout-dashboard',
    hash: '#/dashboard',
    visibleRoles: 'all',
  },
  {
    key: 'quotes',
    label: 'Quotations',
    group: 'Sales',
    iconClass: 'lucide-file-text',
    hash: '#/quotes',
    visibleRoles: 'all',
  },
  {
    key: 'orders',
    label: 'Sales Orders',
    group: 'Sales',
    iconClass: 'lucide-shopping-cart',
    hash: '#/orders',
    visibleRoles: 'all',
  },
  {
    key: 'invoices',
    label: 'Receivables',
    group: 'Sales',
    iconClass: 'lucide-receipt',
    hash: '#/invoices',
    visibleRoles: 'all',
  },
  {
    key: 'payments',
    label: 'Payments',
    group: 'Accounting',
    iconClass: 'lucide-banknote',
    hash: '#/payments',
    visibleRoles: 'all',
  },
  {
    key: 'partner_commission',
    label: 'Network & Commission',
    group: 'Accounting',
    iconClass: 'lucide-handshake',
    hash: '#/partner-commission',
    visibleRoles: 'all',
  },
  {
    key: 'payables',
    label: 'Payables',
    group: 'Accounting',
    iconClass: 'lucide-wallet-cards',
    hash: '#/payables',
    visibleRoles: 'all',
  },
  {
    key: 'expenses',
    label: 'Expenses',
    group: 'Accounting',
    iconClass: 'lucide-receipt-text',
    hash: '#/expenses',
    visibleRoles: 'all',
  },
  {
    key: 'banking',
    label: 'Banking',
    group: 'Accounting',
    iconClass: 'lucide-landmark',
    hash: '#/banking',
    visibleRoles: 'all',
  },
  {
    key: 'assets',
    label: 'Assets',
    group: 'Accounting',
    iconClass: 'lucide-building',
    hash: '#/assets',
    visibleRoles: 'all',
  },
  {
    key: 'liabilities',
    label: 'Liabilities',
    group: 'Accounting',
    iconClass: 'lucide-scale',
    hash: '#/liabilities',
    visibleRoles: 'all',
  },
  {
    key: 'general_ledger',
    label: 'General Ledger',
    group: 'Accounting',
    iconClass: 'lucide-book-open',
    hash: '#/general-ledger',
    visibleRoles: 'all',
  },
  {
    key: 'reports',
    label: 'Reports',
    group: 'Insights',
    iconClass: 'lucide-bar-chart-2',
    hash: '#/reports',
    visibleRoles: 'all',
  },
  {
    key: 'setup',
    label: 'Setup',
    group: 'Administration',
    iconClass: 'lucide-settings-2',
    hash: '#/setup',
    visibleRoles: ['Accounts Manager'],
  },
]

export function getFinanceSections(roles = []) {
  const roleSet = new Set(roles)
  return SIDEBAR_SECTIONS.filter(
    (section) =>
      section.visibleRoles === 'all' ||
      roleSet.has('Administrator') ||
      section.visibleRoles.some((role) => roleSet.has(role)),
  )
}
