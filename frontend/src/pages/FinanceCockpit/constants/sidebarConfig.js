// Finance Workspace navigation. Labels describe the finance job, while the
// underlying native CRM/ERPNext document sections remain unchanged.
// iconClass must be a full static lucide-* Tailwind class (JIT requires static strings).
export const SIDEBAR_SECTIONS = [
  {
    key: 'dashboard',
    label: 'Today',
    iconClass: 'lucide-layout-dashboard',
    hash: '#/dashboard',
    visibleRoles: 'all',
  },
  {
    key: 'quotes',
    label: 'Quotations',
    iconClass: 'lucide-file-text',
    hash: '#/quotes',
    visibleRoles: 'all',
  },
  {
    key: 'orders',
    label: 'Sales Orders',
    iconClass: 'lucide-shopping-cart',
    hash: '#/orders',
    visibleRoles: 'all',
  },
  {
    key: 'invoices',
    label: 'Receivables',
    iconClass: 'lucide-receipt',
    hash: '#/invoices',
    visibleRoles: 'all',
  },
  {
    key: 'payments',
    label: 'Payments',
    iconClass: 'lucide-banknote',
    hash: '#/payments',
    visibleRoles: 'all',
  },
  {
    key: 'partner_commission',
    label: 'Accounting ops',
    iconClass: 'lucide-handshake',
    hash: '#/partner-commission',
    visibleRoles: 'all',
  },
  {
    key: 'reports',
    label: 'Reports',
    iconClass: 'lucide-bar-chart-2',
    hash: '#/reports',
    visibleRoles: 'all',
  },
]
