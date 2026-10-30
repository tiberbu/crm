<script setup>
import CxIcon from './components/CxIcon.vue'
import FacilityCard from './components/FacilityCard.vue'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { call, createResource, Dialog } from 'frappe-ui'
import TokenCalculator from '@/components/TokenCalculator.vue'
import FacilitySingleView from './FacilitySingleView.vue'
import OptInRequests from './OptInRequests.vue'
import { compactPackageGridClass, packageGridClass } from '@/utils/cardGrid'
import { partnerName, pricePerToken, summaryLines } from '@/utils/portalPartner'
import { facilityId } from '@/utils/facilityId'
import { tokenBalance, tokenBalanceText } from '@/utils/tokenBalance'
import {
  facilityLabel,
  findOpenOrder,
  invoiceStatus,
  oisForReference,
  packageLabel,
  paymentFailureMessage,
  referenceFromSearch,
  verificationOutcome,
} from '@/utils/portalOrderState'

function __(text, args) {
  let str =
    typeof window !== 'undefined' && typeof window.__ === 'function'
      ? window.__(text)
      : text
  if (args) {
    for (const key of Object.keys(args)) {
      str = str.replace(`:${key}`, args[key])
    }
  }
  return str
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const loading = ref(true)
const errorMessage = ref('')
const context = ref({
  user: '',
  user_info: {},
  ois: [],
  customer_accounts: [],
  token_packages: [],
  calculator_config: {},
})

// Current Active Navigation View: 'dashboard' | 'facilities' | 'pricing' | 'billing' | 'profile'
// The portal lands on the Dashboard — the at-a-glance portfolio story — and
// drills down from there instead of opening on the densest data table.
const activeView = ref('dashboard')
const supportDrawerOpen = ref(false)
const supportFacilityMfl = ref('')

// Sidebar collapsed state for responsive layout
const sidebarCollapsed = ref(false)
const isMobileViewport = ref(false)
const mobileMoreOpen = ref(false)
const mobileMoreItems = computed(() => [
  { view: 'pricing', label: 'Plans & Pricing', icon: 'coins' },
  { view: 'support', label: 'Network Support', icon: 'chat' },
  ...((context.value.ois || []).length
    ? [{ view: 'optin_requests', label: 'Opt-In Requests', icon: 'clipboard-list' }]
    : []),
])

function updateMobileViewport() {
  isMobileViewport.value = window.matchMedia('(max-width: 639px)').matches
}

function selectMobileView(view) {
  if (view === 'support') {
    openNetworkSupportDrawer()
    mobileMoreOpen.value = false
    return
  }
  activeView.value = view
  mobileMoreOpen.value = false
}

// Logout — the framework's /api/method/logout is POST-only, so the old GET
// anchor 403'd and bounced to an unknown route. frappe-ui's resourceFetcher
// issues the POST with the CSRF token (same pattern as session.js / FinanceCockpit).
const logout = createResource({
  url: 'logout',
  onSuccess: () => {
    window.location.href = '/'
  },
  onError: () => {
    notice.value = {
      tone: 'error',
      text: 'Could not sign out. Your session is still active; please try again.',
    }
  },
})

// Top Right User Avatar Dropdown
const isUserMenuOpen = ref(false)
const userMenuRef = ref(null)

// Global search — filters the facility directory; typing from another view
// switches to Facilities so the search never silently does nothing.
const globalSearchRef = ref(null)

const toggleUserMenu = () => {
  isUserMenuOpen.value = !isUserMenuOpen.value
}

function onGlobalSearchInput() {
  if (activeView.value !== 'facilities' && searchQuery.value) {
    activeView.value = 'facilities'
  }
}

function onGlobalKeydown(e) {
  if (e.key === 'Escape' && supportDrawerOpen.value) {
    closeNetworkSupportDrawer()
    return
  }
  if ((e.metaKey || e.ctrlKey) && String(e.key).toLowerCase() === 'k') {
    e.preventDefault()
    globalSearchRef.value?.focus()
    globalSearchRef.value?.select()
  }
}

const navigateTo = (view) => {
  activeView.value = view
  isUserMenuOpen.value = false
}

// User Profile & National ID state
const userProfile = ref({
  user_id: '',
  full_name: '',
  email: '',
  mobile_no: '',
  national_id: '',
  masked_national_id: '',
  national_id_verified: false,
  identification_type: 'National ID',
  hfr_owner_licence: '',
  hfr_registration_number: '',
  organization: '',
  primary_network: '',
  facility_count: 0,
})
const showUnmaskedId = ref(false)
const profileModalOpen = ref(false)
const profileForm = ref({
  national_id: '',
  mobile_no: '',
  full_name: '',
  organization: '',
  identification_type: 'National ID',
})
const profileSaving = ref(false)

// HFR Auto-Discovery by Owner ID
const hfrOwnerSearchBusy = ref(false)
const hfrOwnerSearchResults = ref([])
const hfrOwnerSearchComplete = ref(false)
const hfrOwnerSearchError = ref('')

// Shared facility-name search plus directory filters and grouping state
const searchQuery = ref('')
const selectedStatusFilter = ref('all') // 'all' | 'ready' | 'progress' | 'lead'
const selectedLevelFilter = ref('all') // 'all' | 'Level 2' | 'Level 3' | 'Level 4'
const selectedNetworkFilter = ref('all') // 'all' | network names
const groupByNetwork = ref(false) // Toggle to group facilities by network/partner
const facilityViewMode = ref('table') // 'table' | 'cards'

// Facility selection for Top-Up & Calculator
const selectedFacilityMfl = ref('')
const selectedTopUpPackageCode = ref('')
const topUpMode = ref('all')

// Modals
const topUpModalOpen = ref(false)
const addFacilityModalOpen = ref(false)
const calculatorModalOpen = ref(false)

// M-Pesa Paybill Settlement Modal
const mpesaModalOpen = ref(false)
const mpesaInvoice = ref(null)
const mpesaCodeInput = ref('')
const mpesaPhoneInput = ref('')
const mpesaReportBusy = ref(false)

// HFR Lookup state inside Add Facility Modal
const hfrSearchQuery = ref('')
const hfrSearchBy = ref('mfl_code') // 'mfl_code' | 'facility_fid' | 'registration_number'
const partnerIdInput = ref('')
const hfrSearchBusy = ref(false)
const hfrSearchResults = ref([])
const hfrSearchError = ref('')
const hfrSearchComplete = ref(false)
const hfrLinkBusy = ref(false)

// Action feedback & busy states
const purchaseBusy = ref(false)
const busyId = ref('')
const notice = ref(null)
let noticeTimeout = null
watch(notice, (value) => {
  clearTimeout(noticeTimeout)
  noticeTimeout = null
  if (value && value.tone !== 'pending') {
    noticeTimeout = setTimeout(() => {
      notice.value = null
    }, 5000)
  }
})
const bankTransferOis = ref('')
const copiedMfl = ref('')
const copiedKey = ref('')

// ---------------------------------------------------------------------------
// Unified Data Model (Customer Accounts & OIS)
// ---------------------------------------------------------------------------
const allFacilities = computed(() => {
  const list = []
  const seenMfl = new Set()

  for (const account of context.value.customer_accounts || []) {
    for (const fac of account.facilities || []) {
      const mfl = String(fac.mfl_code || '').trim()
      if (mfl && !seenMfl.has(mfl.toLowerCase())) {
        seenMfl.add(mfl.toLowerCase())
        list.push({
          ...fac,
          facility_name: fac.facility_name || 'Healthcare Facility',
          mfl_code: mfl,
          keph_level: fac.keph_level || 'Level 2 Dispensary',
          network_support: fac.network_support || null,
          network: partnerName(fac.network_support?.display_name || fac.network || account.network),
          membership_status: fac.membership_status || 'Active',
          go_live: Boolean(fac.go_live),
          deal: fac.deal || account.deal || '',
          customer: fac.customer || account.customer || '',
          organization: account.organization || account.customer || '',
          token_package: fac.token_package || '',
          token_package_item_code: fac.token_package_item_code || '',
          token_quantity: Number(fac.token_quantity) || 0,
          token_balance: fac.token_balance || null,
          package_price: fac.package_price,
          package_vat: fac.package_vat,
          package_gross_total: fac.package_gross_total,
          package_currency: fac.package_currency || 'KES',
          recent_purchase: fac.recent_purchase || null,
          invoice_summary: fac.invoice_summary || null,
          source_type: 'customer',
        })
      }
    }
  }

  for (const submission of context.value.ois || []) {
    for (const fac of submission.progress?.facilities || []) {
      const mfl = String(fac.mfl_code || '').trim()
      if (mfl && !seenMfl.has(mfl.toLowerCase())) {
        seenMfl.add(mfl.toLowerCase())
        list.push({
          ...fac,
          facility_name: fac.facility_name || 'Healthcare Facility',
          mfl_code: mfl,
          keph_level: fac.keph_level || 'Level 2 Dispensary',
          network_support: fac.network_support || submission.network || null,
          network: partnerName(submission.network?.display_name || submission.network_slug),
          membership_status: fac.membership_status || 'Active',
          go_live: Boolean(fac.network_contact?.go_live),
          deal: '',
          customer: '',
          ois_name: submission.name,
          organization: submission.facility_signatory_name || submission.name,
          token_package: submission.progress?.package?.display_name || '',
          token_package_item_code: submission.progress?.package?.item_code || '',
          token_quantity: Number(submission.progress?.package?.token_quantity) || 0,
          package_price: submission.progress?.package?.price,
          package_vat: submission.progress?.package?.vat_amount,
          package_gross_total: submission.progress?.package?.gross_total,
          package_currency: submission.progress?.package?.currency || 'KES',
          recent_purchase: null,
          invoice_summary: null,
          source_type: 'ois',
        })
      }
    }
  }

  return list
})

// Available Networks from all registered facilities
const availableNetworks = computed(() => {
  const set = new Set()
  for (const fac of allFacilities.value) {
    if (fac.network) set.add(fac.network)
  }
  return Array.from(set).sort()
})

const availableLevelFilters = computed(() => {
  const levels = new Set()
  for (const facility of allFacilities.value) {
    const level = String(facility.keph_level || '').trim()
    if (!level) continue
    levels.add(level.match(/^Level\s+\d+/i)?.[0] || level)
  }
  return Array.from(levels).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
})

// Filtered facilities for data table and card view
const filteredFacilities = computed(() => {
  return allFacilities.value.filter((fac) => {
    // Search query matching
    const q = searchQuery.value.trim().toLowerCase()
    if (q) {
      const matches = [fac.facility_name, facilityId(fac), fac.mfl_code].some((value) =>
        String(value || '').toLowerCase().includes(q),
      )
      if (!matches) return false
    }

    // Status filter
    if (selectedStatusFilter.value === 'ready' && !fac.go_live) return false
    if (selectedStatusFilter.value === 'progress' && (fac.go_live || fac.membership_status === 'Lead Inquiry')) return false
    if (selectedStatusFilter.value === 'lead' && fac.membership_status !== 'Lead Inquiry') return false

    // Level filter
    if (selectedLevelFilter.value !== 'all') {
      if (!fac.keph_level.toLowerCase().includes(selectedLevelFilter.value.toLowerCase())) {
        return false
      }
    }

    // Network / Partner filter
    if (selectedNetworkFilter.value !== 'all') {
      if (fac.network !== selectedNetworkFilter.value) {
        return false
      }
    }

    return true
  })
})

function facilityReadinessLabel(facility) {
  if (facility.membership_status === 'Lead Inquiry') return 'Lead inquiry'
  return facility.go_live ? 'Ready for go-live' : 'Implementation in progress'
}

function resetFacilityFilters() {
  searchQuery.value = ''
  selectedStatusFilter.value = 'all'
  selectedLevelFilter.value = 'all'
  selectedNetworkFilter.value = 'all'
}

// Facilities grouped by partner network; facilities without one are grouped last.
const NO_PARTNER_GROUP = 'Without a partner'
const facilitiesByNetwork = computed(() => {
  const map = new Map()
  for (const fac of filteredFacilities.value) {
    const net = fac.network || NO_PARTNER_GROUP
    if (!map.has(net)) {
      map.set(net, [])
    }
    map.get(net).push(fac)
  }
  const result = []
  for (const [network, facilities] of map.entries()) {
    result.push({
      network,
      facilities,
      count: facilities.length,
    })
  }
  return result.sort((a, b) => Number(a.network === NO_PARTNER_GROUP) - Number(b.network === NO_PARTNER_GROUP))
})

// User Display Identity for top right avatar
const userDisplayName = computed(() => {
  return (
    userProfile.value.full_name ||
    context.value.user_info?.full_name ||
    context.value.user ||
    'Provider'
  )
})

const userInitials = computed(() => {
  const name = userDisplayName.value.trim()
  if (!name) return 'U'
  const parts = name.split(/\s+/)
  if (parts.length >= 2 && parts[0] && parts[1]) {
    return (parts[0][0] + parts[1][0]).toUpperCase()
  }
  return name.slice(0, 2).toUpperCase()
})

const handleDocumentClick = (e) => {
  if (userMenuRef.value && !userMenuRef.value.contains(e.target)) {
    isUserMenuOpen.value = false
  }
}

// Unified Orders
const allOrders = computed(() => {
  const list = []
  for (const account of context.value.customer_accounts || []) {
    for (const order of account.open_orders || []) {
      list.push({
        ...order,
        source_type: 'customer',
        customer: order.customer || account.customer,
        organization: account.organization || account.customer,
      })
    }
  }
  for (const submission of context.value.ois || []) {
    for (const order of submission.open_orders || []) {
      list.push({
        ...order,
        source_type: 'ois',
        ois_name: submission.name,
        organization: submission.facility_signatory_name || submission.name,
      })
    }
  }
  return list
})

// Unified Invoices
const allInvoices = computed(() => {
  const list = []
  for (const account of context.value.customer_accounts || []) {
    for (const invoice of account.open_invoices || []) {
      list.push({
        ...invoice,
        source_type: 'customer',
        customer: invoice.customer || account.customer,
        organization: account.organization || account.customer,
      })
    }
  }
  for (const submission of context.value.ois || []) {
    for (const invoice of submission.open_invoices || []) {
      list.push({
        ...invoice,
        source_type: 'ois',
        ois_name: submission.name,
        organization: submission.facility_signatory_name || submission.name,
      })
    }
  }
  return list
})

// Unified Payments
const allPayments = computed(() => {
  const list = []
  for (const account of context.value.customer_accounts || []) {
    for (const payment of account.payments || []) {
      list.push({
        ...payment,
        source_type: 'customer',
        customer: payment.customer || account.customer,
        organization: account.organization || account.customer,
      })
    }
  }
  return list
})

function pendingPaymentForInvoice(invoice) {
  if (!invoice?.name) return null
  return allPayments.value.find((payment) => {
    if (payment.status !== 'Pending Verification') return false
    const invoiceNames = payment.invoice_names?.length
      ? payment.invoice_names
      : payment.invoice
        ? [payment.invoice]
        : []
    return invoiceNames.some((name) => String(name) === String(invoice.name))
  }) || null
}

// Selected Facility — never falls back to the first facility; an empty
// selection means "not chosen yet" and the Top Up modal shows a picker.
const selectedFacility = computed(() => {
  if (selectedFacilityMfl.value) {
    const found = allFacilities.value.find(
      (f) => String(f.mfl_code).toLowerCase() === String(selectedFacilityMfl.value).toLowerCase(),
    )
    if (found) return found
  }
  return null
})

// Facility detail drawer — the single surface that ties all of one facility's
// records together (identity, capacity, invoices, orders, opt-in origin)
const facilityDrawerMfl = ref('')
const drawerFacility = computed(
  () => allFacilities.value.find((f) => String(f.mfl_code) === String(facilityDrawerMfl.value)) || null,
)
const supportDrawerFacility = computed(
  () => allFacilities.value.find((f) => String(f.mfl_code) === String(supportFacilityMfl.value)) || null,
)
const primaryNetworkName = computed(() =>
  allFacilities.value.find((facility) => facility.network)?.network || partnerName(userProfile.value.primary_network),
)
const networkSupportGroups = computed(() => {
  const groups = new Map()
  for (const facility of allFacilities.value) {
    const details = facility.network_support || {}
    const name = details.display_name || facility.network || 'CareVerse Partner Network'
    const key = details.name || details.slug || name
    const group = groups.get(key) || {
      key,
      name,
      partnerId: details.partner_id || '',
      contactEmail: details.contact_email || '',
      deliveryPartner: details.technology_delivery_partner_name || '',
      deliveryPartnerShortName: details.technology_delivery_partner_short_name || '',
      coordinators: Array.isArray(details.coordinators) ? details.coordinators : [],
      facilities: [],
    }
    if (!group.facilities.includes(facility.facility_name)) group.facilities.push(facility.facility_name)
    groups.set(key, group)
  }
  const currentKey = supportDrawerFacility.value?.network_support?.name || supportDrawerFacility.value?.network
  return Array.from(groups.values()).sort((a, b) => Number(b.key === currentKey) - Number(a.key === currentKey))
})

function openNetworkSupportDrawer(facility = null) {
  const target = facility || (activeView.value === 'facility_detail' ? drawerFacility.value : null)
  supportFacilityMfl.value = target?.mfl_code || ''
  supportDrawerOpen.value = true
  mobileMoreOpen.value = false
}

function closeNetworkSupportDrawer() {
  supportDrawerOpen.value = false
}

const drawerInvoices = computed(() => {
  if (drawerFacility.value?.invoices) return drawerFacility.value.invoices
  const mfl = String(drawerFacility.value?.mfl_code || '').toLowerCase()
  return allInvoices.value.filter((inv) => String(inv.crm_token_facility_mfl || '').toLowerCase() === mfl)
})
const drawerOrders = computed(() => {
  const mfl = String(drawerFacility.value?.mfl_code || '').toLowerCase()
  return allOrders.value.filter((o) => String(o.crm_token_facility_mfl || '').toLowerCase() === mfl)
})
const drawerPayments = computed(() => {
  const invoiceNames = new Set(drawerInvoices.value.map((invoice) => String(invoice.name)))
  return allPayments.value.filter((payment) => {
    const names = payment.invoice_names?.length
      ? payment.invoice_names
      : payment.invoice
        ? [payment.invoice]
        : []
    return names.some((name) => invoiceNames.has(String(name)))
  })
})
function invoiceForFacility(facility) {
  const invoiceName = facility.invoice_summary?.invoice_name
  return allInvoices.value.find((invoice) => invoice.name === invoiceName) || allInvoices.value.find(
    (invoice) => String(invoice.crm_token_facility_mfl || '').toLowerCase() === String(facility.mfl_code || '').toLowerCase(),
  ) || null
}
function pendingPaymentForFacility(facility) {
  const invoice = invoiceForFacility(facility)
  return invoice ? pendingPaymentForInvoice(invoice) : null
}
function openFacilityDrawer(facility) {
  facilityDrawerMfl.value = facility.mfl_code
  activeView.value = 'facility_detail'
}
function openFacilityFromSurface(event, facility) {
  if (event.target?.closest?.('button, a, input, select, textarea, [role="button"]')) return
  openFacilityDrawer(facility)
}
function openAttentionFacility(item) {
  const facility = allFacilities.value.find(
    (row) => String(row.mfl_code || '').toLowerCase() === String(item.mfl_code || '').toLowerCase(),
  )
  if (facility) openFacilityDrawer(facility)
}
function closeFacilityDrawer() {
  facilityDrawerMfl.value = ''
  activeView.value = 'facilities'
}

async function ensureProvisioningDraft(mflCode) {
  const response = await call('crm.api.hfr.ensure_provisioning_draft', { mfl_code: mflCode })
  return unwrap(response)
}

// Read-only status refresh used for polling. The endpoint only accepts GET, and
// frappe-ui `call` always POSTs.
async function getProvisioningStatus(mflCode) {
  const query = new URLSearchParams({ mfl_code: mflCode })
  const res = await fetch(`/api/method/crm.api.hfr.get_provisioning_status?${query}`, {
    headers: { Accept: 'application/json', 'X-Frappe-Site-Name': window.location.hostname },
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(body?._error_message || body?.exception || 'Status refresh failed.')
  return unwrap(body.message)
}

// Selected Package
const selectedPackageObj = computed(() => {
  return (
    context.value.token_packages?.find(
      (p) => p.item_code === selectedTopUpPackageCode.value,
    ) || context.value.token_packages?.[1] || null
  )
})

// Executive KPIs
const facilityCount = computed(() => allFacilities.value.length)

// Live OpenMeter balance only: a package's tokens count once its invoice is paid and granted.
function availableTokens(facility) {
  const live = facility?.token_balance
  if (live?.status === 'ok') return Number(live.balance) || 0
  return 0
}

const anyBalanceKnown = computed(() => allFacilities.value.some((fac) => tokenBalance(fac).known))
const totalTokenCount = computed(() =>
  allFacilities.value.reduce((sum, fac) => sum + availableTokens(fac), 0),
)
const liveFacilitiesCount = computed(
  () => allFacilities.value.filter((f) => f.go_live).length,
)
const openInvoiceCount = computed(() => allInvoices.value.length)
const totalOutstandingAmount = computed(() =>
  allInvoices.value.reduce((sum, inv) => sum + (Number(inv.amount) || 0), 0),
)
const primaryOrganizationName = computed(() => {
  return (
    context.value.customer_accounts?.[0]?.organization ||
    context.value.customer_accounts?.[0]?.customer ||
    context.value.ois?.[0]?.facility_signatory_name ||
    context.value.user ||
    'Healthcare Enterprise'
  )
})

// Dashboard: actionable invoice items. Registry verification is not a customer action.
const dashboardAttention = computed(() => {
  const items = []
  for (const inv of allInvoices.value) {
    const facilityMfl = String(inv.crm_token_facility_mfl || '').trim()
    const facility = allFacilities.value.find(
      (item) => String(item.mfl_code || '').trim().toLowerCase() === facilityMfl.toLowerCase(),
    )
    const status = invoiceStatus(inv)
    items.push({
      key: `inv-${inv.name}`,
      icon: 'credit-card',
      text: `Invoice ${inv.invoice_number || inv.name} — ${money(inv.amount, inv.currency)} ${status.key === 'overdue' ? 'overdue' : 'due'}`,
      meta: `Facility: ${facility?.facility_name || facilityLabel(inv.crm_token_facility_mfl, allFacilities.value)}`,
      mfl_code: facility?.mfl_code || '',
    })
  }
  return items
})

// Dashboard: unified activity stream (orders + payments), newest first
const recentActivity = computed(() => {
  const items = []
  for (const pay of allPayments.value) {
    if (!pay.posting_date) continue
    items.push({
      kind: 'payment',
      icon: 'receipt',
      title: pay.status === 'Pending Verification' ? 'M-Pesa report' : 'Payment recorded',
      text: `${pay.mode_of_payment || 'Payment'} · ${money(pay.amount, 'KES')}${pay.status === 'Pending Verification' ? ' · Verification pending' : ''}`,
      date: pay.posting_date,
    })
  }
  for (const order of allOrders.value) {
    if (!order.transaction_date) continue
    items.push({
      kind: 'order',
      icon: 'coins',
      title: packageLabel(order.crm_token_package_item, context.value.token_packages || []),
      text: `Order ${order.name} · ${money(order.grand_total, order.currency)}`,
      date: order.transaction_date,
    })
  }
  return items
    .sort((a, b) => String(b.date).localeCompare(String(a.date)))
    .slice(0, 8)
})

// Opt-in requests as first-class records: status, facilities, package,
// open financials, and quotations attached to each submission
const optinRequests = computed(() => {
  return (context.value.ois || []).map((ois) => {
    let quotes = []
    try {
      const parsed = JSON.parse(ois.quote_names_json || '[]')
      if (Array.isArray(parsed)) quotes = parsed
    } catch {
      quotes = ois.quote_names_json ? [String(ois.quote_names_json)] : []
    }
    return {
      name: ois.name,
      status: ois.status || 'Submitted',
      network: partnerName(ois.network || ois.network_slug) || 'Self-onboarding',
      signatory: ois.facility_signatory_name || '',
      source: ois.onboarding_source || '',
      contract: ois.contract || '',
      facilities: (ois.progress?.facilities || []).map((f) => ({
        name: f.facility_name,
        mfl_code: f.mfl_code,
        facility_id: facilityId(f),
      })),
      package: ois.progress?.package || null,
      open_orders: (ois.open_orders || []).length,
      open_invoices: (ois.open_invoices || []).length,
      quotes,
    }
  })
})

const defaultCurrency = computed(() => {
  return (
    allInvoices.value[0]?.currency ||
    context.value.token_packages?.[0]?.currency ||
    'KES'
  )
})

// ---------------------------------------------------------------------------
// Actions & Handlers
// ---------------------------------------------------------------------------
async function copyMfl(code) {
  if (!await copyText(code, `mfl-${code}`)) return
  copiedMfl.value = code
  setTimeout(() => {
    if (copiedMfl.value === code) copiedMfl.value = ''
  }, 2000)
}

async function copyText(text, key) {
  if (text === undefined || text === null || text === '') {
    notice.value = { tone: 'error', text: 'This value is not available to copy.' }
    return false
  }
  try {
    if (typeof navigator === 'undefined' || !navigator.clipboard?.writeText) {
      throw new Error('Clipboard access is unavailable.')
    }
    await navigator.clipboard.writeText(String(text))
    copiedKey.value = key
    setTimeout(() => {
      if (copiedKey.value === key) copiedKey.value = ''
    }, 2000)
    return true
  } catch {
    notice.value = { tone: 'error', text: 'Could not copy this value. Select and copy it manually.' }
    return false
  }
}

const paybillInfo = computed(() => context.value.paybill_info || {})

async function loadUserProfile() {
  try {
    const res = await call('crm.api.customer_experience.get_user_profile')
    const data = unwrap(res)
    if (data && data.email) {
      userProfile.value = {
        ...userProfile.value,
        ...data,
      }
      profileForm.value = {
        national_id: data.national_id || '',
        mobile_no: data.mobile_no || '',
        full_name: data.full_name || '',
        organization: data.organization || '',
        identification_type: data.identification_type || 'National ID',
      }
    }
  } catch (error) {
    console.error('Failed to load user profile', error)
  }
}

function openEditProfileModal() {
  profileForm.value = {
    national_id: userProfile.value.national_id || '',
    mobile_no: userProfile.value.mobile_no || '',
    full_name: userProfile.value.full_name || '',
    organization: userProfile.value.organization || '',
    identification_type: userProfile.value.identification_type || 'National ID',
  }
  profileModalOpen.value = true
}

async function saveUserProfile() {
  profileSaving.value = true
  notice.value = null
  try {
    const res = await call('crm.api.customer_experience.update_user_profile', {
      national_id: profileForm.value.national_id,
      mobile_no: profileForm.value.mobile_no,
      full_name: profileForm.value.full_name,
      organization: profileForm.value.organization,
      identification_type: profileForm.value.identification_type,
    })
    const data = unwrap(res)
    if (data) {
      userProfile.value = {
        ...userProfile.value,
        ...data,
      }
      profileModalOpen.value = false
      await loadContext()
      notice.value = {
        tone: 'success',
        text: 'Profile and account details updated successfully!',
      }
    }
  } catch (error) {
    notice.value = {
      tone: 'error',
      text: error?.messages?.[0] || 'Could not update profile.',
    }
  } finally {
    profileSaving.value = false
  }
}

async function discoverFacilitiesByOwnerId() {
  hfrOwnerSearchBusy.value = true
  hfrOwnerSearchComplete.value = false
  hfrOwnerSearchError.value = ''
  hfrOwnerSearchResults.value = []
  notice.value = null
  try {
    const res = await call('crm.api.customer_experience.lookup_facilities_by_owner_id', {
      national_id: userProfile.value.national_id || undefined,
    })
    const data = unwrap(res)
    hfrOwnerSearchResults.value = Array.isArray(data) ? data : []
    hfrOwnerSearchComplete.value = true
    if (res?.masked_national_id && !userProfile.value.masked_national_id) {
      userProfile.value.masked_national_id = res.masked_national_id
      userProfile.value.national_id = res.national_id
    }
    if (!hfrOwnerSearchResults.value.length) {
      notice.value = {
        tone: 'pending',
        text: 'No additional facilities registered under this National ID in the Health Facility Registry.',
      }
    }
  } catch (error) {
    hfrOwnerSearchComplete.value = true
    hfrOwnerSearchError.value = error?.messages?.[0] || 'Unable to discover facilities by National ID.'
    notice.value = {
      tone: 'error',
      text: hfrOwnerSearchError.value,
    }
  } finally {
    hfrOwnerSearchBusy.value = false
  }
}

function packageIsFree(pkg) {
  const amount = Number(pkg?.price_ex_vat ?? pkg?.price ?? pkg?.gross_total)
  return Number.isFinite(amount) && amount <= 0
}

function packageIsPaid(pkg) {
  const amount = Number(pkg?.price_ex_vat ?? pkg?.price ?? pkg?.gross_total)
  return Number.isFinite(amount) && amount > 0
}

const freeTokenPackages = computed(() => (context.value.token_packages || []).filter((pkg) => packageIsFree(pkg)))
const paidTokenPackages = computed(() => (context.value.token_packages || []).filter((pkg) => packageIsPaid(pkg)))
const visibleTopUpPackages = computed(() => topUpMode.value === 'free'
  ? freeTokenPackages.value
  : topUpMode.value === 'paid'
    ? paidTokenPackages.value
    : context.value.token_packages || [])
const topUpModalTitle = computed(() => topUpMode.value === 'free'
  ? __('Choose Free Go-live Tokens')
  : topUpMode.value === 'paid'
    ? __('Buy Care Tokens')
    : __('Top Up Care Tokens'))

function openTopUpModal(facility = null, mode = 'all') {
  if (facility) {
    selectedFacilityMfl.value = facility.mfl_code
  } else if (allFacilities.value.length === 1) {
    selectedFacilityMfl.value = allFacilities.value[0].mfl_code
  } else if (!selectedFacilityMfl.value) {
    // Multiple facilities: user must explicitly pick one (PRD REQ-ARC-02)
    selectedFacilityMfl.value = ''
  }
  topUpMode.value = mode
  if (!visibleTopUpPackages.value.length) {
    notice.value = {
      tone: 'error',
      text: mode === 'free' ? 'No free token package is available right now. Contact Network Support.' : 'No paid token packages are available right now. Contact Network Support.',
    }
    return
  }
  if (!visibleTopUpPackages.value.some((pkg) => pkg.item_code === selectedTopUpPackageCode.value)) {
    selectedTopUpPackageCode.value = visibleTopUpPackages.value[0].item_code
  }
  topUpModalOpen.value = true
}

function openAddFacilityModal() {
  activeView.value = 'facilities'
  notice.value = null
  hfrSearchQuery.value = ''
  hfrSearchResults.value = []
  hfrSearchError.value = ''
  hfrSearchComplete.value = false
  partnerIdInput.value = ''
  hfrOwnerSearchResults.value = []
  hfrOwnerSearchComplete.value = false
  hfrOwnerSearchError.value = ''
  addFacilityModalOpen.value = true
}

function openCalculatorModal(facility = null) {
  if (facility) {
    selectedFacilityMfl.value = facility.mfl_code
  }
  calculatorModalOpen.value = true
}

function facilityAlreadyLinked(candidate) {
  const candidateMfl = String(candidate?.mfl_code || '').trim().toLowerCase()
  return Boolean(candidateMfl && allFacilities.value.some((facility) => String(facility.mfl_code || '').trim().toLowerCase() === candidateMfl))
}

function onCalculatorApplyPlan(pkg) {
  calculatorModalOpen.value = false
  selectedTopUpPackageCode.value = pkg.item_code
  openTopUpModal(selectedFacility.value)
}

function selectPlanFromPricingTab(pkg) {
  selectedTopUpPackageCode.value = pkg.item_code
  openTopUpModal(selectedFacility.value)
}

function openMpesaModal(invoice) {
  if (pendingPaymentForInvoice(invoice)) {
    notice.value = {
      tone: 'pending',
      text: 'An M-Pesa payment report is being verified for this invoice. Please wait before starting another payment.',
    }
    return
  }
  mpesaInvoice.value = invoice
  mpesaCodeInput.value = ''
  mpesaPhoneInput.value = userProfile.value.mobile_no || ''
  mpesaModalOpen.value = true
}

function openMpesaModalForFacility(facility) {
  const invName = facility.invoice_summary?.invoice_name
  let inv = invoiceForFacility(facility)
  if (!inv) {
    inv = {
      name: invName || `INV-${facility.mfl_code}`,
      amount: facility.invoice_summary?.outstanding_amount || 0,
      outstanding_amount: facility.invoice_summary?.outstanding_amount || 0,
      currency: facility.invoice_summary?.currency || 'KES',
      customer: facility.customer,
    }
  }
  openMpesaModal(inv)
}

async function submitMpesaPayment() {
  if (!mpesaInvoice.value) return
  const code = mpesaCodeInput.value.trim().toUpperCase()
  if (!code || code.length < 6) {
    notice.value = {
      tone: 'error',
      text: 'Please enter a valid M-Pesa transaction confirmation code (e.g. SB65A1TU7X).',
    }
    return
  }

  mpesaReportBusy.value = true
  notice.value = null
  try {
    const res = await call('crm.api.customer_experience.report_mpesa_payment', {
      invoice_name: mpesaInvoice.value.name,
      mpesa_code: code,
      amount: mpesaInvoice.value.amount || mpesaInvoice.value.outstanding_amount,
      phone: mpesaPhoneInput.value.trim(),
    })
    const data = unwrap(res)
    const alreadyPending = data?.status === 'payment_already_pending'
    mpesaModalOpen.value = false
    notice.value = {
      tone: alreadyPending ? 'pending' : 'success',
      text: data?.message || `M-Pesa payment ${code} recorded successfully. Your invoice will update after verification.`,
    }
    await refreshContext()
  } catch (error) {
    notice.value = {
      tone: 'error',
      text: error?.messages?.[0] || 'Could not record M-Pesa payment. Please verify the confirmation code.',
    }
  } finally {
    mpesaReportBusy.value = false
  }
}

// Currency codes ("KES 6,000"), matching the package catalogue and onboarding.
function money(value, currency, fractionDigits = 0) {
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: currency || defaultCurrency.value || 'KES',
    currencyDisplay: 'code',
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value || 0)
}

function isFreePackage(pkg) {
  return Number(pkg?.price_ex_vat ?? pkg?.price ?? 0) === 0
}

// `call` already returns the server's `message`. Some payloads (provisioning
// status) carry their own human-readable `message` string, which is not data.
function unwrap(response) {
  return (
    response?.message?.data ||
    response?.data ||
    (response?.message && typeof response.message === 'object' ? response.message : null) ||
    response ||
    {}
  )
}

async function refreshContext() {
  const refreshed = await call('crm.api.website_redirect.get_portal_context')
  context.value = unwrap(refreshed) || context.value
  if (!selectedFacilityMfl.value && allFacilities.value.length === 1) {
    selectedFacilityMfl.value = allFacilities.value[0].mfl_code
  }
}

// Search HFR API for new facility
async function executeHfrSearch() {
  const query = hfrSearchQuery.value.trim()
  if (!query) return

  hfrSearchBusy.value = true
  hfrSearchResults.value = []
  hfrSearchError.value = ''
  hfrSearchComplete.value = false

  try {
    const res = await call('crm.api.customer_experience.lookup_hfr_facility', {
      query,
      search_by: hfrSearchBy.value,
    })
    const data = unwrap(res)
    hfrSearchResults.value = Array.isArray(data) ? data : []
    hfrSearchComplete.value = true
    if (!hfrSearchResults.value.length) {
      notice.value = {
        tone: 'pending',
        text: `No Health Facility Registry records matched query "${query}". Try searching by the facility's 5-digit MFL code.`,
      }
    }
  } catch (error) {
    hfrSearchError.value = error?.messages?.[0] || 'Unable to connect to the Health Facility Registry. Please try again.'
    hfrSearchComplete.value = true
    notice.value = {
      tone: 'error',
      text: hfrSearchError.value,
    }
  } finally {
    hfrSearchBusy.value = false
  }
}

// Link verified HFR facility to account
async function linkHfrCandidate(candidate) {
  hfrLinkBusy.value = true
  notice.value = null

  try {
    const res = await call('crm.api.customer_experience.add_facility_from_hfr', {
      mfl_code: candidate.mfl_code,
      fid: candidate.facility_fid || candidate.fid,
      partner_id: partnerIdInput.value.trim(),
    })
    const payload = unwrap(res)

    addFacilityModalOpen.value = false
    notice.value = {
      tone: 'success',
      text: `Facility "${payload.facility_name}" (${facilityId(payload) || facilityId(candidate) ? `Facility ID ${facilityId(payload) || facilityId(candidate)} · ` : ''}MFL ${payload.mfl_code}) was linked to your enterprise account successfully!`,
    }

    await refreshContext()
    activeView.value = 'facilities'
  } catch (error) {
    notice.value = {
      tone: 'error',
      text: error?.messages?.[0] || 'Could not link facility. Please try again.',
    }
  } finally {
    hfrLinkBusy.value = false
  }
}

// Order tokens
async function executeTopUp() {
  if (!selectedFacility.value) {
    notice.value = {
      tone: 'error',
      text: 'Please select a facility to receive this token package.',
    }
    return
  }

  purchaseBusy.value = true
  notice.value = null

  try {
    const params = {
      facility_mfl: selectedFacility.value.mfl_code,
      package_item_code: selectedPackageObj.value.item_code,
    }
    if (selectedFacility.value.customer) {
      params.customer = selectedFacility.value.customer
    } else if (selectedFacility.value.ois_name) {
      params.ois_number = selectedFacility.value.ois_name
    }

    const payload = unwrap(
      await call('crm.api.customer_experience.create_token_order', params),
    )

    topUpModalOpen.value = false
    notice.value = {
      tone: 'success',
      text: `Order ${payload.sales_order || ''} created for ${selectedFacility.value.facility_name}. Check Billing & Invoices for any amount due.`,
    }

    await refreshContext()
    activeView.value = 'billing'
  } catch (error) {
    notice.value = {
      tone: 'error',
      text: error?.messages?.[0] || 'We could not create the token order.',
    }
  } finally {
    purchaseBusy.value = false
  }
}

async function createInvoice(order) {
  busyId.value = order.name
  notice.value = null
  try {
    await call('crm.api.customer_experience.start_token_payment', {
      sales_order: order.name,
    })
    await refreshContext()
    notice.value = {
      tone: 'success',
      text: `Invoice created! You can now complete checkout via M-Pesa or Card.`,
    }
  } catch (error) {
    notice.value = {
      tone: 'error',
      text: error?.messages?.[0] || 'Could not create invoice for this order.',
    }
  } finally {
    busyId.value = ''
  }
}

// Draft order review: billing address, KRA PIN and frequency before the invoice is raised.
const draftOrders = computed(() => allOrders.value.filter((order) => order.is_draft))
const orderReviewOpen = ref(false)
const orderReview = ref(null)
const orderReviewBusy = ref(false)
const orderReviewError = ref('')
const reviewForm = ref(emptyReviewForm())
const KRA_PIN_PATTERN = /^[A-Z]\d{9}[A-Z]$/

function emptyReviewForm() {
  return {
    billing_address: '',
    address_line1: '',
    address_line2: '',
    city: '',
    county: '',
    postal_code: '',
    kra_pin: '',
    frequency: 'One-time',
    recurrence_period: 'Monthly',
  }
}

const reviewBonusTokens = computed(() =>
  (orderReview.value?.items || []).reduce((sum, row) => sum + (Number(row.bonus_tokens) || 0), 0),
)
const reviewKraPin = computed(() => reviewForm.value.kra_pin.replace(/\s+/g, '').toUpperCase())
const reviewProblems = computed(() => {
  const form = reviewForm.value
  const problems = []
  if (!KRA_PIN_PATTERN.test(reviewKraPin.value)) problems.push('Enter a valid KRA PIN, for example A123456789Z.')
  if (!form.billing_address && !(form.address_line1.trim() && form.city.trim())) {
    problems.push('Choose a saved billing address, or enter the street address and town.')
  }
  return problems
})

async function openOrderReview(order) {
  orderReview.value = null
  orderReviewError.value = ''
  reviewForm.value = emptyReviewForm()
  orderReviewOpen.value = true
  try {
    const data = unwrap(
      await call('crm.api.customer_experience.get_draft_order', { sales_order: order.name }),
    )
    orderReview.value = data
    reviewForm.value.kra_pin = data.kra_pin || ''
    reviewForm.value.billing_address = data.billing_address || data.addresses?.[0]?.name || ''
    reviewForm.value.frequency = data.frequency || 'One-time'
    reviewForm.value.recurrence_period = data.recurrence_period || 'Monthly'
  } catch (error) {
    orderReviewError.value = error?.messages?.[0] || 'We could not load this order.'
  }
}

async function confirmOrderReview() {
  if (!orderReview.value || reviewProblems.value.length) return
  const form = reviewForm.value
  orderReviewBusy.value = true
  orderReviewError.value = ''
  try {
    const params = {
      sales_order: orderReview.value.name,
      kra_pin: reviewKraPin.value,
      frequency: form.frequency,
      recurrence_period: form.frequency === 'Recurring' ? form.recurrence_period : '',
    }
    if (form.billing_address) {
      params.billing_address = form.billing_address
    } else {
      params.new_address = JSON.stringify({
        address_line1: form.address_line1,
        address_line2: form.address_line2,
        city: form.city,
        county: form.county,
        postal_code: form.postal_code,
      })
    }
    const data = unwrap(await call('crm.api.customer_experience.confirm_draft_order', params))
    orderReviewOpen.value = false
    await refreshContext()
    // Reviewed from a facility page: stay there, where the new invoice shows with its payment button.
    if (activeView.value !== 'facility_detail') activeView.value = 'billing'
    notice.value = {
      tone: 'success',
      text: `Order ${data.sales_order} confirmed and invoice ${data.invoice} generated. Pay it below; your tokens are added once payment is received.`,
    }
  } catch (error) {
    orderReviewError.value = error?.messages?.[0] || 'We could not confirm this order.'
  } finally {
    orderReviewBusy.value = false
  }
}

async function payInvoice(invoice) {
  if (pendingPaymentForInvoice(invoice)) {
    notice.value = {
      tone: 'pending',
      text: 'An M-Pesa payment report is being verified for this invoice. Please wait before starting another payment.',
    }
    return
  }
  busyId.value = invoice.name
  notice.value = null
  try {
    const params = { invoice: invoice.name }
    if (invoice.ois_name) {
      params.ois_number = invoice.ois_name
    } else if (invoice.customer) {
      params.customer = invoice.customer
    }

    const data = unwrap(
      await call('crm.api.checkout.initialize_portal_paystack_payment', params),
    )

    if (data.authorization_url) {
      window.location.href = data.authorization_url
      return
    }
    notice.value = { tone: 'error', text: 'Payment checkout could not be started.' }
  } catch (error) {
    const failure = paymentFailureMessage(error)
    notice.value = { tone: 'error', text: failure.message }
  } finally {
    busyId.value = ''
  }
}

async function verifyReturnedPayment() {
  const reference = referenceFromSearch(window.location.search)
  if (!reference) return
  window.history.replaceState({}, '', window.location.pathname)

  const oisName = oisForReference(
    reference,
    (context.value.ois || []).map((item) => item.name),
  )

  try {
    const params = { reference }
    if (oisName) params.ois_number = oisName

    const result = unwrap(
      await call('crm.api.checkout.verify_portal_paystack_payment', params),
    )
    notice.value = verificationOutcome(result)
    if (result.paid) await refreshContext()
  } catch (error) {
    notice.value = {
      tone: 'error',
      text: error?.messages?.[0] || 'We could not confirm the payment yet.',
    }
  }
}

async function retryLoad() {
  loading.value = true
  errorMessage.value = ''
  try {
    await refreshContext()
    await loadUserProfile()
    await verifyReturnedPayment()
  } catch (error) {
    errorMessage.value = error?.messages?.[0] || 'Failed to load portal.'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  updateMobileViewport()
  window.addEventListener('resize', updateMobileViewport, { passive: true })
  if (typeof document !== 'undefined') {
    document.addEventListener('click', handleDocumentClick)
    document.addEventListener('keydown', onGlobalKeydown)
  }
  await retryLoad()
  loadTokenAlerts()
})

// The owner's low-token email alerts, keyed by MFL code. Optional: the portal works without them.
const tokenAlerts = ref({})
async function loadTokenAlerts() {
  try {
    const response = await call('crm.api.token_alerts.get_token_alerts')
    tokenAlerts.value = response?.alerts || {}
  } catch {
    tokenAlerts.value = {}
  }
}
function onTokenAlertSaved(alert) {
  tokenAlerts.value = { ...tokenAlerts.value, [alert.mfl_code]: alert }
}

onUnmounted(() => {
  window.removeEventListener('resize', updateMobileViewport)
  clearTimeout(noticeTimeout)
  if (typeof document !== 'undefined') {
    document.removeEventListener('click', handleDocumentClick)
    document.removeEventListener('keydown', onGlobalKeydown)
  }
})
</script>

<template>
  <div class="cx-portal min-h-screen bg-cx-bg text-cx-ink flex flex-col antialiased">
    <!-- Notice Toast Bar -->
    <div
      v-if="notice"
      class="cx-toast border px-4 py-2.5 text-xs font-semibold flex items-center justify-between z-50"
      :class="{
        'bg-cx-success-soft text-cx-success-ink border-cx-success-border': notice.tone === 'success',
        'bg-cx-warning-soft text-cx-warning-ink border-cx-warning-border': notice.tone === 'pending',
        'bg-cx-danger-soft text-rose-900 border-cx-danger-border': notice.tone === 'error',
      }"
    >
      <div class="flex items-center gap-2 max-w-5xl mx-auto w-full">
        <CxIcon v-if="notice.tone === 'success'" name="check-circle" class="size-4 shrink-0" />
        <CxIcon v-else :name="notice.tone === 'pending' ? 'clock' : 'alert'" class="size-4 shrink-0" />
        <span>{{ notice.text }}</span>
      </div>
      <button type="button" class="underline ml-4 shrink-0" @click="notice = null">Dismiss</button>
    </div>

    <div class="flex-1 flex overflow-hidden">
      <!-- 1. PERSISTENT COLLAPSIBLE SIDEBAR (Exact SaaS Pattern from Screenshot) -->
      <aside
        class="cx-glass-chrome hidden md:flex bg-cx-surface border-r border-cx-border flex-col shrink-0 transition-all duration-200 select-none z-30"
        :class="sidebarCollapsed ? 'w-16' : 'w-64'"
      >
        <!-- Brand Header -->
        <div class="h-16 border-b border-cx-border flex items-center justify-between px-4">
          <div class="flex items-center gap-2.5 overflow-hidden" v-if="!sidebarCollapsed">
            <div class="size-8 rounded-cx-sm bg-cx-brand text-cx-contrast flex items-center justify-center font-semibold text-sm shadow-cx shrink-0">
              T
            </div>
            <div class="truncate">
              <span class="font-bold text-sm tracking-tight text-cx-ink block leading-tight">
                Tiberbu <span class="text-cx-brand">CareVerse</span>
              </span>
              <span class="text-[11px] font-semibold text-cx-ink-3 uppercase tracking-[0.08em] block">
                HMIS Enterprise
              </span>
            </div>
          </div>
          <div v-else class="mx-auto">
            <div class="size-8 rounded-cx-sm bg-cx-brand text-cx-contrast flex items-center justify-center font-semibold text-sm shadow-cx">
              T
            </div>
          </div>

          <button
            type="button"
            class="text-cx-ink-3 hover:text-cx-ink p-1 rounded-cx-sm hover:bg-cx-well transition hidden sm:inline-block"
            :title="sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'"
            @click="sidebarCollapsed = !sidebarCollapsed"
          >
            <svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path v-if="!sidebarCollapsed" stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
              <path v-else stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
            </svg>
          </button>
        </div>

        <!-- Navigation Menu Items -->
        <nav class="flex-1 py-4 px-2 space-y-1 overflow-y-auto">
          <!-- 1. Dashboard -->
          <button
            type="button"
            class="w-full flex items-center gap-3 px-3 py-2.5 rounded-cx-sm text-xs font-semibold transition text-left"
            :class="
              activeView === 'dashboard'
                ? 'bg-cx-brand-soft text-cx-brand-ink shadow-cx'
                : 'text-cx-ink-3 hover:bg-cx-well hover:text-cx-ink'
            "
            @click="activeView = 'dashboard'"
          >
            <span class="text-base shrink-0"><CxIcon name="dashboard" class="inline-block size-4 align-[-0.15em]" /></span>
            <span v-if="!sidebarCollapsed" class="truncate">Dashboard</span>
          </button>

          <!-- 2. Facilities (Active in Screenshot) -->
          <button
            type="button"
            class="w-full flex items-center justify-between px-3 py-2.5 rounded-cx-sm text-xs font-semibold transition text-left"
            :class="
              activeView === 'facilities' || activeView === 'facility_detail'
                ? 'bg-cx-brand-soft text-cx-brand-ink shadow-cx'
                : 'text-cx-ink-3 hover:bg-cx-well hover:text-cx-ink'
            "
            @click="activeView = 'facilities'"
          >
            <div class="flex items-center gap-3 truncate">
              <span class="text-base shrink-0"><CxIcon name="hospital" class="inline-block size-4 align-[-0.15em]" /></span>
              <span v-if="!sidebarCollapsed" class="truncate">Facilities</span>
            </div>
            <span
              v-if="!sidebarCollapsed"
              class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
              :class="activeView === 'facilities' ? 'bg-cx-brand-soft text-cx-brand-ink' : 'bg-cx-well text-cx-ink-3'"
            >
              {{ facilityCount }}
            </span>
          </button>

          <!-- 3. Plans & Pricing (GitHub Style) -->
          <button
            type="button"
            class="w-full flex items-center gap-3 px-3 py-2.5 rounded-cx-sm text-xs font-semibold transition text-left"
            :class="
              activeView === 'pricing'
                ? 'bg-cx-brand-soft text-cx-brand-ink shadow-cx'
                : 'text-cx-ink-3 hover:bg-cx-well hover:text-cx-ink'
            "
            @click="activeView = 'pricing'"
          >
            <span class="text-base shrink-0"><CxIcon name="coins" class="inline-block size-4 align-[-0.15em]" /></span>
            <span v-if="!sidebarCollapsed" class="truncate">Plans & Pricing</span>
          </button>

          <!-- 4. Billing & Invoices -->
          <button
            type="button"
            class="w-full flex items-center justify-between px-3 py-2.5 rounded-cx-sm text-xs font-semibold transition text-left"
            :class="
              activeView === 'billing'
                ? 'bg-cx-brand-soft text-cx-brand-ink shadow-cx'
                : 'text-cx-ink-3 hover:bg-cx-well hover:text-cx-ink'
            "
            @click="activeView = 'billing'"
          >
            <div class="flex items-center gap-3 truncate">
              <span class="text-base shrink-0"><CxIcon name="credit-card" class="inline-block size-4 align-[-0.15em]" /></span>
              <span v-if="!sidebarCollapsed" class="truncate">Billing & Invoices</span>
            </div>
            <span
              v-if="!sidebarCollapsed && openInvoiceCount > 0"
              class="rounded-full bg-cx-warning-soft text-cx-warning-ink px-2 py-0.5 text-[11px] font-semibold"
            >
              {{ openInvoiceCount }}
            </span>
          </button>

          <!-- 4b. Opt-In Requests (only when the user has submissions) -->
          <button
            v-if="(context.ois || []).length"
            type="button"
            class="w-full flex items-center justify-between px-3 py-2.5 rounded-cx-sm text-xs font-semibold transition text-left"
            :class="
              activeView === 'optin_requests'
                ? 'bg-cx-brand-soft text-cx-brand-ink shadow-cx'
                : 'text-cx-ink-3 hover:bg-cx-well hover:text-cx-ink'
            "
            @click="activeView = 'optin_requests'"
          >
            <div class="flex items-center gap-3 truncate">
              <span class="text-base shrink-0"><CxIcon name="clipboard-list" class="inline-block size-4 align-[-0.15em]" /></span>
              <span v-if="!sidebarCollapsed" class="truncate">Opt-In Requests</span>
            </div>
            <span
              v-if="!sidebarCollapsed"
              class="rounded-full px-2 py-0.5 text-[11px] font-semibold"
              :class="activeView === 'optin_requests' ? 'bg-cx-brand-soft text-cx-brand-ink' : 'bg-cx-well text-cx-ink-3'"
            >
              {{ (context.ois || []).length }}
            </span>
          </button>

          <!-- 5. My Profile (National ID & Identity) -->
          <button
            type="button"
            class="w-full flex items-center justify-between px-3 py-2.5 rounded-cx-sm text-xs font-semibold transition text-left"
            :class="
              activeView === 'profile'
                ? 'bg-cx-brand-soft text-cx-brand-ink shadow-cx'
                : 'text-cx-ink-3 hover:bg-cx-well hover:text-cx-ink'
            "
            @click="activeView = 'profile'"
          >
            <div class="flex items-center gap-3 truncate">
              <span class="text-base shrink-0"><CxIcon name="user" class="inline-block size-4 align-[-0.15em]" /></span>
              <span v-if="!sidebarCollapsed" class="truncate">My Profile</span>
            </div>
            <span
              v-if="!sidebarCollapsed && userProfile.masked_national_id"
              class="rounded-full bg-cx-well text-cx-ink-2 font-mono px-2 py-0.5 text-[11px]"
            >
              {{ userProfile.masked_national_id }}
            </span>
          </button>

          <!-- 7. Network Support -->
          <button
            type="button"
            class="w-full flex items-center gap-3 px-3 py-2.5 rounded-cx-sm text-xs font-semibold transition text-left"
            :class="
              supportDrawerOpen
                ? 'bg-cx-brand-soft text-cx-brand-ink shadow-cx'
                : 'text-cx-ink-3 hover:bg-cx-well hover:text-cx-ink'
            "
            @click="openNetworkSupportDrawer()"
          >
            <span class="text-base shrink-0"><CxIcon name="chat" class="inline-block size-4 align-[-0.15em]" /></span>
            <span v-if="!sidebarCollapsed" class="truncate">Network Support</span>
          </button>
        </nav>
      </aside>

      <!-- 2. MAIN APPLICATION CONTENT -->
      <div class="flex-1 flex flex-col min-w-0 overflow-y-auto">
        <!-- Top App Bar (Facility search and account identity) -->
        <header class="cx-glass-chrome h-16 bg-cx-surface border-b border-cx-border px-3 sm:px-6 flex items-center justify-between shrink-0 sticky top-0 z-20">
          <!-- Search Bar -->
          <div class="relative w-[min(58vw,20rem)] sm:w-80 lg:w-96">
            <svg class="size-4 text-cx-ink-4 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="11" cy="11" r="8"></circle>
              <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
            </svg>
            <input
              ref="globalSearchRef"
              type="text"
              v-model="searchQuery"
              placeholder="Search by facility name, Facility ID or MFL code"
              aria-label="Search by facility name, Facility ID or MFL code"
              class="w-full rounded-cx-sm bg-cx-well border border-cx-border pl-9 pr-9 sm:pr-12 py-2 text-xs font-medium text-cx-ink placeholder:text-cx-ink-4 focus:bg-cx-surface focus:border-cx-brand focus:outline-none focus:ring-2 focus:ring-cx-brand-soft transition"
              @input="onGlobalSearchInput"
            />
            <button v-if="searchQuery" type="button" class="absolute right-2 top-1/2 -translate-y-1/2 rounded px-1 text-sm text-cx-ink-3 hover:text-cx-ink sm:hidden" aria-label="Clear facility search" @click="searchQuery = ''">×</button>
            <span v-else class="absolute right-2.5 top-1/2 hidden -translate-y-1/2 rounded-cx-sm bg-cx-band px-1.5 py-0.5 text-[11px] font-mono text-cx-ink-3 sm:block">
              ⌘K
            </span>
            <button v-if="searchQuery" type="button" class="absolute right-2.5 top-1/2 hidden -translate-y-1/2 rounded-cx-sm bg-cx-band px-1.5 py-0.5 text-[11px] font-semibold text-cx-ink-3 hover:text-cx-ink sm:block" aria-label="Clear facility search" @click="searchQuery = ''">Clear</button>
          </div>

          <!-- Account controls -->
          <div class="flex items-center gap-1 sm:gap-3">
            <!-- Profile and sign-out live here; product navigation stays in the sidebar. -->
            <div class="relative" ref="userMenuRef">
              <button
                type="button"
                class="flex items-center gap-2 p-1 rounded-cx-sm hover:bg-cx-well transition focus:outline-none select-none cursor-pointer border border-transparent hover:border-cx-border"
                @click.stop="toggleUserMenu"
                :aria-expanded="isUserMenuOpen"
                title="Account menu"
              >
                <div class="size-8 rounded-full bg-cx-brand text-cx-contrast flex items-center justify-center font-semibold text-xs shadow-cx shrink-0 ring-2 ring-cx-brand-soft">
                  {{ userInitials }}
                </div>
                <div class="hidden lg:block text-left mr-0.5">
                  <span class="text-xs font-semibold text-cx-ink block leading-tight truncate max-w-[130px]">
                    {{ userDisplayName }}
                  </span>
                  <span class="text-[11px] text-cx-ink-3 block leading-tight truncate max-w-[130px]">
                    {{ primaryOrganizationName }}
                  </span>
                </div>
                <svg
                  class="size-4 text-cx-ink-4 transition-transform duration-200"
                  :class="isUserMenuOpen ? 'rotate-180' : ''"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                >
                  <path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              <!-- Floating User Menu -->
              <div
                v-if="isUserMenuOpen"
                class="cx-glass-panel absolute right-0 top-full mt-2 w-64 rounded-cx bg-cx-surface shadow-cx-raised border border-cx-border p-2 z-50 text-xs animate-in fade-in slide-in-from-top-1 duration-150"
              >
                <!-- User Header Info -->
                <div class="px-3 py-2.5 bg-cx-well rounded-cx-sm mb-1.5 border border-cx-border-soft">
                  <span class="font-bold text-cx-ink block truncate">{{ userDisplayName }}</span>
                  <span class="text-[11px] text-cx-ink-3 block truncate font-mono">{{ context.user }}</span>
                  <div class="flex items-center gap-1.5 mt-1.5 flex-wrap">
                    <span class="rounded-cx-sm bg-cx-brand-soft text-cx-brand-ink text-[11px] font-semibold px-1.5 py-0.5">
                      {{ primaryOrganizationName || 'Health System' }}
                    </span>
                    <span v-if="userProfile.masked_national_id" class="rounded-cx-sm bg-cx-band text-cx-ink-2 text-[11px] font-mono px-1.5 py-0.5">
                      {{ userProfile.masked_national_id }}
                    </span>
                  </div>
                </div>

                <button
                  type="button"
                  class="w-full flex items-center gap-2.5 px-3 py-2 rounded-cx-sm text-cx-ink-2 hover:bg-cx-well hover:text-cx-ink font-semibold transition text-left cursor-pointer"
                  @click="navigateTo('profile')"
                >
                  <CxIcon name="user" class="size-4" />
                  <span>Account settings</span>
                </button>

                <div class="border-t border-cx-border-soft my-1.5"></div>

                <!-- Sign Out — POST /api/method/logout via frappe-ui resource (POST-only endpoint) -->
                <button
                  type="button"
                  class="w-full flex items-center gap-2.5 px-3 py-2 rounded-cx-sm text-cx-danger hover:bg-cx-danger-soft font-semibold transition text-left cursor-pointer disabled:opacity-60"
                  :disabled="logout.loading"
                  @click="logout.submit()"
                >
                  <svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                  </svg>
                  <span>{{ logout.loading ? 'Signing out…' : 'Sign Out' }}</span>
                </button>
              </div>
            </div>
          </div>
        </header>

        <!-- Dynamic Main Views -->
        <main class="p-4 pb-24 sm:p-6 sm:pb-24 md:pb-6 max-w-7xl w-full mx-auto space-y-6">
          <!-- Loading skeleton -->
          <div v-if="loading" class="space-y-4" aria-busy="true">
            <div class="h-8 w-56 rounded-cx-sm bg-cx-band animate-pulse" />
            <div class="h-3 w-96 max-w-full rounded-cx-sm bg-cx-band animate-pulse" />
            <div class="grid gap-4 sm:grid-cols-3">
              <div v-for="i in 3" :key="i" class="rounded-cx border border-cx-border bg-cx-surface p-5">
                <div class="mb-3 h-3 w-24 rounded-cx-sm bg-cx-band animate-pulse" />
                <div class="h-7 w-32 rounded-cx-sm bg-cx-band animate-pulse" />
              </div>
            </div>
            <div class="h-96 rounded-cx border border-cx-border bg-cx-surface" />
          </div>

          <!-- Error state with retry -->
          <div v-else-if="errorMessage" class="rounded-cx border border-cx-danger-border bg-cx-surface p-10 text-center">
            <span class="text-3xl"><CxIcon name="alert" class="inline-block size-4 align-[-0.15em]" /></span>
            <h1 class="mt-3 text-lg font-bold text-cx-ink">Unable to load your portal</h1>
            <p class="mx-auto mt-1 max-w-md text-xs text-cx-ink-3">{{ errorMessage }}</p>
            <button
              type="button"
              class="mt-4 rounded-cx-sm bg-cx-brand px-5 py-2.5 text-xs font-semibold text-cx-contrast shadow-cx hover:bg-cx-brand-strong transition"
              @click="retryLoad()"
            >
              Try again
            </button>
          </div>

          <template v-else>
          <FacilitySingleView
            v-if="activeView === 'facility_detail' && drawerFacility"
            :facility="drawerFacility"
            :invoices="drawerInvoices"
            :orders="drawerOrders"
            :payments="drawerPayments"
            :token-packages="context.token_packages"
            :default-currency="defaultCurrency"
            :ensure-provisioning-draft="ensureProvisioningDraft"
            :get-provisioning-status="getProvisioningStatus"
            :busy-order="busyId"
            :token-alert="tokenAlerts[drawerFacility.mfl_code] || null"
            @back="closeFacilityDrawer"
            @open-top-up="openTopUpModal"
            @open-support="openNetworkSupportDrawer"
            @pay="openMpesaModal"
            @review-order="openOrderReview"
            @create-invoice="createInvoice"
            @open-billing="activeView = 'billing'"
            @token-alert-saved="onTokenAlertSaved"
          />
          <!-- ============================================================== -->
          <!-- VIEW A: FACILITIES TABLE (Exact match to screenshot structure) -->
          <!-- ============================================================== -->
          <div v-if="activeView === 'facilities'" class="space-y-4">
            <!-- Breadcrumbs / Page Header -->
            <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div>
                <h1 class="text-4xl font-bold text-cx-ink tracking-tight leading-tight">
                  Facilities
                </h1>
                <p class="text-xs text-cx-ink-3 mt-0.5">
                  Search your linked facilities by name, then open any facility to review its operations and provisioning status.
                </p>
              </div>

              <!-- Registry search and linking live inside Facilities, not as a second menu. -->
              <div class="flex items-center gap-2">
                <button
                  type="button"
                  class="inline-flex items-center gap-1.5 rounded-cx-sm bg-cx-brand px-4 py-2 text-xs font-semibold text-cx-contrast shadow-cx hover:bg-cx-brand-strong transition"
                  @click="openAddFacilityModal()"
                >
                  <span><CxIcon name="plus" class="inline-block size-4 align-[-0.15em]" /> Find and link facility</span>
                </button>
              </div>
            </div>

            <!-- Directory filters and view controls -->
            <div class="flex flex-wrap items-center justify-between gap-3 pt-2">
              <div class="flex items-center gap-2 flex-wrap">
                <!-- Status Filter -->
                <select
                  v-model="selectedStatusFilter"
                  aria-label="Filter facilities by go-live readiness"
                  class="rounded-cx-sm bg-cx-surface border border-cx-border px-3 py-1.5 text-xs font-semibold text-cx-ink-2 shadow-cx focus:outline-none focus:border-cx-brand"
                >
                  <option value="all">All readiness</option>
                  <option value="ready">Ready for go-live</option>
                  <option value="progress">Implementation in progress</option>
                  <option value="lead">Lead inquiry</option>
                </select>

                <!-- Level Filter -->
                <select
                  v-model="selectedLevelFilter"
                  aria-label="Filter facilities by KEPH level"
                  class="rounded-cx-sm bg-cx-surface border border-cx-border px-3 py-1.5 text-xs font-semibold text-cx-ink-2 shadow-cx focus:outline-none focus:border-cx-brand"
                >
                  <option value="all">All KEPH Levels</option>
                  <option v-for="level in availableLevelFilters" :key="level" :value="level">{{ level }}</option>
                </select>

                <!-- Partner / Network Filter -->
                <select
                  v-model="selectedNetworkFilter"
                  aria-label="Filter facilities by partner network"
                  class="rounded-cx-sm bg-cx-surface border border-cx-border px-3 py-1.5 text-xs font-semibold text-cx-ink-2 shadow-cx focus:outline-none focus:border-cx-brand"
                >
                  <option value="all">All Networks / Partners</option>
                  <option v-for="net in availableNetworks" :key="net" :value="net">
                    {{ net }}
                  </option>
                </select>
              </div>

              <!-- View Switcher & Network Grouping -->
              <div class="flex items-center gap-2">
                <!-- Group By Network Button -->
                <button
                  type="button"
                  class="inline-flex items-center gap-1.5 rounded-cx-sm border px-2.5 py-1.5 text-xs font-semibold transition shadow-cx cursor-pointer select-none"
                  :class="groupByNetwork ? 'bg-cx-well border-cx-border text-cx-ink' : 'bg-cx-surface border-cx-border text-cx-ink-3 hover:bg-cx-well'"
                  @click="groupByNetwork = !groupByNetwork"
                  title="Group facilities by partner network"
                >
                  <span><CxIcon name="globe" class="inline-block size-4 align-[-0.15em]" /></span>
                  <span>{{ groupByNetwork ? 'Grouped by Network' : 'Group by Network' }}</span>
                </button>

                <div class="h-4 w-px bg-cx-border"></div>

                <button
                  type="button"
                  class="hidden sm:inline-flex rounded-cx-sm border p-1.5 text-xs cursor-pointer"
                  :class="facilityViewMode === 'table' ? 'bg-cx-well border-cx-border text-cx-ink font-semibold' : 'bg-cx-surface border-cx-border text-cx-ink-3'"
                  @click="facilityViewMode = 'table'"
                  title="Table view"
                >
                  <svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="8" y1="6" x2="21" y2="6"></line>
                    <line x1="8" y1="12" x2="21" y2="12"></line>
                    <line x1="8" y1="18" x2="21" y2="18"></line>
                    <line x1="3" y1="6" x2="3.01" y2="6"></line>
                    <line x1="3" y1="12" x2="3.01" y2="12"></line>
                    <line x1="3" y1="18" x2="3.01" y2="18"></line>
                  </svg>
                </button>
                <button
                  type="button"
                  class="hidden sm:inline-flex rounded-cx-sm border p-1.5 text-xs cursor-pointer"
                  :class="facilityViewMode === 'cards' ? 'bg-cx-well border-cx-border text-cx-ink font-semibold' : 'bg-cx-surface border-cx-border text-cx-ink-3'"
                  @click="facilityViewMode = 'cards'"
                  title="Card view"
                >
                  <svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="3" y="3" width="7" height="7"></rect>
                    <rect x="14" y="3" width="7" height="7"></rect>
                    <rect x="14" y="14" width="7" height="7"></rect>
                    <rect x="3" y="14" width="7" height="7"></rect>
                  </svg>
                </button>
              </div>
            </div>

            <p v-if="searchQuery || selectedStatusFilter !== 'all' || selectedLevelFilter !== 'all' || selectedNetworkFilter !== 'all'" class="-mt-2 text-[11px] text-cx-ink-3" role="status">
              Showing {{ filteredFacilities.length }} of {{ allFacilities.length }} facilities
            </p>

            <!-- Empty portfolio state -->
            <div v-if="!allFacilities.length" class="rounded-cx border border-cx-border bg-cx-surface p-10 text-center">
              <span class="mb-2 block text-3xl"><CxIcon name="hospital" class="inline-block size-4 align-[-0.15em]" /></span>
              <p class="text-sm font-semibold text-cx-ink">No facilities in your portfolio yet</p>
              <p class="mx-auto mt-1 max-w-md text-xs text-cx-ink-3">
                Link your clinics from the Health Facility Registry — we can auto-discover the ones registered under your National ID.
              </p>
              <p class="mt-4 text-xs font-semibold text-cx-brand-ink">Use “Find and link facility” above to search the registry or discover clinics linked to your ID.</p>
            </div>

            <div v-else-if="!filteredFacilities.length" class="rounded-cx border border-cx-border bg-cx-surface p-8 text-center" role="status">
              <p class="text-sm font-semibold text-cx-ink">No facilities match these filters</p>
              <p class="mt-1 text-xs text-cx-ink-3">Search uses facility names in your portfolio. Registry identifiers are searched from “Find and link facility.”</p>
              <button type="button" class="mt-4 rounded-cx-sm border border-cx-border bg-cx-surface px-3.5 py-2 text-xs font-semibold text-cx-ink-2 hover:bg-cx-well" @click="resetFacilityFilters()">Clear search and filters</button>
            </div>

            <!-- TABLE VIEW -->
          <div v-if="allFacilities.length && filteredFacilities.length && facilityViewMode === 'table' && !isMobileViewport" class="space-y-4">
              <!-- Render Grouped by Network when toggle active -->
              <template v-if="groupByNetwork">
                <div
                  v-for="group in facilitiesByNetwork"
                  :key="group.network"
                  class="cx-glass-panel bg-cx-surface rounded-cx border border-cx-border shadow-cx overflow-hidden space-y-0"
                >
                  <!-- Group Header Banner -->
                  <div class="px-5 py-3 bg-cx-band border-b border-cx-border flex items-center justify-between">
                    <div class="flex items-center gap-2.5">
                      <div class="size-6 rounded-cx-sm bg-cx-well text-cx-ink-2 flex items-center justify-center font-semibold text-xs">
                        <CxIcon name="globe" class="inline-block size-4 align-[-0.15em]" />
                      </div>
                      <span class="font-semibold text-xs text-cx-ink uppercase tracking-[0.08em]">
                        {{ group.network }}
                      </span>
                      <span class="rounded-full bg-cx-surface border border-cx-border text-cx-ink-2 px-2 py-0.5 text-[11px] font-semibold">
                        {{ group.facilities.length }} {{ group.facilities.length === 1 ? 'branch' : 'branches' }}
                      </span>
                    </div>
                  </div>

                  <div class="overflow-x-auto">
                    <table class="w-full min-w-[54rem] text-left border-collapse text-xs">
                      <thead>
                        <tr class="border-b border-cx-border bg-cx-band text-[11px] font-semibold uppercase tracking-[0.08em] text-cx-ink-3">
                          <th class="py-3 px-4">Facility</th>
                          <th class="py-3 px-4">Facility ID</th>
                          <th class="py-3 px-4">Go-live readiness</th>
                          <th class="py-3 px-4">Plan</th>
                          <th class="py-3 px-4 text-right">Available tokens</th>
                          <th class="py-3 px-4 text-right">Actions</th>
                        </tr>
                      </thead>
                      <tbody class="divide-y divide-cx-border-soft">
                        <tr
                          v-for="facility in group.facilities"
                          :key="facility.mfl_code"
                          class="cursor-pointer hover:bg-cx-band transition"
                          @click="openFacilityFromSurface($event, facility)"
                        >
                          <td class="py-3.5 px-4 font-semibold text-cx-ink">
                            <div class="flex items-center gap-3">
                              <div class="size-8 rounded-cx-sm bg-cx-brand-soft text-cx-brand-ink flex items-center justify-center font-semibold text-xs shrink-0 border border-cx-brand-soft">
                                <CxIcon name="hospital" class="inline-block size-4 align-[-0.15em]" />
                              </div>
                              <div class="min-w-[12rem]">
                                <button
                                type="button"
                                class="block text-left font-bold text-cx-ink underline-offset-2 hover:text-cx-brand-strong hover:underline"
                                @click="openFacilityDrawer(facility)"
                              >
                                {{ facility.facility_name }}
                              </button>
                              <p class="mt-0.5 text-[11px] font-normal text-cx-ink-3">{{ facility.keph_level }}</p>
                                <span v-if="facility.network" class="inline-flex items-center gap-1 rounded-cx-sm bg-cx-well text-cx-ink-2 px-1.5 py-0.5 text-[11px] font-medium mt-0.5 border border-cx-border-soft" data-testid="facility-partner">
                                  <span><CxIcon name="globe" class="inline-block size-4 align-[-0.15em]" /></span>
                                  <span>{{ facility.network }}</span>
                                </span>
                              </div>
                            </div>
                          </td>
                          <td class="py-3.5 px-4">
                            <button
                              v-if="facilityId(facility)"
                              type="button"
                              class="font-mono text-xs font-semibold text-cx-ink-2 hover:text-cx-brand inline-flex items-center gap-1.5 bg-cx-well px-2 py-0.5 rounded-cx-sm border border-cx-border-soft cursor-pointer whitespace-nowrap"
                              :title="`Copy Facility ID ${facilityId(facility)}`"
                              data-testid="facility-id"
                              @click="copyMfl(facilityId(facility))"
                            >
                              <span>{{ facilityId(facility) }}</span>
                              <CxIcon :name="copiedMfl === facilityId(facility) ? 'check' : 'copy'" class="size-3.5 text-cx-ink-3" />
                            </button>
                            <span v-else class="text-[11px] italic text-cx-ink-3" data-testid="facility-id">Not linked yet</span>
                            <p v-if="facility.mfl_code" class="mt-1 font-mono text-[11px] text-cx-ink-3">MFL {{ facility.mfl_code }}</p>
                          </td>
                          <td class="py-3.5 px-4">
                            <span
                              class="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-[11px] font-semibold border"
                              :class="facility.go_live ? 'bg-cx-success-soft text-cx-success-ink border-cx-success-border' : 'bg-cx-warning-soft text-cx-warning-ink border-cx-warning-border'"
                            >
                              <span class="size-1.5 rounded-full" :class="facility.go_live ? 'bg-cx-success' : 'bg-cx-warning'"></span>
                              <span>{{ facilityReadinessLabel(facility) }}</span>
                            </span>
                          </td>
                          <td class="min-w-[10rem] py-3.5 px-4 font-medium text-cx-ink-2">
                            <span class="font-bold text-cx-ink block">{{ facility.token_package || 'No active plan' }}</span>
                            <span v-if="facility.recent_purchase" class="text-[11px] text-cx-ink-3 font-mono block mt-0.5">
                              {{ facility.recent_purchase.package_name }}: {{ money(facility.recent_purchase.amount, facility.recent_purchase.currency) }} · {{ facility.recent_purchase.date }}
                            </span>
                          </td>
                          <td class="py-3.5 px-4 text-right">
                            <span class="font-semibold font-mono text-sm inline-flex items-center gap-1 whitespace-nowrap" :class="tokenBalance(facility).known ? 'text-cx-brand' : 'text-cx-ink-3 text-xs'">
                              <span v-if="tokenBalance(facility).known"><CxIcon name="coins" class="inline-block size-4 align-[-0.15em]" /></span>
                              <span>{{ tokenBalanceText(facility) }}</span>
                            </span>
                          </td>
                          <td class="py-3.5 px-4 text-right">
                            <div class="flex flex-col items-end gap-1.5 whitespace-nowrap">
                              <button
                                v-if="facility.invoice_summary?.has_outstanding && !pendingPaymentForFacility(facility)"
                                type="button"
                                class="rounded-cx-sm bg-cx-success px-2.5 py-1 text-xs font-semibold text-cx-contrast hover:bg-cx-success transition shadow-cx inline-flex items-center gap-1 shrink-0 cursor-pointer"
                                @click="openMpesaModalForFacility(facility)"
                                title="Pay outstanding invoice via M-Pesa"
                              >
                                <span><CxIcon name="phone" class="inline-block size-4 align-[-0.15em]" /> Pay {{ money(facility.invoice_summary.outstanding_amount, facility.invoice_summary.currency) }}</span>
                              </button>
                              <span v-else-if="facility.invoice_summary?.has_outstanding" class="text-[11px] font-semibold text-cx-warning-ink">
                                Payment verification pending
                              </span>
                              <button
                                type="button"
                                class="rounded-cx-sm bg-cx-ink px-2.5 py-1 text-xs font-semibold text-cx-contrast hover:bg-cx-ink-hover transition shadow-cx cursor-pointer"
                                @click="openTopUpModal(facility)"
                              >
                                Top Up
                              </button>
                            </div>
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              </template>

              <!-- Render Flat Table when not grouped -->
              <div v-else class="cx-glass-panel bg-cx-surface rounded-cx border border-cx-border shadow-cx overflow-hidden">
                <div class="overflow-x-auto">
                  <table class="w-full min-w-[54rem] text-left border-collapse text-xs">
                    <thead>
                      <tr class="border-b border-cx-border bg-cx-band text-[11px] font-semibold uppercase tracking-[0.08em] text-cx-ink-3">
                        <th class="py-3 px-4">Facility</th>
                        <th class="py-3 px-4">Facility ID</th>
                        <th class="py-3 px-4">Go-live readiness</th>
                        <th class="py-3 px-4">Plan</th>
                        <th class="py-3 px-4 text-right">Available tokens</th>
                        <th class="py-3 px-4 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-cx-border-soft">
                      <tr
                        v-for="facility in filteredFacilities"
                        :key="facility.mfl_code"
                        class="cursor-pointer hover:bg-cx-band transition"
                        @click="openFacilityFromSurface($event, facility)"
                      >
                        <!-- Name & Location & Network -->
                        <td class="py-3.5 px-4 font-semibold text-cx-ink">
                          <div class="flex items-center gap-3">
                            <div class="size-8 rounded-cx-sm bg-cx-brand-soft text-cx-brand-ink flex items-center justify-center font-semibold text-xs shrink-0 border border-cx-brand-soft">
                              <CxIcon name="hospital" class="inline-block size-4 align-[-0.15em]" />
                            </div>
                            <div class="min-w-[12rem]">
                              <button
                                type="button"
                                class="block text-left font-bold text-cx-ink underline-offset-2 hover:text-cx-brand-strong hover:underline"
                                @click="openFacilityDrawer(facility)"
                              >
                                {{ facility.facility_name }}
                              </button>
                              <p class="mt-0.5 text-[11px] font-normal text-cx-ink-3">{{ facility.keph_level }}</p>
                              <span v-if="facility.network" class="inline-flex items-center gap-1 rounded-cx-sm bg-cx-well text-cx-ink-2 px-1.5 py-0.5 text-[11px] font-medium mt-0.5 border border-cx-border-soft" data-testid="facility-partner">
                                <span><CxIcon name="globe" class="inline-block size-4 align-[-0.15em]" /></span>
                                <span>{{ facility.network }}</span>
                              </span>
                            </div>
                          </div>
                        </td>

                        <!-- Facility ID (HFR FID), with the MFL code beneath -->
                        <td class="py-3.5 px-4">
                          <button
                            v-if="facilityId(facility)"
                            type="button"
                            class="font-mono text-xs font-semibold text-cx-ink-2 hover:text-cx-brand inline-flex items-center gap-1.5 bg-cx-well px-2 py-0.5 rounded-cx-sm border border-cx-border-soft cursor-pointer whitespace-nowrap"
                            :title="`Copy Facility ID ${facilityId(facility)}`"
                            data-testid="facility-id"
                            @click="copyMfl(facilityId(facility))"
                          >
                            <span>{{ facilityId(facility) }}</span>
                            <CxIcon :name="copiedMfl === facilityId(facility) ? 'check' : 'copy'" class="size-3.5 text-cx-ink-3" />
                          </button>
                          <span v-else class="text-[11px] italic text-cx-ink-3" data-testid="facility-id">Not linked yet</span>
                          <p v-if="facility.mfl_code" class="mt-1 font-mono text-[11px] text-cx-ink-3">MFL {{ facility.mfl_code }}</p>
                        </td>

                        <!-- Status Badge -->
                        <td class="py-3.5 px-4">
                          <span
                            class="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-[11px] font-semibold border"
                            :class="
                              facility.go_live
                                ? 'bg-cx-success-soft text-cx-success-ink border-cx-success-border'
                                : 'bg-cx-warning-soft text-cx-warning-ink border-cx-warning-border'
                            "
                          >
                            <span class="size-1.5 rounded-full" :class="facility.go_live ? 'bg-cx-success' : 'bg-cx-warning'"></span>
                            <span>{{ facilityReadinessLabel(facility) }}</span>
                          </span>
                        </td>

                        <!-- Plan & Recent Purchase -->
                        <td class="min-w-[10rem] py-3.5 px-4 font-medium text-cx-ink-2">
                          <span class="font-bold text-cx-ink block">{{ facility.token_package || 'No active plan' }}</span>
                          <span v-if="facility.recent_purchase" class="text-[11px] text-cx-ink-3 font-mono block mt-0.5">
                            {{ facility.recent_purchase.package_name }}: {{ money(facility.recent_purchase.amount, facility.recent_purchase.currency) }} · {{ facility.recent_purchase.date }}
                          </span>
                        </td>

                        <!-- Tokens -->
                        <td class="py-3.5 px-4 text-right">
                          <span class="font-semibold font-mono text-sm inline-flex items-center gap-1 whitespace-nowrap" :class="tokenBalance(facility).known ? 'text-cx-brand' : 'text-cx-ink-3 text-xs'">
                            <span v-if="tokenBalance(facility).known"><CxIcon name="coins" class="inline-block size-4 align-[-0.15em]" /></span>
                            <span>{{ tokenBalanceText(facility) }}</span>
                          </span>
                        </td>

                        <!-- Actions & Direct M-Pesa Settlement -->
                        <td class="py-3.5 px-4 text-right">
                          <div class="flex flex-col items-end gap-1.5 whitespace-nowrap">
                            <button
                              v-if="facility.invoice_summary?.has_outstanding && !pendingPaymentForFacility(facility)"
                              type="button"
                              class="rounded-cx-sm bg-cx-success px-2.5 py-1 text-xs font-semibold text-cx-contrast hover:bg-cx-success transition shadow-cx inline-flex items-center gap-1 shrink-0 cursor-pointer"
                              @click="openMpesaModalForFacility(facility)"
                              title="Pay outstanding invoice via M-Pesa"
                            >
                              <span><CxIcon name="phone" class="inline-block size-4 align-[-0.15em]" /> Pay {{ money(facility.invoice_summary.outstanding_amount, facility.invoice_summary.currency) }}</span>
                            </button>
                            <span v-else-if="facility.invoice_summary?.has_outstanding" class="text-[11px] font-semibold text-cx-warning-ink">
                              Payment verification pending
                            </span>
                            <button
                              type="button"
                              class="rounded-cx-sm bg-cx-ink px-2.5 py-1 text-xs font-semibold text-cx-contrast hover:bg-cx-ink-hover transition shadow-cx cursor-pointer"
                              @click="openTopUpModal(facility)"
                            >
                              Top Up
                            </button>
                          </div>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <!-- Footer summary -->
                <div class="p-4 bg-cx-well border-t border-cx-border flex items-center justify-between text-xs text-cx-ink-3 font-medium">
                  <span>Showing {{ filteredFacilities.length }} of {{ allFacilities.length }} registered clinics</span>
                  <span>Go-live readiness is shown on each facility row</span>
                </div>
              </div>
            </div>

            <!-- CARDS VIEW (Optional toggle) -->
            <div v-else-if="allFacilities.length && filteredFacilities.length" class="space-y-6">
              <!-- Render Grouped by Network when toggle active -->
              <template v-if="groupByNetwork">
                <div
                  v-for="group in facilitiesByNetwork"
                  :key="group.network"
                  class="space-y-3"
                >
                  <div class="flex items-center justify-between bg-cx-band rounded-cx-sm px-4 py-2.5 border border-cx-border">
                    <div class="flex items-center gap-2">
                      <span class="text-sm"><CxIcon name="globe" class="inline-block size-4 align-[-0.15em]" /></span>
                      <span class="font-semibold text-xs text-cx-ink uppercase tracking-[0.08em]">{{ group.network }}</span>
                      <span class="rounded-full bg-cx-surface border border-cx-border text-cx-ink-2 px-2 py-0.5 text-[11px] font-semibold">
                        {{ group.facilities.length }} {{ group.facilities.length === 1 ? 'branch' : 'branches' }}
                      </span>
                    </div>
                  </div>

                  <div class="grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(min(100%,18rem),1fr))]">
                    <FacilityCard
                      v-for="facility in group.facilities"
                      :key="facility.mfl_code"
                      :facility="facility"
                      :readiness-label="facilityReadinessLabel(facility)"
                      :money="money"
                      :payment-pending="Boolean(pendingPaymentForFacility(facility))"
                      :alert="tokenAlerts[facility.mfl_code]"
                      @open="openFacilityDrawer"
                      @top-up="openTopUpModal"
                      @pay="openMpesaModalForFacility"
                    />
                  </div>
                </div>
              </template>

              <!-- Render Flat Cards when not grouped -->
              <div v-else class="grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(min(100%,18rem),1fr))]">
                <FacilityCard
                  v-for="facility in filteredFacilities"
                  :key="facility.mfl_code"
                  :facility="facility"
                  :readiness-label="facilityReadinessLabel(facility)"
                  :money="money"
                  :payment-pending="Boolean(pendingPaymentForFacility(facility))"
                  :alert="tokenAlerts[facility.mfl_code]"
                  @open="openFacilityDrawer"
                  @top-up="openTopUpModal"
                  @pay="openMpesaModalForFacility"
                />
              </div>
            </div>
          </div>

          <!-- ============================================================== -->
          <!-- VIEW B: DASHBOARD / EXECUTIVE RUNWAY OVERVIEW                   -->
          <!-- ============================================================== -->
          <div v-if="activeView === 'dashboard'" class="space-y-6">
            <div
              v-if="draftOrders.length"
              data-testid="draft-orders-banner"
              class="flex flex-col gap-3 rounded-cx border border-cx-warning-border bg-cx-warning-soft p-4 sm:flex-row sm:items-center sm:justify-between"
            >
              <div class="min-w-0">
                <p class="text-xs font-semibold text-cx-warning-ink">
                  {{ draftOrders.length === 1 ? 'A token order is waiting for your review' : `${draftOrders.length} token orders are waiting for your review` }}
                </p>
                <p class="mt-0.5 text-[11px] text-cx-ink-2">Confirm your billing details and generate the invoice. Your facility's tokens are added once the invoice is paid.</p>
              </div>
              <button
                type="button"
                class="shrink-0 rounded-cx-sm bg-cx-ink px-3 py-2 text-xs font-semibold text-cx-contrast hover:bg-cx-ink-hover transition"
                @click="openOrderReview(draftOrders[0])"
              >
                Review order
              </button>
            </div>
            <!-- Organization identity band: the legal parent entity owns the account -->
            <div class="cx-glass-panel rounded-cx border border-cx-border bg-cx-surface p-5 shadow-cx">
              <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div class="min-w-0">
                  <span class="text-[11px] font-semibold uppercase tracking-[0.08em] text-cx-ink-3">Your Organization</span>
                  <h1 class="mt-0.5 line-clamp-2 break-words text-2xl font-bold tracking-tight text-cx-ink leading-tight sm:text-4xl" :title="primaryOrganizationName">{{ primaryOrganizationName }}</h1>
                  <div class="mt-2 flex flex-wrap items-center gap-2">
                    <span v-if="primaryNetworkName" class="inline-flex items-center gap-1 rounded-cx-sm border border-cx-border bg-cx-well px-2 py-0.5 text-[11px] font-semibold text-cx-ink-2">
                      <span><CxIcon name="globe" class="inline-block size-4 align-[-0.15em]" /></span>
                      <span>{{ primaryNetworkName }}</span>
                    </span>
                    <span class="inline-flex items-center gap-1 rounded-cx-sm border border-cx-border bg-cx-well px-2 py-0.5 text-[11px] font-semibold text-cx-ink-2">
                      <span><CxIcon name="hospital" class="inline-block size-4 align-[-0.15em]" /></span>
                      <span>{{ facilityCount }} {{ facilityCount === 1 ? 'facility' : 'facilities' }}</span>
                    </span>
                    <span v-if="userProfile.masked_national_id" class="rounded-cx-sm border border-cx-border bg-cx-well px-2 py-0.5 font-mono text-[11px] text-cx-ink-2">
                      {{ userProfile.masked_national_id }}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Attention band: only what needs action, with a direct drill-in -->
            <div v-if="dashboardAttention.length" class="rounded-cx border border-cx-warning-border bg-cx-warning-soft p-4">
              <span class="text-[11px] font-semibold uppercase tracking-[0.08em] text-cx-warning-ink">Needs your attention</span>
              <div class="mt-2 space-y-2">
                <div
                  v-for="item in dashboardAttention"
                  :key="item.key"
                  class="flex items-center justify-between gap-3 rounded-cx-sm border border-cx-border bg-cx-surface px-3.5 py-2.5"
                >
                  <div class="flex min-w-0 items-center gap-2.5">
                    <CxIcon :name="item.icon" class="size-4 shrink-0" />
                    <div class="min-w-0">
                      <span class="block truncate text-xs font-semibold text-cx-ink">{{ item.text }}</span>
                      <span class="block truncate text-[11px] text-cx-ink-3">{{ item.meta }}</span>
                    </div>
                  </div>
                  <button
                    v-if="item.mfl_code"
                    type="button"
                    class="shrink-0 text-xs font-semibold text-cx-brand hover:underline"
                    @click="openAttentionFacility(item)"
                  >
                    Review →
                  </button>
                  <button
                    v-else
                    type="button"
                    class="shrink-0 text-xs font-semibold text-cx-brand hover:underline"
                    @click="activeView = 'billing'"
                  >
                    Open billing →
                  </button>
                </div>
              </div>
            </div>

            <!-- Top 3 Executive Metrics -->
            <div class="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(min(100%,15rem),1fr))]">
              <div class="min-w-0 rounded-cx border border-cx-border bg-cx-surface p-5 shadow-cx space-y-3">
                <span class="text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink-3 block">Available tokens</span>
                <div class="flex flex-wrap items-baseline gap-x-2 gap-y-1" data-testid="dashboard-total-tokens">
                  <template v-if="anyBalanceKnown">
                    <span class="text-4xl font-bold text-cx-brand tracking-tight leading-none xl:text-5xl">{{ totalTokenCount.toLocaleString() }}</span>
                    <span class="text-xs font-semibold text-cx-ink-3">Care Tokens</span>
                  </template>
                  <span v-else class="text-2xl font-bold text-cx-ink-3 tracking-tight leading-none">Not reported</span>
                </div>
                <p class="text-xs text-cx-ink-3 leading-relaxed">
                  {{ anyBalanceKnown ? 'Combined live balance across your linked facilities.' : 'Live balances appear once your facilities are metered.' }}
                </p>
                <div class="pt-2 border-t border-cx-border-soft">
                  <button type="button" class="text-xs font-semibold text-cx-brand hover:underline" @click="openTopUpModal()">
                    + Add Care Tokens →
                  </button>
                </div>
              </div>

              <div class="min-w-0 rounded-cx border border-cx-border bg-cx-surface p-5 shadow-cx space-y-3">
                <span class="text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink-3 block">Go-live readiness</span>
                <div class="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <span class="text-4xl font-bold text-cx-ink tracking-tight leading-none xl:text-5xl">{{ liveFacilitiesCount }} / {{ facilityCount }}</span>
                  <span class="text-xs font-semibold text-cx-success-ink">ready for go-live</span>
                </div>
                <p class="text-xs text-cx-ink-3 leading-relaxed">
                  Facilities your implementation team has marked ready for go-live.
                </p>
                <div class="pt-2 border-t border-cx-border-soft">
                  <button type="button" class="text-xs font-semibold text-cx-brand hover:underline" @click="activeView = 'facilities'">
                    Manage facilities →
                  </button>
                </div>
              </div>

              <div class="min-w-0 rounded-cx border border-cx-border bg-cx-surface p-5 shadow-cx space-y-3" :class="openInvoiceCount > 0 ? 'border-cx-warning-border bg-cx-warning-soft' : ''">
                <span class="text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink-3 block">Settlement & Invoices</span>
                <div class="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <span class="break-words text-4xl font-bold tracking-tight leading-none xl:text-5xl" :class="openInvoiceCount > 0 ? 'text-cx-warning-ink' : 'text-cx-ink'">
                    {{ openInvoiceCount > 0 ? money(totalOutstandingAmount) : 'Paid' }}
                  </span>
                  <span v-if="openInvoiceCount > 0" class="text-xs font-semibold text-cx-warning-ink">Due</span>
                </div>
                <p class="text-xs text-cx-ink-3 leading-relaxed">
                  {{ openInvoiceCount > 0 ? `${openInvoiceCount} ${openInvoiceCount === 1 ? 'invoice' : 'invoices'} awaiting payment by M-Pesa or bank` : 'All invoices settled with zero outstanding balance.' }}
                </p>
                <div class="pt-2 border-t border-cx-border-soft">
                  <button type="button" class="text-xs font-semibold text-cx-ink hover:underline" @click="activeView = 'billing'">
                    Go to Invoices & Billing →
                  </button>
                </div>
              </div>
            </div>

            <!-- Portfolio: one equal card per facility (no alphabetical hero) -->
            <div class="space-y-3">
              <div class="flex items-center justify-between">
                <h2 class="text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink-3">Your facilities</h2>
                <button type="button" class="text-xs font-semibold text-cx-brand hover:underline" @click="activeView = 'facilities'">
                  View all →
                </button>
              </div>

              <div v-if="!allFacilities.length" class="rounded-cx border border-cx-border bg-cx-surface p-8 text-center text-xs text-cx-ink-3">
                <span class="mb-2 block text-3xl"><CxIcon name="hospital" class="inline-block size-4 align-[-0.15em]" /></span>
                <p class="text-sm font-semibold text-cx-ink">No facilities in your portfolio yet</p>
                <p class="mt-1">Link your clinics from the Health Facility Registry to start using CareVerse.</p>
              </div>

              <div v-else class="grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(min(100%,18rem),1fr))]">
                <FacilityCard
                  v-for="fac in allFacilities"
                  :key="fac.mfl_code"
                  :facility="fac"
                  :readiness-label="facilityReadinessLabel(fac)"
                  :money="money"
                  :payment-pending="Boolean(pendingPaymentForFacility(fac))"
                  :alert="tokenAlerts[fac.mfl_code]"
                  @open="openFacilityDrawer"
                  @top-up="openTopUpModal"
                  @pay="openMpesaModalForFacility"
                />
              </div>
            </div>

            <!-- Recent activity: orders + payments, newest first -->
            <div v-if="recentActivity.length" class="space-y-3">
              <h2 class="text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink-3">Recent activity</h2>
              <div class="overflow-hidden rounded-cx border border-cx-border bg-cx-surface shadow-cx">
                <ul class="divide-y divide-cx-border-soft">
                  <li v-for="act in recentActivity" :key="act.kind + act.title" class="flex items-center gap-3 px-4 py-3">
                    <CxIcon :name="act.icon" class="size-4 shrink-0" />
                    <div class="min-w-0 flex-1">
                      <span class="block truncate text-xs font-semibold text-cx-ink">{{ act.title }}</span>
                      <span class="block truncate text-[11px] text-cx-ink-3">{{ act.text }}</span>
                    </div>
                    <span class="shrink-0 font-mono text-[11px] text-cx-ink-3">{{ act.date }}</span>
                  </li>
                </ul>
              </div>
            </div>
          </div>

          <!-- ============================================================== -->
          <!-- VIEW C: PLANS & PRICING (GitHub-Style Minimalist Architecture)  -->
          <!-- ============================================================== -->
          <div v-if="activeView === 'pricing'" class="space-y-8">
            <div class="max-w-3xl">
              <span class="inline-flex items-center gap-1.5 rounded-full border border-cx-brand-soft-border bg-cx-brand-soft px-3 py-0.5 text-xs font-semibold uppercase tracking-[0.08em] text-cx-brand-ink">
                Consumption-Based HMIS Pricing
              </span>
              <h1 class="text-4xl font-bold text-cx-ink tracking-tight mt-2 leading-tight">
                CareVerse Token Plans & Capacity
              </h1>
              <p class="text-sm text-cx-ink-3 mt-2 leading-relaxed">
                Compare the current Care Token packages for your facility. Each package shows its price and the Care Tokens it buys; token use depends on your HMIS activity.
              </p>
            </div>

            <!-- Pricing cards: one column per package (up to four) so the row spans the page -->
            <div
              class="grid gap-6"
              :class="packageGridClass(context.token_packages?.length)"
              data-testid="portal-package-grid"
            >
              <article
                v-for="pkg in context.token_packages"
                :key="pkg.item_code"
                class="flex flex-col rounded-cx border border-cx-border bg-cx-surface p-6 shadow-cx transition hover:shadow-cx"
                data-testid="portal-package-card"
              >
                <div class="flex h-7 items-center justify-between gap-2">
                  <h3 class="truncate text-lg font-bold text-cx-ink">{{ pkg.display_name }}</h3>
                  <span
                    v-if="isFreePackage(pkg)"
                    class="shrink-0 rounded-full bg-cx-well px-2 py-0.5 text-[11px] font-semibold text-cx-ink-2"
                  >
                    Free Trial
                  </span>
                </div>

                <!-- What the package buys: the headline -->
                <p class="mt-4 flex items-center gap-2 text-cx-brand" data-testid="portal-package-tokens">
                  <CxIcon name="coins" class="size-5 shrink-0" />
                  <span class="text-2xl font-bold tracking-tight">{{ Number(pkg.token_quantity || 0).toLocaleString() }}</span>
                  <span class="text-sm font-semibold">Care Tokens</span>
                </p>

                <!-- Price -->
                <div class="mt-4 border-t border-cx-border-soft pt-4" data-testid="portal-package-price">
                  <p class="flex items-baseline gap-1.5">
                    <span class="text-3xl font-bold leading-tight text-cx-ink">{{ money(pkg.price_ex_vat ?? pkg.price, pkg.currency) }}</span>
                    <span class="text-xs font-semibold text-cx-ink-3">{{ isFreePackage(pkg) ? 'no charge' : 'excl. VAT' }}</span>
                  </p>
                  <p class="mt-1 h-4 text-[11px] text-cx-ink-3">
                    <template v-if="!isFreePackage(pkg)">
                      {{ pkg.vat_label || 'VAT' }} {{ money(pkg.vat_amount, pkg.currency) }} · Total {{ money(pkg.gross_total, pkg.currency) }}
                    </template>
                  </p>
                  <p class="mt-1 h-4 text-[11px] font-semibold text-cx-ink-2">
                    <template v-if="pricePerToken(pkg)">{{ money(pricePerToken(pkg), pkg.currency, 2) }} per token</template>
                  </p>
                </div>

                <!-- Summary as a checklist: one sentence per line -->
                <ul class="mt-4 space-y-2.5 border-t border-cx-border-soft pt-4" data-testid="portal-package-summary">
                  <li
                    v-for="line in summaryLines(pkg.coverage_summary || pkg.description)"
                    :key="line"
                    class="flex items-start gap-2 text-xs leading-5 text-cx-ink-2"
                  >
                    <CxIcon name="check" class="mt-0.5 size-4 shrink-0 text-cx-success" />
                    <span>{{ line }}</span>
                  </li>
                </ul>

                <div class="mt-auto pt-5">
                  <button
                    type="button"
                    class="w-full rounded-cx-sm bg-cx-brand px-4 py-2.5 text-center text-xs font-semibold text-cx-contrast shadow-cx transition hover:bg-cx-brand-strong"
                    @click="selectPlanFromPricingTab(pkg)"
                  >
                    {{ isFreePackage(pkg) ? 'Choose free package' : `Choose ${pkg.display_name}` }}
                  </button>
                </div>
              </article>
            </div>

            <div class="mt-8 rounded-cx border border-cx-border bg-cx-well p-4 text-xs text-cx-ink-3">
              Package names, prices, token quantities, and summaries above reflect the current catalog. Contact Network Support if you need a capability-by-capability comparison.
            </div>
          </div>

          <!-- ============================================================== -->
          <!-- VIEW D: BILLING & INVOICES                                      -->
          <!-- ============================================================== -->
          <div v-if="activeView === 'billing'" class="space-y-6">
            <div>
              <h1 class="text-4xl font-bold text-cx-ink tracking-tight leading-tight">Billing & Invoices</h1>
              <p class="text-xs text-cx-ink-3 mt-0.5">Review invoices and token orders. Pay by M-Pesa Paybill and submit the transaction code for verification, or use Paystack card checkout.</p>
            </div>

            <!-- M-Pesa Paybill settlement details -->
            <div class="rounded-cx border border-cx-success-border bg-cx-success-soft p-4">
              <div class="flex items-center gap-3">
                <div class="size-8 shrink-0 rounded-cx-sm bg-cx-success text-cx-contrast flex items-center justify-center font-semibold text-sm">M</div>
                <div class="min-w-0">
                  <span class="font-semibold text-xs text-cx-success-ink block">M-Pesa Paybill<span v-if="paybillInfo.business_name"> · {{ paybillInfo.business_name }}</span></span>
                  <span class="text-[11px] text-cx-success-ink">Pay the invoice by Paybill, then submit your M-Pesa confirmation code for verification.</span>
                </div>
              </div>
              <div class="mt-3 grid gap-3 lg:grid-cols-3">
                <div class="rounded-cx-sm border border-cx-border bg-cx-surface p-3">
                  <span class="text-[11px] font-semibold uppercase tracking-[0.08em] text-cx-ink-3 block">Business No</span>
                  <div class="mt-1 flex items-center justify-between gap-2">
                    <span v-if="paybillInfo.business_number" class="font-mono text-base font-bold text-cx-ink">{{ paybillInfo.business_number }}</span>
                    <span v-else class="text-xs text-cx-ink-3">Not configured yet. Contact Network Support for payment details.</span>
                    <button
                      v-if="paybillInfo.business_number"
                      type="button"
                      class="rounded-cx-sm border border-cx-border bg-cx-surface px-2 py-0.5 text-[11px] font-semibold text-cx-ink-2 hover:bg-cx-well transition shrink-0"
                      @click="copyText(paybillInfo.business_number, 'paybill_biz')"
                    >
                      <CxIcon :name="copiedKey === 'paybill_biz' ? 'check' : 'copy'" class="mr-1 inline-block size-4 align-[-0.15em]" />{{ copiedKey === 'paybill_biz' ? 'Copied' : 'Copy' }}
                    </button>
                  </div>
                </div>
                <div class="rounded-cx-sm border border-cx-border bg-cx-surface p-3">
                  <span class="text-[11px] font-semibold uppercase tracking-[0.08em] text-cx-ink-3 block">Account No</span>
                  <p class="mt-1 text-[11px] text-cx-ink-3 leading-relaxed">
                    Enter the invoice number shown on the invoice you are paying.
                  </p>
                </div>
                <div class="rounded-cx-sm border border-cx-border bg-cx-surface p-3">
                  <span class="text-[11px] font-semibold uppercase tracking-[0.08em] text-cx-ink-3 block">How to pay</span>
                  <p class="mt-1 text-[11px] text-cx-ink-3 leading-relaxed">
                    1. M-Pesa app → Lipa na M-Pesa → Paybill<br />
                    2. Business No, then Account No (invoice number)<br />
                    3. Amount &amp; PIN. After payment, enter the M-Pesa confirmation code in the invoice payment flow.
                  </p>
                </div>
              </div>
            </div>

            <!-- Invoices List -->
            <div class="space-y-4">
              <div v-if="!allInvoices.length" class="bg-cx-surface rounded-cx border border-cx-border p-8 text-center text-xs text-cx-ink-3">
                <span class="text-3xl block mb-2"><CxIcon name="check-circle" class="inline-block size-4 align-[-0.15em]" /></span>
                <p class="font-semibold text-cx-ink text-sm">All invoices settled</p>
                <p class="mt-1">There are no outstanding balances due on your account.</p>
              </div>

              <div v-else class="space-y-3">
                <article
                  v-for="invoice in allInvoices"
                  :key="invoice.name"
                  class="bg-cx-surface rounded-cx border border-cx-border p-5 shadow-cx flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4"
                >
                  <div class="min-w-0">
                    <div class="flex flex-wrap items-center gap-2">
                      <span class="font-semibold text-sm text-cx-ink">{{ invoice.invoice_number || invoice.name }}</span>
                      <span
                        v-if="pendingPaymentForInvoice(invoice)"
                        class="rounded-cx-sm bg-cx-warning-soft px-2 py-0.5 text-[11px] font-semibold text-cx-warning-ink"
                      >
                        M-Pesa report · verification pending
                      </span>
                      <span
                        v-else
                        class="rounded-cx-sm px-2 py-0.5 text-[11px] font-semibold"
                        :class="invoiceStatus(invoice).key === 'overdue' ? 'bg-cx-danger-soft text-cx-danger-ink' : 'bg-cx-warning-soft text-cx-warning-ink'"
                      >
                        {{ invoiceStatus(invoice).label }}
                      </span>
                    </div>
                    <p class="text-xs text-cx-ink-3 mt-1">
                      Due: <strong>{{ invoice.due_date || 'On Receipt' }}</strong> · Issued: {{ invoice.posting_date }}
                    </p>
                    <p v-if="pendingPaymentForInvoice(invoice)" class="mt-1 text-[11px] text-cx-warning-ink">
                      Payment reference {{ pendingPaymentForInvoice(invoice).reference_no || pendingPaymentForInvoice(invoice).name }} is being checked. Please wait before paying again.
                    </p>
                    <span class="inline-flex max-w-full items-center gap-1.5 rounded-cx-sm border border-cx-border bg-cx-well px-2 py-0.5 mt-1.5 text-[11px] font-semibold text-cx-ink-2">
                      <span class="shrink-0"><CxIcon name="hospital" class="inline-block size-4 align-[-0.15em]" /></span>
                      <span class="min-w-0 truncate">{{ facilityLabel(invoice.crm_token_facility_mfl, allFacilities) }}</span>
                      <span v-if="invoice.crm_token_facility_mfl" class="shrink-0 font-mono text-[11px] text-cx-ink-3">MFL {{ invoice.crm_token_facility_mfl }}</span>
                    </span>
                  </div>

                  <div class="flex items-center gap-3 flex-wrap justify-between lg:justify-end lg:shrink-0">
                    <div class="lg:text-right">
                      <span class="text-base font-bold text-cx-ink block leading-tight">{{ money(invoice.amount, invoice.currency) }}</span>
                      <span class="text-[11px] text-cx-ink-4 uppercase font-medium">
                        {{ pendingPaymentForInvoice(invoice) ? 'Balance until verified' : 'Balance' }}
                      </span>
                    </div>
                    <span
                      v-if="pendingPaymentForInvoice(invoice)"
                      class="rounded-cx-sm border border-cx-warning-border bg-cx-warning-soft px-3 py-2 text-xs font-semibold text-cx-warning-ink"
                    >
                      Payment verification pending
                    </span>
                    <button
                      v-else
                      type="button"
                      class="rounded-cx-sm bg-cx-success px-4 py-2 text-xs font-semibold text-cx-contrast shadow-cx hover:bg-cx-success transition inline-flex items-center gap-1.5"
                      :disabled="busyId === invoice.name"
                      @click="openMpesaModal(invoice)"
                    >
                      <span>{{ busyId === invoice.name ? 'Connecting…' : 'Choose payment method' }}</span>
                    </button>
                  </div>
                </article>
              </div>
            </div>

            <!-- Orders awaiting invoice -->
            <div v-if="allOrders.length" class="space-y-3 pt-6 border-t border-cx-border">
              <h2 class="text-sm font-semibold uppercase tracking-[0.08em] text-cx-ink-3">Token Orders</h2>
              <p class="text-xs text-cx-ink-3">Review a draft order, confirm your billing details and generate its invoice. Tokens are added when the invoice is paid.</p>
              <div class="space-y-3">
                <article
                  v-for="order in allOrders"
                  :key="order.name"
                  class="bg-cx-surface rounded-cx border border-cx-border p-4 shadow-cx flex items-center justify-between"
                >
                  <div>
                    <span class="font-semibold text-xs text-cx-ink">{{ packageLabel(order.crm_token_package_item, context.token_packages) }}</span>
                    <span v-if="order.is_draft" class="ml-2 rounded-full border border-cx-warning-border bg-cx-warning-soft px-2 py-0.5 text-[11px] font-semibold text-cx-warning-ink">Draft · needs review</span>
                    <span class="text-xs text-cx-ink-3 ml-2">For {{ facilityLabel(order.crm_token_facility_mfl, allFacilities) }} · Order #{{ order.name }}</span>
                  </div>
                  <div class="flex items-center gap-3">
                    <span class="text-xs font-semibold text-cx-ink">{{ money(order.grand_total, order.currency) }}</span>
                    <button
                      v-if="order.is_draft"
                      type="button"
                      :data-testid="`review-order-${order.name}`"
                      class="rounded-cx-sm bg-cx-brand px-3 py-1.5 text-xs font-semibold text-cx-contrast hover:bg-cx-brand-strong transition cursor-pointer"
                      @click="openOrderReview(order)"
                    >
                      Review order
                    </button>
                    <button
                      v-if="order.can_create_invoice"
                      type="button"
                      class="rounded-cx-sm bg-cx-ink px-3 py-1.5 text-xs font-semibold text-cx-contrast hover:bg-cx-ink-hover transition cursor-pointer"
                      @click="createInvoice(order)"
                    >
                      Generate Invoice
                    </button>
                  </div>
                </article>
              </div>
            </div>

            <!-- Payment Receipts & History -->
            <div v-if="allPayments.length" class="space-y-3 pt-6 border-t border-cx-border">
              <div class="flex items-center justify-between">
                <div>
                  <h2 class="text-sm font-semibold uppercase tracking-[0.08em] text-cx-ink-3">Payment activity</h2>
                  <p class="text-xs text-cx-ink-3 mt-0.5">Recorded payments and M-Pesa reports awaiting verification.</p>
                </div>
                <span class="text-xs text-cx-ink-3 font-semibold bg-cx-well px-2.5 py-1 rounded-cx-sm border border-cx-border">
                  {{ allPayments.length }} {{ allPayments.length === 1 ? 'payment' : 'payments' }}
                </span>
              </div>

              <div class="bg-cx-surface rounded-cx border border-cx-border shadow-cx overflow-hidden">
                <div class="overflow-x-auto">
                  <table class="w-full min-w-[36rem] text-left border-collapse text-xs">
                    <thead>
                      <tr class="border-b border-cx-border bg-cx-well text-[11px] font-semibold uppercase tracking-[0.08em] text-cx-ink-3">
                        <th class="py-3 px-4">Date</th>
                        <th class="py-3 px-4">Invoice</th>
                        <th class="py-3 px-4">Mode & Reference</th>
                        <th class="py-3 px-4 text-right">Amount</th>
                        <th class="py-3 px-4 text-center">Status</th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-cx-border-soft">
                      <tr v-for="pay in allPayments" :key="pay.name" class="hover:bg-cx-band transition">
                        <td class="py-3 px-4 text-cx-ink-3">{{ pay.posting_date }}</td>
                        <td class="py-3 px-4 font-mono text-[11px] text-cx-ink-2">{{ pay.invoice_names?.join(', ') || pay.invoice || '—' }}</td>
                        <td class="py-3 px-4">
                          <span class="font-semibold text-cx-ink">{{ pay.mode_of_payment }}</span>
                          <span v-if="pay.reference_no" class="ml-2 font-mono text-[11px] text-cx-ink-3 bg-cx-well px-1.5 py-0.5 rounded-cx-sm border border-cx-border">
                            {{ pay.reference_no }}
                          </span>
                        </td>
                        <td class="py-3 px-4 text-right font-bold text-cx-ink">{{ money(pay.amount, 'KES') }}</td>
                        <td class="py-3 px-4 text-center">
                          <span
                            class="rounded-full px-2 py-0.5 text-[11px] font-semibold border"
                            :class="pay.status === 'Recorded' ? 'bg-cx-success-soft text-cx-success-ink border-cx-success-border' : 'bg-cx-warning-soft text-cx-warning-ink border-cx-warning-border'"
                          >
                            {{ pay.status }}
                          </span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>

          <!-- ============================================================== -->
          <!-- VIEW E1: OPT-IN REQUESTS (first-class records with quotes)     -->
          <!-- ============================================================== -->
          <div v-if="activeView === 'optin_requests'" class="space-y-6">
            <OptInRequests :requests="optinRequests" />
          </div>

          <!-- ============================================================== -->
          <!-- VIEW F: MY PROFILE & IDENTIFICATION                            -->
          <!-- ============================================================== -->
          <div v-if="activeView === 'profile'" class="space-y-6 max-w-5xl">
            <!-- Profile Hero Header Banner -->
            <div class="rounded-cx border border-cx-border bg-cx-surface p-6 shadow-cx flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
              <div class="flex items-center gap-4">
                <div class="relative flex-shrink-0">
                  <div class="grid size-16 place-items-center rounded-full bg-cx-brand-soft text-cx-brand-ink text-xl font-bold shadow-sm border border-cx-brand-soft-border">
                    {{ userInitials }}
                  </div>
                  <div
                    v-if="userProfile.national_id_verified"
                    class="absolute -bottom-1 -right-1 grid size-6 place-items-center rounded-full bg-cx-success text-white shadow-sm ring-2 ring-cx-surface"
                    title="Verified Identity"
                  >
                    <CxIcon name="check" class="size-3.5 stroke-[2.5]" />
                  </div>
                </div>
                <div class="space-y-1">
                  <div class="flex flex-wrap items-center gap-2.5">
                    <h1 class="text-2xl font-bold text-cx-ink tracking-tight">{{ userProfile.full_name || userDisplayName }}</h1>
                    <span
                      class="rounded-full px-2.5 py-0.5 text-[11px] font-semibold border inline-flex items-center gap-1"
                      :class="userProfile.national_id_verified ? 'bg-cx-success-soft text-cx-success-ink border-cx-success-border' : 'bg-cx-well text-cx-ink-2 border-cx-border'"
                    >
                      <CxIcon :name="userProfile.national_id_verified ? 'shield-check' : 'user'" class="size-3" />
                      {{ userProfile.national_id_verified ? 'Verified Facility Owner' : 'Account Holder' }}
                    </span>
                  </div>
                  <p class="text-xs text-cx-ink-2 font-medium">
                    {{ userProfile.organization || primaryOrganizationName }}
                    <span v-if="partnerName(userProfile.primary_network)"> · {{ partnerName(userProfile.primary_network) }}</span>
                  </p>
                  <p class="text-[11px] font-mono text-cx-ink-3">
                    {{ userProfile.email }}
                    <span v-if="userProfile.mobile_no"> · {{ userProfile.mobile_no }}</span>
                  </p>
                </div>
              </div>

              <div class="flex items-center gap-2.5 w-full md:w-auto">
                <button
                  type="button"
                  class="rounded-cx-sm bg-cx-brand px-4 py-2.5 text-xs font-semibold text-cx-contrast shadow-cx hover:bg-cx-brand-strong transition inline-flex items-center justify-center gap-1.5 flex-1 md:flex-initial"
                  @click="openEditProfileModal()"
                >
                  <CxIcon name="pencil" class="size-3.5" />
                  <span>Edit Profile Details</span>
                </button>
                <button
                  type="button"
                  class="rounded-cx-sm border border-cx-border bg-cx-surface px-4 py-2.5 text-xs font-semibold text-cx-ink-2 hover:bg-cx-well transition inline-flex items-center justify-center gap-1.5 flex-1 md:flex-initial"
                  @click="activeView = 'facilities'"
                >
                  <CxIcon name="hospital" class="size-3.5" />
                  <span>View Facilities</span>
                </button>
              </div>
            </div>

            <!-- Profile Cards Grid -->
            <div class="grid gap-6 md:grid-cols-2">
              <!-- Card 1: Official National KYC & Identity -->
              <div class="rounded-cx border border-cx-border bg-cx-surface p-6 shadow-cx space-y-4">
                <div class="flex items-center justify-between pb-3 border-b border-cx-border-soft">
                  <div class="flex items-center gap-2">
                    <span class="grid size-7 place-items-center rounded-cx-sm bg-cx-brand-soft text-cx-brand-ink">
                      <CxIcon name="shield-check" class="size-4" />
                    </span>
                    <div>
                      <span class="text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink-3 block">KYC & Registry Identity</span>
                      <span class="text-sm font-bold text-cx-ink">Official Verification</span>
                    </div>
                  </div>
                  <span
                    class="rounded-full px-2.5 py-0.5 text-[11px] font-semibold border"
                    :class="userProfile.national_id_verified ? 'bg-cx-success-soft text-cx-success-ink border-cx-success-border' : 'bg-cx-well text-cx-ink-2 border-cx-border'"
                  >
                    {{ userProfile.national_id_verified ? 'Verified on Registry' : (userProfile.national_id ? 'On file' : 'Not added') }}
                  </span>
                </div>

                <div class="space-y-3">
                  <div class="rounded-cx-sm bg-cx-well border border-cx-border p-3.5 space-y-2">
                    <div class="flex items-center justify-between text-xs text-cx-ink-3 font-medium">
                      <span>{{ userProfile.identification_type || 'Kenyan National ID' }}</span>
                      <span class="text-[10px] uppercase font-semibold text-cx-success-ink" v-if="userProfile.national_id_verified">
                        Active Verification
                      </span>
                    </div>
                    <div class="flex items-center justify-between">
                      <span class="font-mono text-lg font-bold tracking-wider text-cx-ink">
                        {{ showUnmaskedId ? (userProfile.national_id || 'Not on file') : (userProfile.masked_national_id || 'Not on file') }}
                      </span>
                      <button
                        type="button"
                        class="rounded-cx-sm border border-cx-border bg-cx-surface px-2.5 py-1 text-xs font-semibold text-cx-ink-2 hover:bg-cx-well transition inline-flex items-center gap-1"
                        @click="showUnmaskedId = !showUnmaskedId"
                        :title="showUnmaskedId ? 'Mask National ID' : 'Reveal National ID'"
                      >
                        <CxIcon :name="showUnmaskedId ? 'eye-off' : 'eye'" class="size-3.5" />
                        <span>{{ showUnmaskedId ? 'Mask' : 'Reveal' }}</span>
                      </button>
                    </div>
                  </div>

                  <div class="grid gap-2.5 text-xs sm:grid-cols-2">
                    <div class="min-w-0 rounded-cx-sm bg-cx-well border border-cx-border-soft p-3">
                      <span class="text-cx-ink-3 block text-[11px] font-medium">Verification source</span>
                      <strong class="text-cx-ink block font-semibold mt-0.5 break-words">{{ userProfile.national_id_verified ? 'IPRS and Client Registry' : 'Not verified yet' }}</strong>
                    </div>
                    <div class="min-w-0 rounded-cx-sm bg-cx-well border border-cx-border-soft p-3">
                      <span class="text-cx-ink-3 block text-[11px] font-medium">HFR Licence Reference</span>
                      <strong class="text-cx-ink block font-semibold mt-0.5 break-words">
                        {{ userProfile.hfr_owner_licence || userProfile.hfr_registration_number || 'Not recorded' }}
                      </strong>
                    </div>
                  </div>
                </div>

                <div v-if="userProfile.national_id" class="rounded-cx-sm border border-cx-border bg-cx-well p-3 text-xs leading-relaxed text-cx-ink-2 flex items-start gap-2" data-testid="profile-id-note">
                  <CxIcon :name="userProfile.national_id_verified ? 'check-circle' : 'info'" class="size-4 shrink-0 mt-0.5" />
                  <span>{{ userProfile.national_id_verified ? 'This identity is verified and can administer the facilities connected to your account.' : 'Your ID is on file. It is used to find facilities you own on the Health Facility Registry.' }}</span>
                </div>

                <div class="pt-2 border-t border-cx-border-soft flex items-center justify-between">
                  <button
                    type="button"
                    class="text-xs font-semibold text-cx-brand hover:underline"
                    @click="openEditProfileModal()"
                  >
                    Update Identification Number →
                  </button>
                </div>
              </div>

              <!-- Card 2: Legal Organization & Identity -->
              <div class="rounded-cx border border-cx-border bg-cx-surface p-6 shadow-cx space-y-4">
                <div class="flex items-center justify-between pb-3 border-b border-cx-border-soft">
                  <div class="flex items-center gap-2">
                    <span class="grid size-7 place-items-center rounded-cx-sm bg-cx-brand-soft text-cx-brand-ink">
                      <CxIcon name="hospital" class="size-4" />
                    </span>
                    <div>
                      <span class="text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink-3 block">Organization & Account</span>
                      <span class="text-sm font-bold text-cx-ink">Enterprise Details</span>
                    </div>
                  </div>
                  <span class="rounded-full bg-cx-brand-soft text-cx-brand-ink border border-cx-brand-soft-border px-2.5 py-0.5 text-[11px] font-semibold">
                    Primary Account
                  </span>
                </div>

                <div class="space-y-3 text-xs">
                  <div class="rounded-cx-sm bg-cx-well border border-cx-border-soft p-3.5 space-y-1">
                    <span class="text-cx-ink-3 font-medium block text-[11px]">Parent Legal Organization / Customer</span>
                    <div class="flex items-center justify-between">
                      <strong class="font-bold text-base text-cx-ink block">{{ userProfile.organization || primaryOrganizationName }}</strong>
                      <button
                        type="button"
                        class="text-[11px] font-semibold text-cx-brand hover:underline"
                        @click="openEditProfileModal()"
                      >
                        Edit
                      </button>
                    </div>
                  </div>

                  <div class="grid grid-cols-2 gap-2 text-xs">
                    <div class="rounded-cx-sm bg-cx-well border border-cx-border-soft p-3">
                      <span class="text-cx-ink-3 block text-[11px] font-medium">Primary Network</span>
                      <strong class="text-cx-ink block font-semibold truncate mt-0.5">{{ partnerName(userProfile.primary_network) || 'Not linked to a partner' }}</strong>
                    </div>
                    <div class="rounded-cx-sm bg-cx-well border border-cx-border-soft p-3">
                      <span class="text-cx-ink-3 block text-[11px] font-medium">Managed Facilities</span>
                      <strong class="text-cx-ink block font-semibold mt-0.5">{{ allFacilities.length }} connected</strong>
                    </div>
                  </div>

                  <div class="rounded-cx-sm bg-cx-well border border-cx-border-soft p-3.5 space-y-1.5">
                    <span class="text-cx-ink-3 font-medium block text-[11px]">Account Contact & Communications</span>
                    <strong class="text-cx-ink block font-semibold text-sm">{{ userProfile.full_name || context.user }}</strong>
                    <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-cx-ink-2">
                      <span class="inline-flex items-center gap-1 font-mono text-[11px]">
                        <CxIcon name="inbox" class="size-3 text-cx-ink-3" />
                        {{ userProfile.email }}
                      </span>
                      <span class="inline-flex items-center gap-1 font-mono text-[11px]">
                        <CxIcon name="phone" class="size-3 text-cx-ink-3" />
                        {{ userProfile.mobile_no || 'Phone not set' }}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Connected Facilities Portfolio Strip -->
            <div class="rounded-cx border border-cx-border bg-cx-surface p-6 shadow-cx space-y-4">
              <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                <div>
                  <h3 class="text-base font-bold text-cx-ink">Connected Facility Portfolio</h3>
                  <p class="text-xs text-cx-ink-3">Facilities linked to your account across all networks.</p>
                </div>
                <button
                  type="button"
                  class="text-xs font-semibold text-cx-brand hover:underline inline-flex items-center gap-1"
                  @click="activeView = 'facilities'"
                >
                  <span>View all facilities ({{ allFacilities.length }})</span>
                  <CxIcon name="arrow-right" class="size-3.5" />
                </button>
              </div>

              <div class="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(min(100%,15rem),1fr))]">
                <div
                  v-for="facility in allFacilities.slice(0, 6)"
                  :key="facility.mfl_code || facility.facility_name"
                  class="rounded-cx-sm border border-cx-border bg-cx-well p-3.5 space-y-2 hover:border-cx-brand transition cursor-pointer"
                  @click="openFacilityDrawer(facility)"
                >
                  <div class="min-w-0">
                    <h4 class="line-clamp-2 break-words text-xs font-bold text-cx-ink" :title="facility.facility_name">{{ facility.facility_name }}</h4>
                    <span class="mt-1 inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold bg-cx-surface text-cx-ink-2 border border-cx-border-soft">
                      {{ facility.keph_level }}
                    </span>
                  </div>
                  <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-cx-ink-3">
                    <span class="font-mono">Facility ID {{ facilityId(facility) || 'not linked yet' }}</span>
                    <span v-if="facility.mfl_code" class="font-mono">MFL {{ facility.mfl_code }}</span>
                    <span class="ml-auto font-medium" :class="tokenBalance(facility).known ? 'text-cx-success-ink' : 'text-cx-ink-3'" data-testid="facility-card-tokens">
                      {{ tokenBalanceText(facility, ' tokens') }}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          </template>
        </main>

        <Transition
          enter-active-class="transition duration-200 ease-out"
          enter-from-class="opacity-0"
          enter-to-class="opacity-100"
          leave-active-class="transition duration-150 ease-in"
          leave-from-class="opacity-100"
          leave-to-class="opacity-0"
        >
          <div v-if="supportDrawerOpen" class="fixed inset-0 z-[70]">
            <button type="button" class="absolute inset-0 size-full cursor-default bg-cx-ink/35 backdrop-blur-sm" aria-label="Close network support" @click="closeNetworkSupportDrawer" />
            <aside
              class="cx-glass-panel absolute inset-y-0 right-0 flex w-full max-w-xl flex-col border-l border-cx-border bg-cx-surface/90 shadow-cx-raised backdrop-blur-2xl"
              role="dialog"
              aria-modal="true"
              aria-labelledby="network-support-title"
            >
              <header class="flex items-start justify-between gap-4 border-b border-cx-border-soft px-5 py-5 sm:px-7">
                <div>
                  <p class="text-[10px] font-semibold uppercase tracking-[0.12em] text-cx-ink-3">CareVerse partner network</p>
                  <h2 id="network-support-title" class="mt-1 text-xl font-bold tracking-tight text-cx-ink">Network Support</h2>
                  <p class="mt-1 text-xs leading-relaxed text-cx-ink-3">Configured contacts for your network, available while you stay on this page.</p>
                </div>
                <button type="button" class="grid size-9 shrink-0 place-items-center rounded-cx-sm border border-cx-border bg-cx-surface text-cx-ink-2 transition hover:bg-cx-well" aria-label="Close network support" @click="closeNetworkSupportDrawer">
                  <CxIcon name="x" class="size-4" />
                </button>
              </header>

              <div class="min-h-0 flex-1 space-y-4 overflow-y-auto p-4 sm:p-6">
                <div v-if="supportDrawerFacility" class="rounded-cx border border-cx-brand-soft-border bg-cx-brand-soft/70 p-4">
                  <p class="text-[10px] font-semibold uppercase tracking-wide text-cx-brand-ink">Facility you’re viewing</p>
                  <p class="mt-1 text-sm font-bold text-cx-ink">{{ supportDrawerFacility.facility_name }}</p>
                  <p class="mt-1 text-xs text-cx-ink-2">{{ supportDrawerFacility.network }}<span v-if="facilityId(supportDrawerFacility)"> · Facility ID {{ facilityId(supportDrawerFacility) }}</span><span v-if="supportDrawerFacility.mfl_code"> · MFL {{ supportDrawerFacility.mfl_code }}</span></p>
                </div>

                <article v-for="network in networkSupportGroups" :key="network.key" class="rounded-cx border border-cx-border bg-cx-surface/80 p-5 shadow-cx">
                  <div class="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h3 class="text-base font-bold text-cx-ink">{{ network.name }}</h3>
                      <p v-if="network.partnerId" class="mt-1 text-[11px] text-cx-ink-3">Partner ID <span class="font-mono font-semibold text-cx-ink-2">{{ network.partnerId }}</span></p>
                    </div>
                    <span class="rounded-full border border-cx-border bg-cx-well px-2.5 py-1 text-[10px] font-medium text-cx-ink-3">{{ network.facilities.length }} {{ network.facilities.length === 1 ? 'facility' : 'facilities' }}</span>
                  </div>

                  <div class="mt-4 space-y-3">
                    <div v-if="network.contactEmail" class="flex items-center justify-between gap-3 rounded-cx-sm border border-cx-border-soft bg-cx-well/70 p-3">
                      <div>
                        <p class="text-[10px] font-semibold uppercase tracking-wide text-cx-ink-3">Network support</p>
                        <a :href="`mailto:${network.contactEmail}`" class="mt-1 inline-flex text-sm font-semibold text-cx-brand hover:underline">{{ network.contactEmail }}</a>
                      </div>
                      <a :href="`mailto:${network.contactEmail}`" class="rounded-cx-sm border border-cx-border bg-cx-surface px-3 py-2 text-[11px] font-semibold text-cx-ink-2 hover:bg-cx-well">Email</a>
                    </div>

                    <div v-if="network.coordinators.length" class="space-y-2">
                      <p class="text-[10px] font-semibold uppercase tracking-wide text-cx-ink-3">Network coordinators</p>
                      <div v-for="person in network.coordinators" :key="person.email || person.name" class="rounded-cx-sm border border-cx-border-soft bg-cx-well/70 p-3">
                        <p class="text-sm font-semibold text-cx-ink">{{ person.name }}</p>
                        <div class="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs">
                          <a v-if="person.email" :href="`mailto:${person.email}`" class="text-cx-brand hover:underline">{{ person.email }}</a>
                          <a v-if="person.phone" :href="`tel:${person.phone}`" class="text-cx-ink-2 hover:text-cx-brand">{{ person.phone }}</a>
                        </div>
                      </div>
                    </div>

                    <p v-if="network.deliveryPartner" class="rounded-cx-sm bg-cx-well/60 px-3 py-2 text-xs text-cx-ink-2">
                      Technology delivery partner: <strong>{{ network.deliveryPartner }}<span v-if="network.deliveryPartnerShortName"> ({{ network.deliveryPartnerShortName }})</span></strong>
                    </p>
                    <p v-if="!network.contactEmail && !network.coordinators.length" class="rounded-cx-sm border border-cx-warning-border bg-cx-warning-soft/70 p-3 text-xs leading-relaxed text-cx-warning-ink">
                      Support contacts have not been configured for this network. Contact your network administrator to add them.
                    </p>
                    <p v-if="network.facilities.length" class="text-[11px] leading-relaxed text-cx-ink-3">
                      Supports: {{ network.facilities.slice(0, 4).join(', ') }}<span v-if="network.facilities.length > 4"> and {{ network.facilities.length - 4 }} more</span>
                    </p>
                  </div>
                </article>

                <div v-if="!networkSupportGroups.length" class="rounded-cx border border-cx-border bg-cx-surface/80 p-6 text-center shadow-cx">
                  <span class="mx-auto grid size-11 place-items-center rounded-full bg-cx-well text-cx-ink-3"><CxIcon name="chat" class="size-5" /></span>
                  <h3 class="mt-3 text-sm font-bold text-cx-ink">No network contacts found</h3>
                  <p class="mt-1 text-xs leading-relaxed text-cx-ink-3">Your facilities are not linked to a configured Opt-In Network support contact yet.</p>
                </div>
              </div>
            </aside>
          </div>
        </Transition>

        <nav
          class="cx-glass-chrome fixed inset-x-0 bottom-0 z-40 grid grid-cols-5 border-t border-cx-border px-2 pt-2 md:hidden"
          style="padding-bottom: max(0.5rem, env(safe-area-inset-bottom))"
          aria-label="Primary navigation"
        >
          <button v-for="tab in [
            { view: 'dashboard', label: 'Home', icon: 'dashboard' },
            { view: 'facilities', label: 'Facilities', icon: 'hospital' },
            { view: 'billing', label: 'Billing', icon: 'credit-card' },
            { view: 'profile', label: 'Profile', icon: 'user' },
          ]" :key="tab.view" type="button"
            class="flex min-h-12 flex-col items-center justify-center gap-0.5 rounded-cx-sm text-[10px] font-semibold transition"
            :class="(activeView === tab.view || (tab.view === 'facilities' && activeView === 'facility_detail')) ? 'text-cx-brand' : 'text-cx-ink-3'"
            :aria-current="(activeView === tab.view || (tab.view === 'facilities' && activeView === 'facility_detail')) ? 'page' : undefined"
            @click="selectMobileView(tab.view)"
          >
            <CxIcon :name="tab.icon" class="size-5" />
            <span>{{ tab.label }}</span>
          </button>
          <button type="button"
            class="flex min-h-12 flex-col items-center justify-center gap-0.5 rounded-cx-sm text-[10px] font-semibold transition"
            :class="mobileMoreOpen ? 'text-cx-brand' : 'text-cx-ink-3'"
            :aria-expanded="mobileMoreOpen"
            aria-label="More navigation options"
            @click="mobileMoreOpen = !mobileMoreOpen"
          >
            <CxIcon name="menu" class="size-5" />
            <span>More</span>
          </button>
          <div v-if="mobileMoreOpen" class="cx-glass-panel absolute bottom-full right-2 mb-2 w-56 rounded-cx border border-cx-border p-2 shadow-cx-raised">
            <button v-for="item in mobileMoreItems" :key="item.view" type="button"
              class="flex w-full items-center gap-2.5 rounded-cx-sm px-3 py-2.5 text-left text-xs font-semibold text-cx-ink-2 hover:bg-cx-well"
              @click="selectMobileView(item.view)"
            >
              <CxIcon :name="item.icon" class="size-4" />{{ item.label }}
            </button>
          </div>
        </nav>

      </div>
    </div>

    <!-- FACILITIES: SEARCH AND LINK FROM HEALTH FACILITY REGISTRY -->
    <Dialog
      v-model:open="addFacilityModalOpen"
      :title="__('Find and link a facility')"
      size="3xl"
    >
      <div class="p-1 space-y-5">
        <section class="rounded-cx-sm border border-cx-border bg-cx-well p-4">
          <div class="grid gap-3 sm:grid-cols-[minmax(0,1fr)_14rem] sm:items-end">
            <div>
              <label class="mb-1.5 block text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink-2" for="portfolio-partner-id">Partner ID <span class="font-normal normal-case text-cx-ink-4">(optional)</span></label>
              <input
                id="portfolio-partner-id"
                v-model="partnerIdInput"
                inputmode="numeric"
                maxlength="6"
                placeholder="Use configured default"
                class="w-full rounded-cx-sm border border-cx-border bg-cx-surface px-3.5 py-2.5 text-sm font-medium text-cx-ink focus:border-cx-brand focus:outline-none"
              />
            </div>
            <p class="text-xs leading-relaxed text-cx-ink-3">Leave blank to use your configured partner ID.</p>
          </div>
        </section>
        <!-- Owner ID discovery is part of the same facility linking workflow. -->
        <section v-if="userProfile.masked_national_id" class="rounded-cx-sm border border-cx-brand-soft-border bg-cx-brand-soft p-4 space-y-3">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 class="font-semibold text-sm text-cx-brand-ink">Find facilities registered to your ID</h3>
              <p class="mt-1 text-xs text-cx-brand-ink">Search using the ID on your profile: <span class="font-mono font-semibold">{{ userProfile.masked_national_id }}</span></p>
            </div>
            <button
              type="button"
              class="rounded-cx-sm bg-cx-brand px-3.5 py-2 text-xs font-semibold text-cx-contrast hover:bg-cx-brand-strong transition disabled:opacity-50"
              :disabled="hfrOwnerSearchBusy"
              @click="discoverFacilitiesByOwnerId()"
            >
              {{ hfrOwnerSearchBusy ? 'Searching…' : 'Find my facilities' }}
            </button>
          </div>
          <p v-if="hfrOwnerSearchComplete && hfrOwnerSearchError" class="rounded-cx-sm border border-cx-danger-border bg-cx-danger-soft p-3 text-xs text-cx-danger-ink" role="alert">{{ hfrOwnerSearchError }}</p>
          <p v-else-if="hfrOwnerSearchComplete && !hfrOwnerSearchResults.length" class="rounded-cx-sm border border-cx-border bg-cx-surface p-3 text-xs text-cx-ink-2" role="status">
            No facilities were found for this ID. You can search the registry by MFL code, FID, or registration number below.
          </p>
          <div v-if="hfrOwnerSearchResults.length" class="space-y-2 border-t border-cx-brand-soft-border pt-3">
            <p class="text-xs font-semibold text-cx-brand-ink">Facilities found ({{ hfrOwnerSearchResults.length }})</p>
            <div class="max-h-56 space-y-2 overflow-y-auto">
              <div v-for="candidate in hfrOwnerSearchResults" :key="candidate.facility_fid || candidate.mfl_code" class="flex flex-col gap-3 rounded-cx-sm border border-cx-border bg-cx-surface p-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p class="text-xs font-semibold text-cx-ink">{{ candidate.name }}</p>
                  <p class="mt-1 text-[11px] text-cx-ink-3">MFL {{ candidate.mfl_code }} · {{ candidate.level || 'Facility' }} · {{ candidate.county }}{{ candidate.subcounty ? ` / ${candidate.subcounty}` : '' }}</p>
                  <p class="mt-1 text-[11px] text-cx-ink-3">{{ candidate.facility_fid ? `Facility ID ${candidate.facility_fid}` : 'Facility ID will be resolved from the MFL code' }}</p>
                </div>
                <span v-if="candidate.already_linked || facilityAlreadyLinked(candidate)" class="shrink-0 rounded-full bg-cx-success-soft px-2.5 py-1 text-[11px] font-semibold text-cx-success-ink">In your portfolio</span>
                <button v-else type="button" class="shrink-0 rounded-cx-sm bg-cx-ink px-3 py-1.5 text-xs font-semibold text-cx-contrast hover:bg-cx-ink-hover disabled:opacity-50" :disabled="hfrLinkBusy" @click="linkHfrCandidate(candidate)">
                  {{ hfrLinkBusy ? 'Linking…' : 'Add to portfolio' }}
                </button>
              </div>
            </div>
          </div>
        </section>

        <section class="space-y-3">
          <div>
            <h3 class="text-sm font-semibold text-cx-ink">Search the Health Facility Registry</h3>
            <p class="mt-1 text-xs text-cx-ink-3">Enter a registry identifier. Your Facilities search only searches names in your current portfolio.</p>
          </div>
          <div class="grid gap-2 sm:grid-cols-[10rem_minmax(0,1fr)_auto]">
            <select
              v-model="hfrSearchBy"
              aria-label="Registry identifier type"
              class="w-full rounded-cx-sm border border-cx-border bg-cx-surface px-3 py-2 text-xs font-semibold text-cx-ink-2"
            >
              <option value="mfl_code">MFL Code</option>
              <option value="facility_fid">Facility ID</option>
              <option value="registration_number">Registration #</option>
            </select>
            <input
              type="text"
              v-model="hfrSearchQuery"
              :placeholder="hfrSearchBy === 'mfl_code' ? 'Enter MFL code' : hfrSearchBy === 'facility_fid' ? 'Enter HFR Facility ID' : 'Enter registration number'"
              class="min-w-0 rounded-cx-sm border border-cx-border bg-cx-surface px-3.5 py-2 text-xs font-medium text-cx-ink focus:outline-none focus:border-cx-brand"
              @keyup.enter="executeHfrSearch()"
            />
            <button
              type="button"
              class="rounded-cx-sm bg-cx-brand px-4 py-2 text-xs font-semibold text-cx-contrast hover:bg-cx-brand-strong disabled:opacity-50"
              :disabled="hfrSearchBusy || !hfrSearchQuery.trim()"
              @click="executeHfrSearch()"
            >
              {{ hfrSearchBusy ? 'Searching…' : 'Search' }}
            </button>
          </div>
          <p v-if="hfrSearchError" class="rounded-cx-sm border border-cx-danger-border bg-cx-danger-soft p-3 text-xs text-cx-danger-ink" role="alert">{{ hfrSearchError }}</p>
        </section>

        <!-- Search Results -->
        <div v-if="hfrSearchResults.length" class="space-y-2">
          <span class="text-xs font-semibold uppercase text-cx-ink-3">Matching Registry Records ({{ hfrSearchResults.length }})</span>
          <div class="space-y-2 max-h-60 overflow-y-auto">
            <div
              v-for="cand in hfrSearchResults"
              :key="cand.facility_fid || cand.mfl_code"
              class="rounded-cx-sm border p-3 flex items-center justify-between gap-3 hover:bg-cx-well transition"
              :class="facilityAlreadyLinked(cand) ? 'border-cx-success-border bg-cx-success-soft' : 'border-cx-border'"
            >
              <div>
                <span class="font-semibold text-xs text-cx-ink block">{{ cand.name }}</span>
                <span class="text-[11px] text-cx-ink-3"><template v-if="facilityId(cand)">Facility ID {{ facilityId(cand) }} · </template>MFL {{ cand.mfl_code }} · {{ cand.level || 'Facility' }} · {{ cand.county || 'County unavailable' }} · {{ cand.owner_type || 'Registry record' }}</span>
              </div>
              <span v-if="facilityAlreadyLinked(cand)" class="shrink-0 rounded-full bg-cx-success-soft px-2.5 py-1 text-[11px] font-semibold text-cx-success-ink">In your portfolio</span>
              <button v-else
                type="button"
                class="rounded-cx-sm bg-cx-ink px-3 py-1.5 text-xs font-semibold text-cx-contrast hover:bg-cx-ink-hover transition shrink-0 disabled:opacity-50"
                :disabled="hfrLinkBusy"
                @click="linkHfrCandidate(cand)"
              >
                {{ hfrLinkBusy ? 'Adding…' : 'Add to portfolio' }}
              </button>
            </div>
          </div>
        </div>
        <p v-else-if="hfrSearchComplete && !hfrSearchError" class="rounded-cx-sm border border-cx-border bg-cx-well p-4 text-xs text-cx-ink-2" role="status">
          No registry record matched that identifier. Check the number or choose another identifier type.
        </p>
      </div>
    </Dialog>

    <!-- MODAL 2: TOP-UP CAPACITY MODAL -->
    <Dialog
      v-model:open="topUpModalOpen"
      :title="topUpModalTitle"
      size="3xl"
    >
      <div class="p-1 space-y-5">
        <div v-if="topUpMode !== 'all'" class="cx-glass-panel rounded-cx-sm border border-cx-brand-soft-border bg-cx-brand-soft/50 p-3 text-xs leading-relaxed text-cx-ink-2">
          {{ topUpMode === 'free' ? 'Choose a no-charge package to create the facility token order for go-live planning.' : 'Choose a paid package to create a token order. The invoice and payment status will be available in Billing & Invoices.' }}
          The setup team reviews and submits the HMIS provisioning request separately.
        </div>
        <div>
          <label class="block text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink-2 mb-1.5">
            Target Facility
          </label>
          <select
            v-model="selectedFacilityMfl"
            class="w-full rounded-cx-sm border border-cx-border bg-cx-surface px-3.5 py-2.5 text-xs sm:text-sm font-semibold text-cx-ink shadow-cx focus:border-cx-brand"
          >
            <option v-if="allFacilities.length > 1" value="" disabled>
              Select a facility to top up…
            </option>
            <option
              v-for="fac in allFacilities"
              :key="fac.mfl_code"
              :value="fac.mfl_code"
            >
              {{ fac.facility_name }} ({{ facilityId(fac) ? `Facility ID ${facilityId(fac)} · ` : '' }}MFL {{ fac.mfl_code }}) · {{ tokenBalanceText(fac, ' tokens') }}
            </option>
          </select>
        </div>

        <div class="space-y-2">
          <span class="text-xs font-semibold uppercase text-cx-ink-2 block">{{ topUpMode === 'free' ? 'Select a free token package' : topUpMode === 'paid' ? 'Select a paid token package' : 'Select package' }}</span>
          <div class="grid gap-3" :class="compactPackageGridClass(visibleTopUpPackages.length)">
            <button
              v-for="pkg in visibleTopUpPackages"
              :key="pkg.item_code"
              type="button"
              :aria-pressed="selectedTopUpPackageCode === pkg.item_code"
              class="rounded-cx-sm border p-4 text-left cursor-pointer transition flex flex-col justify-between focus:outline-none focus-visible:ring-2 focus-visible:ring-cx-brand"
              :class="
                selectedTopUpPackageCode === pkg.item_code
                  ? 'border-2 border-cx-brand bg-cx-brand-soft ring-2 ring-cx-brand-soft'
                  : 'border-cx-border hover:border-cx-border bg-cx-surface'
              "
              @click="selectedTopUpPackageCode = pkg.item_code"
            >
              <div>
                <div class="flex items-center justify-between">
                  <span class="font-semibold text-sm text-cx-ink">{{ pkg.display_name }}</span>
                  <span class="font-semibold text-xs text-cx-brand-ink">
                    {{ Number(pkg.price_ex_vat ?? pkg.price ?? 0) === 0 ? 'Free' : money(pkg.gross_total || pkg.price, pkg.currency) }}
                  </span>
                </div>
                <div class="mt-2 text-xs font-semibold text-cx-ink"><CxIcon name="coins" class="inline-block size-4 align-[-0.15em]" /> {{ (pkg.token_quantity || 0).toLocaleString() }} Tokens</div>
                <p class="mt-1 text-[11px] text-cx-ink-3 leading-normal">{{ pkg.coverage_summary || pkg.description }}</p>
              </div>
              <div class="mt-3 pt-2 border-t border-cx-border-soft flex items-center justify-between text-[11px]">
                <span class="text-cx-ink-4">{{ Number(pkg.gross_total) > 0 ? `incl. ${pkg.vat_label || 'VAT'}` : 'No charge' }}</span>
                <span class="font-semibold" :class="selectedTopUpPackageCode === pkg.item_code ? 'text-cx-brand' : 'text-cx-ink-4'">
                  {{ selectedTopUpPackageCode === pkg.item_code ? 'Selected ✓' : 'Select' }}
                </span>
              </div>
            </button>
          </div>
        </div>

        <div class="pt-4 border-t border-cx-border-soft flex items-center justify-end gap-3">
          <button type="button" class="rounded-cx-sm border border-cx-border px-4 py-2 text-xs font-semibold text-cx-ink-3 hover:bg-cx-well" @click="topUpModalOpen = false">
            Cancel
          </button>
          <button
            type="button"
            class="rounded-cx-sm bg-cx-brand px-5 py-2.5 text-xs font-semibold text-cx-contrast shadow-cx hover:bg-cx-brand-strong disabled:opacity-50"
            :disabled="purchaseBusy || !selectedFacility || !selectedPackageObj"
            @click="executeTopUp()"
          >
            {{ purchaseBusy ? 'Generating Order…' : 'Confirm Order →' }}
          </button>
        </div>
      </div>
    </Dialog>

    <!-- MODAL: DRAFT ORDER REVIEW -->
    <Dialog v-model:open="orderReviewOpen" :title="orderReview ? `Review order ${orderReview.name}` : 'Review order'" size="2xl">
      <div class="p-1 space-y-5" data-testid="order-review">
        <p v-if="!orderReview && !orderReviewError" class="text-xs text-cx-ink-3">Loading order…</p>
        <template v-if="orderReview">
          <div class="rounded-cx-sm border border-cx-border bg-cx-well p-4 space-y-2">
            <div class="flex items-center justify-between text-xs">
              <span class="font-semibold text-cx-ink">{{ packageLabel(orderReview.package_item, context.token_packages) }}</span>
              <span class="text-cx-ink-3">For {{ facilityLabel(orderReview.facility_mfl, allFacilities) }}</span>
            </div>
            <div
              v-for="(row, index) in orderReview.items"
              :key="`${row.item_code}-${index}`"
              class="flex items-start justify-between gap-3 text-xs"
              :class="row.bonus_type ? 'text-cx-success-ink' : 'text-cx-ink-2'"
              :data-testid="row.bonus_type ? 'order-review-bonus' : 'order-review-line'"
            >
              <span>{{ row.bonus_type ? row.description : `${row.item_name || row.item_code} × ${row.qty}` }}</span>
              <span class="shrink-0 font-semibold">{{ row.bonus_type ? 'Free' : money(row.amount, orderReview.currency) }}</span>
            </div>
            <div v-for="tax in orderReview.taxes" :key="tax.description" class="flex items-center justify-between text-xs text-cx-ink-3">
              <span>{{ tax.description }}</span>
              <span>{{ money(tax.tax_amount, orderReview.currency) }}</span>
            </div>
            <div class="flex items-center justify-between border-t border-cx-border-soft pt-2 text-sm font-bold text-cx-ink">
              <span>Total</span>
              <span data-testid="order-review-total">{{ money(orderReview.grand_total, orderReview.currency) }}</span>
            </div>
            <p v-if="reviewBonusTokens && orderReview.package_tokens" data-testid="order-review-tokens" class="text-[11px] text-cx-ink-3">
              You pay for {{ orderReview.package_tokens.toLocaleString() }} tokens and receive
              {{ (orderReview.package_tokens + reviewBonusTokens).toLocaleString() }} once the invoice is paid.
            </p>
          </div>

          <div class="space-y-2">
            <label class="block text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink-2" for="review-kra-pin">KRA PIN</label>
            <input
              id="review-kra-pin"
              v-model="reviewForm.kra_pin"
              type="text"
              autocomplete="off"
              placeholder="A123456789Z"
              class="w-full rounded-cx-sm border border-cx-border bg-cx-surface px-3.5 py-2.5 font-mono text-sm uppercase text-cx-ink focus:border-cx-brand"
            />
            <p class="text-[11px] text-cx-ink-3">Required for the eTIMS tax invoice. Saved to your account for later orders.</p>
          </div>

          <div class="space-y-2">
            <span class="block text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink-2">Billing address</span>
            <select
              v-if="orderReview.addresses.length"
              v-model="reviewForm.billing_address"
              aria-label="Billing address"
              class="w-full rounded-cx-sm border border-cx-border bg-cx-surface px-3.5 py-2.5 text-sm text-cx-ink focus:border-cx-brand"
            >
              <option v-for="address in orderReview.addresses" :key="address.name" :value="address.name">
                {{ [address.address_line1, address.city, address.state].filter(Boolean).join(', ') }}
              </option>
              <option value="">Add a new billing address…</option>
            </select>
            <div v-if="!reviewForm.billing_address" class="grid gap-2 sm:grid-cols-2">
              <input v-model="reviewForm.address_line1" aria-label="Street address" placeholder="Street address / building" class="sm:col-span-2 rounded-cx-sm border border-cx-border bg-cx-surface px-3.5 py-2.5 text-sm text-cx-ink focus:border-cx-brand" />
              <input v-model="reviewForm.address_line2" aria-label="Address line 2" placeholder="P.O. Box / floor (optional)" class="sm:col-span-2 rounded-cx-sm border border-cx-border bg-cx-surface px-3.5 py-2.5 text-sm text-cx-ink focus:border-cx-brand" />
              <input v-model="reviewForm.city" aria-label="Town" placeholder="Town" class="rounded-cx-sm border border-cx-border bg-cx-surface px-3.5 py-2.5 text-sm text-cx-ink focus:border-cx-brand" />
              <input v-model="reviewForm.county" aria-label="County" placeholder="County (optional)" class="rounded-cx-sm border border-cx-border bg-cx-surface px-3.5 py-2.5 text-sm text-cx-ink focus:border-cx-brand" />
              <input v-model="reviewForm.postal_code" aria-label="Postal code" placeholder="Postal code (optional)" class="rounded-cx-sm border border-cx-border bg-cx-surface px-3.5 py-2.5 text-sm text-cx-ink focus:border-cx-brand" />
            </div>
          </div>

          <fieldset class="space-y-2">
            <legend class="block text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink-2">Order type</legend>
            <div class="grid gap-2 sm:grid-cols-2">
              <label
                v-for="option in [{ value: 'One-time', hint: 'Buy these tokens once.' }, { value: 'Recurring', hint: 'A new draft order is prepared for you each period.' }]"
                :key="option.value"
                class="flex cursor-pointer items-start gap-2 rounded-cx-sm border p-3 text-xs"
                :class="reviewForm.frequency === option.value ? 'border-cx-brand bg-cx-brand-soft' : 'border-cx-border bg-cx-surface'"
              >
                <input v-model="reviewForm.frequency" type="radio" name="order-frequency" :value="option.value" class="mt-0.5" />
                <span>
                  <span class="block font-semibold text-cx-ink">{{ option.value }}</span>
                  <span class="text-cx-ink-3">{{ option.hint }}</span>
                </span>
              </label>
            </div>
            <select
              v-if="reviewForm.frequency === 'Recurring'"
              v-model="reviewForm.recurrence_period"
              aria-label="Repeat every"
              class="w-full rounded-cx-sm border border-cx-border bg-cx-surface px-3.5 py-2.5 text-sm text-cx-ink focus:border-cx-brand"
            >
              <option value="Monthly">Every month</option>
              <option value="Quarterly">Every quarter</option>
              <option value="Yearly">Every year</option>
            </select>
          </fieldset>

          <ul v-if="reviewProblems.length" class="space-y-1 text-[11px] text-cx-ink-3">
            <li v-for="problem in reviewProblems" :key="problem">• {{ problem }}</li>
          </ul>
        </template>
        <p v-if="orderReviewError" class="rounded-cx-sm border border-cx-danger-border bg-cx-danger-soft p-3 text-xs text-cx-danger-ink">{{ orderReviewError }}</p>

        <div class="pt-4 border-t border-cx-border-soft flex items-center justify-end gap-3">
          <button type="button" class="rounded-cx-sm border border-cx-border px-4 py-2 text-xs font-semibold text-cx-ink-3 hover:bg-cx-well" @click="orderReviewOpen = false">
            Cancel
          </button>
          <button
            type="button"
            class="rounded-cx-sm bg-cx-brand px-5 py-2.5 text-xs font-semibold text-cx-contrast shadow-cx hover:bg-cx-brand-strong disabled:opacity-50"
            :disabled="orderReviewBusy || !orderReview || reviewProblems.length > 0"
            @click="confirmOrderReview()"
          >
            {{ orderReviewBusy ? 'Generating invoice…' : 'Confirm order & generate invoice' }}
          </button>
        </div>
      </div>
    </Dialog>

    <!-- MODAL 3: SIZING CALCULATOR -->
    <Dialog
      v-model:open="calculatorModalOpen"
      :title="__('CareVerse Token Sizing Calculator')"
      size="4xl"
    >
      <div class="p-1 max-h-[80vh] overflow-y-auto">
        <TokenCalculator
          :packages="context.token_packages"
          :config="context.calculator_config"
          :selected-package-code="selectedTopUpPackageCode"
          :facility-name="selectedFacility?.facility_name"
          context="portal"
          @select-package="(code) => (selectedTopUpPackageCode = code)"
          @apply-plan="onCalculatorApplyPlan"
        />
      </div>
    </Dialog>

    <!-- MODAL 4: CHOOSE PAYMENT METHOD -->
    <Dialog
      v-model:open="mpesaModalOpen"
      :title="__('Choose payment method')"
      size="2xl"
    >
      <div class="p-1 space-y-5">
        <!-- Top M-Pesa Branding Header -->
        <div class="rounded-cx bg-cx-success text-cx-contrast p-4 shadow-cx flex items-center justify-between">
          <div class="flex items-center gap-3">
            <div class="size-10 rounded-cx-sm bg-cx-surface text-cx-success-ink flex items-center justify-center font-bold text-base shadow-cx">
              M
            </div>
            <div>
              <span class="font-semibold text-sm tracking-tight block">Lipa na M-Pesa · Paybill</span>
              <span class="text-xs text-cx-contrast block">Pay by Paybill, then submit the confirmation code for verification</span>
            </div>
          </div>
          <span class="rounded-full bg-emerald-800/80 border border-emerald-500/50 px-2.5 py-1 text-[11px] font-semibold">
            M-Pesa Paybill
          </span>
        </div>
        <p class="text-xs text-cx-ink-3">
          Pay with M-Pesa using the details below, or choose card checkout with Paystack at the bottom.
        </p>

        <!-- 3 Copyable Cards Grid -->
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <!-- 1. Paybill Number -->
          <div class="rounded-cx-sm border border-cx-border bg-cx-band p-3 flex flex-col justify-between">
            <span class="text-[11px] font-semibold uppercase tracking-[0.08em] text-cx-ink-3 block">Business No</span>
            <div class="mt-1">
              <span class="font-mono text-lg font-bold text-cx-ink block leading-tight">{{ paybillInfo.business_number }}</span>
              <span class="text-[11px] text-cx-ink-3 block truncate">{{ paybillInfo.business_name }}</span>
            </div>
            <button
              type="button"
              class="mt-2.5 w-full rounded-cx-sm border border-cx-border bg-cx-surface py-1 px-2 text-xs font-semibold text-cx-ink-2 hover:bg-cx-well transition inline-flex items-center justify-center gap-1 disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="!paybillInfo.business_number"
              @click="copyText(paybillInfo.business_number, 'paybill_biz')"
            >
              <span><CxIcon :name="copiedKey === 'paybill_biz' ? 'check' : 'copy'" class="mr-1 inline-block size-4 align-[-0.15em]" />{{ copiedKey === 'paybill_biz' ? 'Copied' : 'Copy' }}</span>
            </button>
          </div>

          <!-- 2. Account Number -->
          <div class="rounded-cx-sm border border-cx-border bg-cx-band p-3 flex flex-col justify-between">
            <span class="text-[11px] font-semibold uppercase tracking-[0.08em] text-cx-ink-3 block">Account No</span>
            <div class="mt-1">
              <span class="font-mono text-sm font-semibold text-cx-ink block truncate leading-tight">{{ mpesaInvoice?.name }}</span>
              <span class="text-[11px] text-cx-ink-3 block">Invoice Reference</span>
            </div>
            <button
              type="button"
              class="mt-2.5 w-full rounded-cx-sm border border-cx-border bg-cx-surface py-1 px-2 text-xs font-semibold text-cx-ink-2 hover:bg-cx-well transition inline-flex items-center justify-center gap-1"
              @click="copyText(mpesaInvoice?.name, 'paybill_acc')"
            >
              <span><CxIcon :name="copiedKey === 'paybill_acc' ? 'check' : 'copy'" class="mr-1 inline-block size-4 align-[-0.15em]" />{{ copiedKey === 'paybill_acc' ? 'Copied' : 'Copy' }}</span>
            </button>
          </div>

          <!-- 3. Exact Amount -->
          <div class="rounded-cx-sm border border-cx-border bg-cx-band p-3 flex flex-col justify-between">
            <span class="text-[11px] font-semibold uppercase tracking-[0.08em] text-cx-ink-3 block">Amount Due</span>
            <div class="mt-1">
              <span class="font-mono text-lg font-bold text-cx-success-ink block leading-tight">{{ money(mpesaInvoice?.amount || mpesaInvoice?.outstanding_amount, mpesaInvoice?.currency) }}</span>
              <span class="text-[11px] text-cx-ink-3 block">Invoice currency: {{ mpesaInvoice?.currency || 'KES' }}</span>
            </div>
            <button
              type="button"
              class="mt-2.5 w-full rounded-cx-sm border border-cx-border bg-cx-surface py-1 px-2 text-xs font-semibold text-cx-ink-2 hover:bg-cx-well transition inline-flex items-center justify-center gap-1"
              @click="copyText(Math.round(mpesaInvoice?.amount || mpesaInvoice?.outstanding_amount || 0), 'paybill_amt')"
            >
              <span><CxIcon :name="copiedKey === 'paybill_amt' ? 'check' : 'copy'" class="mr-1 inline-block size-4 align-[-0.15em]" />{{ copiedKey === 'paybill_amt' ? 'Copied' : 'Copy' }}</span>
            </button>
          </div>
        </div>

        <!-- Step-by-step instructions -->
        <div class="rounded-cx-sm bg-cx-well border border-cx-border-soft p-4 space-y-1.5 text-xs text-cx-ink-3">
          <strong class="text-cx-ink font-bold block mb-1">Pay this invoice by M-Pesa Paybill:</strong>
          <p>1. Open SIM Toolkit or M-Pesa App &gt; <strong>Lipa na M-Pesa</strong> &gt; <strong>Paybill</strong></p>
          <p>2. Enter Business Number <strong>{{ paybillInfo.business_number }}</strong> ({{ paybillInfo.business_name }})</p>
          <p>3. Enter Account Number <strong>{{ mpesaInvoice?.name }}</strong></p>
          <p>4. Enter Amount <strong>{{ money(mpesaInvoice?.amount || mpesaInvoice?.outstanding_amount, mpesaInvoice?.currency) }}</strong></p>
          <p>5. Enter your M-Pesa PIN and confirm payment</p>
        </div>

        <!-- M-Pesa Transaction Input Form -->
        <div class="space-y-3 pt-2 border-t border-cx-border-soft">
          <div>
            <label for="cx-mpesa-code" class="block text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink">After paying, enter your M-Pesa confirmation code</label>
            <p class="mt-1 text-[11px] text-cx-ink-3">Your invoice stays open until the payment is verified. Do not submit a code before completing the Paybill payment.</p>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <input
                type="text"
                id="cx-mpesa-code"
                v-model="mpesaCodeInput"
                placeholder="e.g. SB65A1TU7X"
                maxlength="15"
                class="w-full rounded-cx-sm border border-cx-border bg-cx-surface px-3.5 py-2.5 text-xs font-mono font-semibold uppercase tracking-[0.08em] text-cx-ink focus:outline-none focus:border-emerald-600 focus:ring-2 focus:ring-emerald-500/10 placeholder:text-cx-ink-4 placeholder:normal-case placeholder:font-sans"
              />
              <span class="text-[11px] text-cx-ink-4 mt-1 block">10-character code from Safaricom SMS</span>
            </div>
            <div>
              <input
                type="tel"
                v-model="mpesaPhoneInput"
                aria-label="Phone number used for the M-Pesa transaction"
                placeholder="M-Pesa Phone (e.g. 0712 345 678)"
                class="w-full rounded-cx-sm border border-cx-border bg-cx-surface px-3.5 py-2.5 text-xs font-medium text-cx-ink focus:outline-none focus:border-emerald-600 focus:ring-2 focus:ring-emerald-500/10"
              />
              <span class="text-[11px] text-cx-ink-4 mt-1 block">Phone used for the M-Pesa transaction</span>
            </div>
          </div>
        </div>

        <!-- Actions -->
        <div class="pt-4 border-t border-cx-border-soft flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <button
            type="button"
            class="text-xs font-semibold text-cx-ink-3 hover:text-cx-brand underline text-left"
            @click="payInvoice(mpesaInvoice); mpesaModalOpen = false"
          >
            Pay by card with Paystack →
          </button>
          <div class="flex items-center gap-2 justify-end">
            <button
              type="button"
              class="rounded-cx-sm border border-cx-border px-4 py-2 text-xs font-semibold text-cx-ink-3 hover:bg-cx-well"
              @click="mpesaModalOpen = false"
            >
              Cancel
            </button>
            <button
              type="button"
              class="rounded-cx-sm bg-cx-success px-5 py-2.5 text-xs font-semibold text-cx-contrast shadow-cx hover:bg-cx-success disabled:opacity-50 transition"
              :disabled="mpesaReportBusy || !mpesaCodeInput"
              @click="submitMpesaPayment()"
            >
              {{ mpesaReportBusy ? 'Submitting…' : 'Submit M-Pesa reference →' }}
            </button>
          </div>
        </div>
      </div>
    </Dialog>

    <!-- MODAL 5: EDIT PROFILE & SETTINGS -->
    <Dialog
      v-model:open="profileModalOpen"
      :title="__('Edit Profile & Account Settings')"
      size="xl"
    >
      <div class="p-1 space-y-4">
        <div>
          <label class="block text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink-2 mb-1.5">
            Full Legal Name (Account Holder)
          </label>
          <input
            type="text"
            v-model="profileForm.full_name"
            placeholder="e.g. Dr. Amina Otieno"
            class="w-full rounded-cx-sm border border-cx-border px-3.5 py-2 text-xs font-medium text-cx-ink focus:outline-none focus:border-cx-brand"
          />
          <p class="text-[11px] text-cx-ink-3 mt-1">
            The legal individual account holder whose credentials manage this facility portfolio.
          </p>
        </div>

        <div>
          <label class="block text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink-2 mb-1.5">
            Legal Organization / Practice Name
          </label>
          <input
            type="text"
            v-model="profileForm.organization"
            placeholder="e.g. Nairobi Healthcare Group"
            class="w-full rounded-cx-sm border border-cx-border px-3.5 py-2 text-xs font-medium text-cx-ink focus:outline-none focus:border-cx-brand"
          />
          <p class="text-[11px] text-cx-ink-3 mt-1">
            Display name for your practice or group across invoices and customer records.
          </p>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label class="block text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink-2 mb-1.5">
              Identification Document
            </label>
            <input
              type="text"
              v-model="profileForm.identification_type"
              placeholder="e.g. National ID"
              class="w-full rounded-cx-sm border border-cx-border px-3.5 py-2 text-xs font-medium text-cx-ink focus:outline-none focus:border-cx-brand"
            />
          </div>

          <div>
            <label class="block text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink-2 mb-1.5">
              Identification Number
            </label>
            <input
              type="text"
              v-model="profileForm.national_id"
              placeholder="6 to 10 digit National ID"
              maxlength="10"
              class="w-full rounded-cx-sm border border-cx-border px-3.5 py-2 text-xs font-mono font-semibold text-cx-ink focus:outline-none focus:border-cx-brand"
            />
          </div>
        </div>
        <p class="text-[11px] text-cx-ink-3">
          Used to securely verify ownership and auto-discover facilities licensed under your profile in the official Health Facility Registry.
        </p>

        <div>
          <label class="block text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink-2 mb-1.5">
            Verified Mobile Phone
          </label>
          <input
            type="tel"
            v-model="profileForm.mobile_no"
            placeholder="e.g. 0712345678"
            class="w-full rounded-cx-sm border border-cx-border px-3.5 py-2 text-xs font-medium text-cx-ink focus:outline-none focus:border-cx-brand"
          />
          <p class="text-[11px] text-cx-ink-3 mt-1">
            Primary mobile number for SMS OTP security checks and token top-up confirmations.
          </p>
        </div>

        <div class="pt-4 border-t border-cx-border-soft flex items-center justify-end gap-3">
          <button
            type="button"
            class="rounded-cx-sm border border-cx-border px-4 py-2 text-xs font-semibold text-cx-ink-3 hover:bg-cx-well"
            @click="profileModalOpen = false"
          >
            Cancel
          </button>
          <button
            type="button"
            class="rounded-cx-sm bg-cx-brand px-5 py-2.5 text-xs font-semibold text-cx-contrast shadow-cx hover:bg-cx-brand-strong disabled:opacity-50 transition"
            :disabled="profileSaving"
            @click="saveUserProfile()"
          >
            {{ profileSaving ? 'Saving…' : 'Save Profile Details' }}
          </button>
        </div>
      </div>
    </Dialog>
  </div>
</template>
