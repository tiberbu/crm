<script setup>
import CxIcon from './components/CxIcon.vue'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { call, createResource, Dialog } from 'frappe-ui'
import TokenCalculator from '@/components/TokenCalculator.vue'
import FacilitySingleView from './FacilitySingleView.vue'
import OptInRequests from './OptInRequests.vue'
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

// Current Active Navigation View: 'dashboard' | 'facilities' | 'pricing' | 'billing' | 'profile' | 'support'
// The portal lands on the Dashboard — the at-a-glance portfolio story — and
// drills down from there instead of opening on the densest data table.
const activeView = ref('dashboard')

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
          network: fac.network || account.network || 'CareVerse Partner Network',
          membership_status: fac.membership_status || 'Active',
          go_live: Boolean(fac.go_live),
          deal: fac.deal || account.deal || '',
          customer: fac.customer || account.customer || '',
          organization: account.organization || account.customer || '',
          token_package: fac.token_package || '',
          token_quantity: Number(fac.token_quantity) || 0,
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
          network: submission.network_slug || 'CareVerse Partner Network',
          membership_status: fac.membership_status || 'Active',
          go_live: Boolean(fac.network_contact?.go_live),
          deal: '',
          customer: '',
          ois_name: submission.name,
          organization: submission.facility_signatory_name || submission.name,
          token_package: submission.progress?.package?.display_name || '',
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
      const matchName = fac.facility_name.toLowerCase().includes(q)
      if (!matchName) return false
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

// Facilities grouped by partner network
const facilitiesByNetwork = computed(() => {
  const map = new Map()
  for (const fac of filteredFacilities.value) {
    const net = fac.network || 'CareVerse Partner Network'
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
  return result
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

async function loadProvisioningStatus(mflCode) {
  const response = await call('crm.api.hfr.get_provisioning_status', { mfl_code: mflCode })
  return unwrap(response)
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
const totalTokenCount = computed(() =>
  allFacilities.value.reduce((sum, fac) => sum + (fac.token_quantity || 0), 0),
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
      network: ois.network || ois.network_slug || 'CareVerse Partner Network',
      signatory: ois.facility_signatory_name || '',
      contract: ois.contract || '',
      facilities: (ois.progress?.facilities || []).map((f) => ({
        name: f.facility_name,
        mfl_code: f.mfl_code,
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
      userProfile.value = data
      profileForm.value = {
        national_id: data.national_id || '',
        mobile_no: data.mobile_no || '',
        full_name: data.full_name || '',
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
    })
    const data = unwrap(res)
    if (data) {
      userProfile.value = data
      profileModalOpen.value = false
      notice.value = {
        tone: 'success',
        text: 'Profile and National ID updated successfully!',
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

function openTopUpModal(facility = null) {
  if (facility) {
    selectedFacilityMfl.value = facility.mfl_code
  } else if (allFacilities.value.length === 1) {
    selectedFacilityMfl.value = allFacilities.value[0].mfl_code
  } else if (!selectedFacilityMfl.value) {
    // Multiple facilities: user must explicitly pick one (PRD REQ-ARC-02)
    selectedFacilityMfl.value = ''
  }
  if (!selectedTopUpPackageCode.value && context.value.token_packages?.length) {
    selectedTopUpPackageCode.value = context.value.token_packages[0].item_code
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

function money(value, currency) {
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: currency || defaultCurrency.value || 'KES',
    maximumFractionDigits: 0,
  }).format(value || 0)
}

function unwrap(response) {
  return (
    response?.message?.data ||
    response?.data ||
    response?.message ||
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
      fid: candidate.fid,
      partner_id: partnerIdInput.value.trim(),
    })
    const payload = unwrap(res)

    addFacilityModalOpen.value = false
    notice.value = {
      tone: 'success',
      text: `Facility "${payload.facility_name}" (MFL: ${payload.mfl_code}) was linked to your enterprise account successfully!`,
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
})

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
              activeView === 'support'
                ? 'bg-cx-brand-soft text-cx-brand-ink shadow-cx'
                : 'text-cx-ink-3 hover:bg-cx-well hover:text-cx-ink'
            "
            @click="activeView = 'support'"
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
              placeholder="Search your facilities by name"
              aria-label="Search your facilities by name"
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
            :default-currency="defaultCurrency"
            :load-provisioning-status="loadProvisioningStatus"
            @back="closeFacilityDrawer"
            @open-top-up="openTopUpModal"
            @pay="openMpesaModal"
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
                    <table class="w-full text-left border-collapse text-xs">
                      <thead>
                        <tr class="border-b border-cx-border bg-cx-band text-[11px] font-semibold uppercase tracking-[0.08em] text-cx-ink-3">
                          <th class="py-3 px-4">Facility Name</th>
                          <th class="py-3 px-4">KEPH Level</th>
                          <th class="py-3 px-4">MFL Code</th>
                          <th class="py-3 px-4">Go-live readiness</th>
                          <th class="py-3 px-4">Plan & Recent Purchase</th>
                          <th class="py-3 px-4 text-right">Care Tokens</th>
                          <th class="py-3 px-4 text-right">Settlement & Actions</th>
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
                              <div>
                                <button
                                type="button"
                                class="block text-left font-bold text-cx-ink underline-offset-2 hover:text-cx-brand-strong hover:underline"
                                @click="openFacilityDrawer(facility)"
                              >
                                {{ facility.facility_name }}
                              </button>
                                <span class="inline-flex items-center gap-1 rounded-cx-sm bg-cx-well text-cx-ink-2 px-1.5 py-0.5 text-[11px] font-medium mt-0.5 border border-cx-border-soft">
                                  <span><CxIcon name="globe" class="inline-block size-4 align-[-0.15em]" /></span>
                                  <span>{{ facility.network }}</span>
                                </span>
                              </div>
                            </div>
                          </td>
                          <td class="py-3.5 px-4">
                            <span class="inline-flex items-center rounded-cx-sm bg-cx-well px-2 py-0.5 text-[11px] font-semibold text-cx-ink-2 border border-cx-border">
                              {{ facility.keph_level }}
                            </span>
                          </td>
                          <td class="py-3.5 px-4">
                            <button
                              type="button"
                              class="font-mono text-xs font-semibold text-cx-ink-2 hover:text-cx-brand inline-flex items-center gap-1.5 bg-cx-well px-2 py-0.5 rounded-cx-sm border border-cx-border-soft cursor-pointer"
                              @click="copyMfl(facility.mfl_code)"
                            >
                              <span>{{ facility.mfl_code }}</span>
                              <CxIcon :name="copiedMfl === facility.mfl_code ? 'check' : 'copy'" class="size-3.5 text-cx-ink-3" />
                            </button>
                          </td>
                          <td class="py-3.5 px-4">
                            <span
                              class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-semibold border"
                              :class="facility.go_live ? 'bg-cx-success-soft text-cx-success-ink border-cx-success-border' : 'bg-cx-warning-soft text-cx-warning-ink border-cx-warning-border'"
                            >
                              <span class="size-1.5 rounded-full" :class="facility.go_live ? 'bg-cx-success' : 'bg-amber-600'"></span>
                              <span>{{ facilityReadinessLabel(facility) }}</span>
                            </span>
                          </td>
                          <td class="py-3.5 px-4 font-medium text-cx-ink-2">
                            <span class="font-bold text-cx-ink block">{{ facility.token_package || 'No active plan' }}</span>
                            <span v-if="facility.recent_purchase" class="text-[11px] text-cx-ink-3 font-mono block mt-0.5">
                              {{ facility.recent_purchase.package_name }}: {{ money(facility.recent_purchase.amount, facility.recent_purchase.currency) }} · {{ facility.recent_purchase.date }}
                            </span>
                          </td>
                          <td class="py-3.5 px-4 text-right">
                            <span class="font-semibold text-cx-brand font-mono text-sm inline-flex items-center gap-1">
                              <span><CxIcon name="coins" class="inline-block size-4 align-[-0.15em]" /></span>
                              <span>{{ (facility.token_quantity || 0).toLocaleString() }}</span>
                            </span>
                          </td>
                          <td class="py-3.5 px-4 text-right">
                            <div class="flex items-center justify-end gap-1.5 flex-wrap">
                              <button
                                v-if="facility.invoice_summary?.has_outstanding && !pendingPaymentForFacility(facility)"
                                type="button"
                                class="rounded-cx-sm bg-cx-success px-2.5 py-1 text-xs font-semibold text-cx-contrast hover:bg-cx-success transition shadow-cx inline-flex items-center gap-1 shrink-0 cursor-pointer"
                                @click="openMpesaModalForFacility(facility)"
                                title="Pay outstanding invoice via M-Pesa"
                              >
                                <span><CxIcon name="phone" class="inline-block size-4 align-[-0.15em]" /> Pay M-Pesa: {{ money(facility.invoice_summary.outstanding_amount, facility.invoice_summary.currency) }} →</span>
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
                  <table class="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr class="border-b border-cx-border bg-cx-band text-[11px] font-semibold uppercase tracking-[0.08em] text-cx-ink-3">
                        <th class="py-3 px-4">Facility & Network</th>
                        <th class="py-3 px-4">KEPH Level</th>
                        <th class="py-3 px-4">MFL Code</th>
                        <th class="py-3 px-4">Go-live readiness</th>
                        <th class="py-3 px-4">Plan & Recent Purchase</th>
                        <th class="py-3 px-4 text-right">Care Tokens</th>
                        <th class="py-3 px-4 text-right">Settlement & Actions</th>
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
                            <div>
                              <button
                                type="button"
                                class="block text-left font-bold text-cx-ink underline-offset-2 hover:text-cx-brand-strong hover:underline"
                                @click="openFacilityDrawer(facility)"
                              >
                                {{ facility.facility_name }}
                              </button>
                              <span class="inline-flex items-center gap-1 rounded-cx-sm bg-cx-well text-cx-ink-2 px-1.5 py-0.5 text-[11px] font-medium mt-0.5 border border-cx-border-soft">
                                <span><CxIcon name="globe" class="inline-block size-4 align-[-0.15em]" /></span>
                                <span>{{ facility.network }}</span>
                              </span>
                            </div>
                          </div>
                        </td>

                        <!-- Level -->
                        <td class="py-3.5 px-4">
                          <span class="inline-flex items-center rounded-cx-sm bg-cx-well px-2 py-0.5 text-[11px] font-semibold text-cx-ink-2 border border-cx-border">
                            {{ facility.keph_level }}
                          </span>
                        </td>

                        <!-- MFL Code -->
                        <td class="py-3.5 px-4">
                          <button
                            type="button"
                            class="font-mono text-xs font-semibold text-cx-ink-2 hover:text-cx-brand inline-flex items-center gap-1.5 bg-cx-well px-2 py-0.5 rounded-cx-sm border border-cx-border-soft cursor-pointer"
                            @click="copyMfl(facility.mfl_code)"
                          >
                            <span>{{ facility.mfl_code }}</span>
                            <CxIcon :name="copiedMfl === facility.mfl_code ? 'check' : 'copy'" class="size-3.5 text-cx-ink-3" />
                          </button>
                        </td>

                        <!-- Status Badge -->
                        <td class="py-3.5 px-4">
                          <span
                            class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-semibold border"
                            :class="
                              facility.go_live
                                ? 'bg-cx-success-soft text-cx-success-ink border-cx-success-border'
                                : 'bg-cx-warning-soft text-cx-warning-ink border-cx-warning-border'
                            "
                          >
                            <span class="size-1.5 rounded-full" :class="facility.go_live ? 'bg-cx-success' : 'bg-amber-600'"></span>
                            <span>{{ facilityReadinessLabel(facility) }}</span>
                          </span>
                        </td>

                        <!-- Plan & Recent Purchase -->
                        <td class="py-3.5 px-4 font-medium text-cx-ink-2">
                          <span class="font-bold text-cx-ink block">{{ facility.token_package || 'No active plan' }}</span>
                          <span v-if="facility.recent_purchase" class="text-[11px] text-cx-ink-3 font-mono block mt-0.5">
                            {{ facility.recent_purchase.package_name }}: {{ money(facility.recent_purchase.amount, facility.recent_purchase.currency) }} · {{ facility.recent_purchase.date }}
                          </span>
                        </td>

                        <!-- Tokens -->
                        <td class="py-3.5 px-4 text-right">
                          <span class="font-semibold text-cx-brand font-mono text-sm inline-flex items-center gap-1">
                            <span><CxIcon name="coins" class="inline-block size-4 align-[-0.15em]" /></span>
                            <span>{{ (facility.token_quantity || 0).toLocaleString() }}</span>
                          </span>
                        </td>

                        <!-- Actions & Direct M-Pesa Settlement -->
                        <td class="py-3.5 px-4 text-right">
                          <div class="flex items-center justify-end gap-1.5 flex-wrap">
                            <button
                              v-if="facility.invoice_summary?.has_outstanding && !pendingPaymentForFacility(facility)"
                              type="button"
                              class="rounded-cx-sm bg-cx-success px-2.5 py-1 text-xs font-semibold text-cx-contrast hover:bg-cx-success transition shadow-cx inline-flex items-center gap-1 shrink-0 cursor-pointer"
                              @click="openMpesaModalForFacility(facility)"
                              title="Pay outstanding invoice via M-Pesa"
                            >
                              <span><CxIcon name="phone" class="inline-block size-4 align-[-0.15em]" /> Pay M-Pesa: {{ money(facility.invoice_summary.outstanding_amount, facility.invoice_summary.currency) }} →</span>
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
                  <span>Registry status is shown on each facility row</span>
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

                  <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    <article
                      v-for="facility in group.facilities"
                      :key="facility.mfl_code"
                      class="cx-glass-panel cursor-pointer rounded-cx border border-cx-border bg-cx-surface p-5 shadow-cx flex flex-col justify-between hover:border-cx-brand transition"
                      @click="openFacilityFromSurface($event, facility)"
                    >
                      <div>
                        <div class="flex items-start justify-between gap-2">
                          <div>
                            <button
                      type="button"
                      class="block text-left text-base font-bold text-cx-ink underline-offset-2 hover:text-cx-brand-strong hover:underline"
                      @click="openFacilityDrawer(facility)"
                    >
                      {{ facility.facility_name }}
                    </button>
                            <p class="text-xs text-cx-ink-3 mt-0.5">{{ facility.keph_level }} · MFL: {{ facility.mfl_code }}</p>
                            <span class="inline-flex items-center gap-1 rounded-cx-sm bg-cx-well text-cx-ink-2 px-1.5 py-0.5 text-[11px] font-medium mt-1 border border-cx-border-soft">
                              <span><CxIcon name="globe" class="inline-block size-4 align-[-0.15em]" /></span>
                              <span>{{ facility.network }}</span>
                            </span>
                          </div>
                          <span
                            class="rounded-full px-2 py-0.5 text-[11px] font-semibold border shrink-0"
                            :class="facility.go_live ? 'bg-cx-success-soft text-cx-success-ink border-cx-success-border' : 'bg-cx-warning-soft text-cx-warning-ink border-cx-warning-border'"
                          >
                            {{ facilityReadinessLabel(facility) }}
                          </span>
                        </div>

                        <div class="mt-4 rounded-cx-sm bg-cx-well border border-cx-border-soft p-3 space-y-1.5 text-xs">
                          <div class="flex justify-between text-cx-ink-3">
                            <span>Active Plan:</span>
                            <strong class="text-cx-ink">{{ facility.token_package || 'None' }}</strong>
                          </div>
                          <div v-if="facility.recent_purchase" class="flex justify-between text-cx-ink-3 text-[11px]">
                            <span>Recent Order:</span>
                            <span class="font-mono text-cx-ink">{{ money(facility.recent_purchase.amount, facility.recent_purchase.currency) }} ({{ facility.recent_purchase.date }})</span>
                          </div>
                          <div class="flex justify-between text-cx-ink-3">
                            <span>Token Runway:</span>
                            <strong class="text-cx-brand"><CxIcon name="coins" class="inline-block size-4 align-[-0.15em]" /> {{ (facility.token_quantity || 0).toLocaleString() }} tokens</strong>
                          </div>
                          <div v-if="facility.invoice_summary?.has_outstanding" class="flex justify-between items-center pt-1.5 border-t border-cx-border-soft">
                            <span class="font-bold text-cx-warning-ink">Due Balance:</span>
                            <strong class="font-bold text-cx-warning-ink">{{ money(facility.invoice_summary.outstanding_amount, facility.invoice_summary.currency) }}</strong>
                          </div>
                        </div>
                      </div>

                      <div class="mt-4 pt-3 border-t border-cx-border-soft space-y-2">
                        <button
                          v-if="facility.invoice_summary?.has_outstanding && !pendingPaymentForFacility(facility)"
                          type="button"
                          class="w-full rounded-cx-sm bg-cx-success px-3 py-2 text-xs font-semibold text-cx-contrast hover:bg-cx-success transition flex items-center justify-center gap-1.5 shadow-cx cursor-pointer"
                          @click="openMpesaModalForFacility(facility)"
                        >
                          <span><CxIcon name="phone" class="inline-block size-4 align-[-0.15em]" /> Pay M-Pesa: {{ money(facility.invoice_summary.outstanding_amount, facility.invoice_summary.currency) }} →</span>
                        </button>
                        <span v-else-if="facility.invoice_summary?.has_outstanding" class="block text-center text-[11px] font-semibold text-cx-warning-ink">
                          Payment verification pending
                        </span>
                        <div class="flex items-center gap-2">
                          <button
                            type="button"
                            class="flex-1 rounded-cx-sm bg-cx-ink px-3 py-2 text-xs font-semibold text-cx-contrast hover:bg-cx-ink-hover transition cursor-pointer"
                            @click="openTopUpModal(facility)"
                          >
                            + Top Up Tokens
                          </button>
                        </div>
                      </div>
                    </article>
                  </div>
                </div>
              </template>

              <!-- Render Flat Cards when not grouped -->
              <div v-else class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                <article
                  v-for="facility in filteredFacilities"
                  :key="facility.mfl_code"
                  class="cx-glass-panel cursor-pointer rounded-cx border border-cx-border bg-cx-surface p-5 shadow-cx flex flex-col justify-between hover:border-cx-brand transition"
                  @click="openFacilityFromSurface($event, facility)"
                >
                  <div>
                    <div class="flex items-start justify-between gap-2">
                      <div>
                        <button
                      type="button"
                      class="block text-left text-base font-bold text-cx-ink underline-offset-2 hover:text-cx-brand-strong hover:underline"
                      @click="openFacilityDrawer(facility)"
                    >
                      {{ facility.facility_name }}
                    </button>
                        <p class="text-xs text-cx-ink-3 mt-0.5">{{ facility.keph_level }} · MFL: {{ facility.mfl_code }}</p>
                        <span class="inline-flex items-center gap-1 rounded-cx-sm bg-cx-well text-cx-ink-2 px-1.5 py-0.5 text-[11px] font-medium mt-1 border border-cx-border-soft">
                          <span><CxIcon name="globe" class="inline-block size-4 align-[-0.15em]" /></span>
                          <span>{{ facility.network }}</span>
                        </span>
                      </div>
                      <span
                        class="rounded-full px-2 py-0.5 text-[11px] font-semibold border shrink-0"
                        :class="facility.go_live ? 'bg-cx-success-soft text-cx-success-ink border-cx-success-border' : 'bg-cx-warning-soft text-cx-warning-ink border-cx-warning-border'"
                      >
                        {{ facilityReadinessLabel(facility) }}
                      </span>
                    </div>

                    <div class="mt-4 rounded-cx-sm bg-cx-well border border-cx-border-soft p-3 space-y-1.5 text-xs">
                      <div class="flex justify-between text-cx-ink-3">
                        <span>Active Plan:</span>
                        <strong class="text-cx-ink">{{ facility.token_package || 'None' }}</strong>
                      </div>
                      <div v-if="facility.recent_purchase" class="flex justify-between text-cx-ink-3 text-[11px]">
                        <span>Recent Order:</span>
                        <span class="font-mono text-cx-ink">{{ money(facility.recent_purchase.amount, facility.recent_purchase.currency) }} ({{ facility.recent_purchase.date }})</span>
                      </div>
                      <div class="flex justify-between text-cx-ink-3">
                        <span>Token Runway:</span>
                        <strong class="text-cx-brand"><CxIcon name="coins" class="inline-block size-4 align-[-0.15em]" /> {{ (facility.token_quantity || 0).toLocaleString() }} tokens</strong>
                      </div>
                      <div v-if="facility.invoice_summary?.has_outstanding" class="flex justify-between items-center pt-1.5 border-t border-cx-border-soft">
                        <span class="font-bold text-cx-warning-ink">Due Balance:</span>
                        <strong class="font-bold text-cx-warning-ink">{{ money(facility.invoice_summary.outstanding_amount, facility.invoice_summary.currency) }}</strong>
                      </div>
                    </div>
                  </div>

                  <div class="mt-4 pt-3 border-t border-cx-border-soft space-y-2">
                    <button
                      v-if="facility.invoice_summary?.has_outstanding && !pendingPaymentForFacility(facility)"
                      type="button"
                      class="w-full rounded-cx-sm bg-cx-success px-3 py-2 text-xs font-semibold text-cx-contrast hover:bg-cx-success transition flex items-center justify-center gap-1.5 shadow-cx cursor-pointer"
                      @click="openMpesaModalForFacility(facility)"
                    >
                      <span><CxIcon name="phone" class="inline-block size-4 align-[-0.15em]" /> Pay M-Pesa: {{ money(facility.invoice_summary.outstanding_amount, facility.invoice_summary.currency) }} →</span>
                    </button>
                    <span v-else-if="facility.invoice_summary?.has_outstanding" class="block text-center text-[11px] font-semibold text-cx-warning-ink">
                      Payment verification pending
                    </span>
                    <div class="flex items-center gap-2">
                      <button
                        type="button"
                        class="flex-1 rounded-cx-sm bg-cx-ink px-3 py-2 text-xs font-semibold text-cx-contrast hover:bg-cx-ink-hover transition cursor-pointer"
                        @click="openTopUpModal(facility)"
                      >
                        + Top Up Tokens
                      </button>
                    </div>
                  </div>
                </article>
              </div>
            </div>
          </div>

          <!-- ============================================================== -->
          <!-- VIEW B: DASHBOARD / EXECUTIVE RUNWAY OVERVIEW                   -->
          <!-- ============================================================== -->
          <div v-if="activeView === 'dashboard'" class="space-y-6">
            <!-- Organization identity band: the legal parent entity owns the account -->
            <div class="cx-glass-panel rounded-cx border border-cx-border bg-cx-surface p-5 shadow-cx">
              <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div class="min-w-0">
                  <span class="text-[11px] font-semibold uppercase tracking-[0.08em] text-cx-ink-3">Your Organization</span>
                  <h1 class="mt-0.5 truncate text-4xl font-bold tracking-tight text-cx-ink leading-tight">{{ primaryOrganizationName }}</h1>
                  <div class="mt-2 flex flex-wrap items-center gap-2">
                    <span class="inline-flex items-center gap-1 rounded-cx-sm border border-cx-border bg-cx-well px-2 py-0.5 text-[11px] font-semibold text-cx-ink-2">
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
            <div class="grid gap-4 sm:grid-cols-3">
              <div class="rounded-cx border border-cx-border bg-cx-surface p-5 shadow-cx space-y-3">
                <span class="text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink-3 block">Care Tokens across facilities</span>
                <div class="flex items-baseline gap-2">
                  <span class="text-6xl font-bold text-cx-brand tracking-tight leading-none">{{ totalTokenCount.toLocaleString() }}</span>
                  <span class="text-xs font-semibold text-cx-ink-3">Care Tokens</span>
                </div>
                <p class="text-xs text-cx-ink-3 leading-relaxed">
                  Combined balance across your linked facilities.
                </p>
                <div class="pt-2 border-t border-cx-border-soft">
                  <button type="button" class="text-xs font-semibold text-cx-brand hover:underline" @click="openTopUpModal()">
                    + Add Care Tokens →
                  </button>
                </div>
              </div>

              <div class="rounded-cx border border-cx-border bg-cx-surface p-5 shadow-cx space-y-3">
                <span class="text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink-3 block">Registry status</span>
                <div class="flex items-baseline gap-2">
                  <span class="text-6xl font-bold text-cx-ink tracking-tight leading-none">{{ liveFacilitiesCount }} / {{ facilityCount }}</span>
                  <span class="text-xs font-semibold text-cx-success-ink">Clinics Live</span>
                </div>
                <p class="text-xs text-cx-ink-3 leading-relaxed">
                  Facilities marked live have completed the registry checks shown in your portfolio.
                </p>
                <div class="pt-2 border-t border-cx-border-soft">
                  <button type="button" class="text-xs font-semibold text-cx-brand hover:underline" @click="activeView = 'facilities'">
                    Manage facilities →
                  </button>
                </div>
              </div>

              <div class="rounded-cx border border-cx-border bg-cx-surface p-5 shadow-cx space-y-3" :class="openInvoiceCount > 0 ? 'border-cx-warning-border bg-cx-warning-soft' : ''">
                <span class="text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink-3 block">Settlement & Invoices</span>
                <div class="flex items-baseline gap-2">
                  <span class="text-6xl font-bold tracking-tight leading-none" :class="openInvoiceCount > 0 ? 'text-cx-warning-ink' : 'text-cx-ink'">
                    {{ openInvoiceCount > 0 ? money(totalOutstandingAmount) : 'Paid' }}
                  </span>
                  <span v-if="openInvoiceCount > 0" class="text-xs font-semibold text-cx-warning-ink">Due</span>
                </div>
                <p class="text-xs text-cx-ink-3 leading-relaxed">
                  {{ openInvoiceCount > 0 ? `${openInvoiceCount} invoice awaiting payment via M-Pesa / Bank` : 'All invoices settled with zero outstanding balance.' }}
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

              <div v-else class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                <article
                  v-for="fac in allFacilities"
                  :key="fac.mfl_code"
                  class="flex cursor-pointer flex-col justify-between rounded-cx border border-cx-border bg-cx-surface p-5 shadow-cx hover:border-cx-brand transition"
                  @click="openFacilityFromSurface($event, fac)"
                >
                  <div>
                    <div class="flex items-start justify-between gap-2">
                      <div class="min-w-0">
                        <button
                          type="button"
                          class="block truncate text-left text-base font-bold text-cx-ink underline-offset-2 hover:text-cx-brand-strong hover:underline"
                          @click="openFacilityDrawer(fac)"
                        >
                          {{ fac.facility_name }}
                        </button>
                        <p class="mt-0.5 text-xs text-cx-ink-3">{{ fac.keph_level }} · MFL: {{ fac.mfl_code }}</p>
                        <span class="mt-1 inline-flex items-center gap-1 rounded-cx-sm border border-cx-border-soft bg-cx-well px-1.5 py-0.5 text-[11px] font-medium text-cx-ink-2">
                          <span><CxIcon name="globe" class="inline-block size-4 align-[-0.15em]" /></span>
                          <span>{{ fac.network }}</span>
                        </span>
                      </div>
                      <span
                        class="shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-semibold"
                        :class="fac.go_live ? 'border-cx-success-border bg-cx-success-soft text-cx-success-ink' : 'border-cx-warning-border bg-cx-warning-soft text-cx-warning-ink'"
                      >
                        {{ facilityReadinessLabel(fac) }}
                      </span>
                    </div>

                    <div class="mt-4 space-y-1.5 rounded-cx-sm border border-cx-border-soft bg-cx-well p-3 text-xs">
                      <div class="flex justify-between text-cx-ink-3">
                        <span>Active Plan:</span>
                        <strong class="text-cx-ink">{{ fac.token_package || 'None' }}</strong>
                      </div>
                      <div v-if="fac.recent_purchase" class="flex justify-between text-[11px] text-cx-ink-3">
                        <span>Recent Order:</span>
                        <span class="font-mono text-cx-ink">{{ money(fac.recent_purchase.amount, fac.recent_purchase.currency) }} ({{ fac.recent_purchase.date }})</span>
                      </div>
                      <div class="flex justify-between text-cx-ink-3">
                        <span>Token Runway:</span>
                        <strong class="text-cx-brand"><CxIcon name="coins" class="inline-block size-4 align-[-0.15em]" /> {{ (fac.token_quantity || 0).toLocaleString() }} tokens</strong>
                      </div>
                      <div v-if="fac.invoice_summary?.has_outstanding" class="flex justify-between border-t border-cx-border-soft pt-1.5">
                        <span class="font-bold text-cx-warning-ink">Due Balance:</span>
                        <strong class="font-bold text-cx-warning-ink">{{ money(fac.invoice_summary.outstanding_amount, fac.invoice_summary.currency) }}</strong>
                      </div>
                    </div>
                  </div>

                  <div class="mt-4 space-y-2 border-t border-cx-border-soft pt-3">
                    <button
                      v-if="fac.invoice_summary?.has_outstanding && !pendingPaymentForFacility(fac)"
                      type="button"
                      class="flex w-full items-center justify-center gap-1.5 rounded-cx-sm bg-cx-success px-3 py-2 text-xs font-semibold text-cx-contrast shadow-cx transition hover:bg-cx-success"
                      @click="openMpesaModalForFacility(fac)"
                    >
                      <span><CxIcon name="phone" class="inline-block size-4 align-[-0.15em]" /> Pay M-Pesa: {{ money(fac.invoice_summary.outstanding_amount, fac.invoice_summary.currency) }} →</span>
                    </button>
                    <span v-else-if="fac.invoice_summary?.has_outstanding" class="block text-center text-[11px] font-semibold text-cx-warning-ink">
                      Payment verification pending
                    </span>
                    <div class="flex items-center gap-2">
                      <button
                        type="button"
                        class="flex-1 rounded-cx-sm bg-cx-ink px-3 py-2 text-xs font-semibold text-cx-contrast transition hover:bg-cx-ink-hover"
                        @click="openTopUpModal(fac)"
                      >
                        + Top Up Tokens
                      </button>
                      <button
                        type="button"
                        class="rounded-cx-sm border border-cx-border bg-cx-surface px-2.5 py-2 text-xs font-semibold text-cx-ink-2 hover:bg-cx-well"
                        @click="openFacilityDrawer(fac)"
                      >
                        Details →
                      </button>
                    </div>
                  </div>
                </article>
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
                Compare the current Care Token packages for your facility. Each package shows its price and billing period; token use depends on your HMIS activity.
              </p>
            </div>

            <!-- Top 4 Minimalist Pricing Cards (GitHub Style) -->
            <div class="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
              <article
                v-for="pkg in context.token_packages"
                :key="pkg.item_code"
                class="rounded-cx border border-cx-border bg-cx-surface p-6 shadow-cx flex flex-col justify-between transition hover:border-cx-border hover:shadow-cx"
              >
                <div>
                  <!-- Tier Header -->
                  <div class="flex items-center justify-between">
                    <h3 class="font-bold text-lg text-cx-ink">{{ pkg.display_name }}</h3>
                    <span
                      v-if="Number(pkg.price_ex_vat ?? pkg.price ?? 0) === 0"
                      class="rounded-full bg-cx-well text-cx-ink-2 px-2 py-0.5 text-[11px] font-semibold"
                    >
                      Free Trial
                    </span>
                  </div>

                  <!-- Short plain-language description -->
                  <p class="text-xs text-cx-ink-3 mt-2 min-h-10 leading-normal">
                    {{ pkg.coverage_summary || pkg.description }}
                  </p>

                  <!-- Price -->
                  <div class="mt-4 pt-4 border-t border-cx-border-soft">
                    <div class="flex items-baseline gap-1">
                      <span class="text-4xl font-bold text-cx-ink leading-tight">
                        {{ Number(pkg.price_ex_vat ?? pkg.price ?? 0) === 0 ? 'KES 0' : money(pkg.price_ex_vat ?? pkg.price, pkg.currency) }}
                      </span>
                      <span class="text-xs text-cx-ink-3 font-medium">/ {{ String(pkg.billing_period || 'Monthly').toLowerCase() }}</span>
                    </div>
                    <span class="text-[11px] text-cx-ink-4 block mt-0.5">
                      {{ Number(pkg.gross_total) > 0 ? `${money(pkg.gross_total, pkg.currency)} incl. ${pkg.vat_label || 'VAT'}` : 'No charge' }}
                    </span>
                  </div>

                  <!-- Token Quantity Pill -->
                  <div class="mt-4 inline-flex items-center gap-1.5 rounded-cx-sm bg-cx-brand-soft border border-cx-brand-soft-border px-3 py-1.5 text-xs font-semibold text-cx-brand">
                    <span><CxIcon name="coins" class="inline-block size-4 align-[-0.15em]" /></span>
                    <span>{{ Number(pkg.token_quantity || 0).toLocaleString() }} Care Tokens</span>
                  </div>
                </div>

                <!-- CTA Button -->
                <div class="mt-6 pt-4 border-t border-cx-border-soft">
                  <button
                    type="button"
                    class="w-full rounded-cx-sm bg-cx-brand py-2.5 px-4 text-xs font-semibold text-cx-contrast transition shadow-cx text-center hover:bg-cx-brand-strong"
                    @click="selectPlanFromPricingTab(pkg)"
                  >
                    {{ Number(pkg.price_ex_vat ?? pkg.price ?? 0) === 0 ? 'Choose free package' : `Choose ${pkg.display_name}` }}
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
              <div class="mt-3 grid gap-3 sm:grid-cols-3">
                <div class="rounded-cx-sm border border-cx-border bg-cx-surface p-3">
                  <span class="text-[11px] font-semibold uppercase tracking-[0.08em] text-cx-ink-3 block">Business No</span>
                  <div class="mt-1 flex items-center justify-between gap-2">
                    <span class="font-mono text-base font-bold text-cx-ink">{{ paybillInfo.business_number || 'Not available' }}</span>
                    <button
                      type="button"
                      class="rounded-cx-sm border border-cx-border bg-cx-surface px-2 py-0.5 text-[11px] font-semibold text-cx-ink-2 hover:bg-cx-well transition shrink-0 disabled:cursor-not-allowed disabled:opacity-50"
                      :disabled="!paybillInfo.business_number"
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
                  class="bg-cx-surface rounded-cx border border-cx-border p-5 shadow-cx flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4"
                >
                  <div>
                    <div class="flex items-center gap-2">
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
                        :class="invoiceStatus(invoice).key === 'overdue' ? 'bg-cx-danger-soft text-cx-danger-ink' : 'bg-amber-100 text-cx-warning-ink'"
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
                    <span class="inline-flex items-center gap-1.5 rounded-cx-sm border border-cx-border bg-cx-well px-2 py-0.5 mt-1.5 text-[11px] font-semibold text-cx-ink-2">
                      <span><CxIcon name="hospital" class="inline-block size-4 align-[-0.15em]" /></span>
                      <span>{{ facilityLabel(invoice.crm_token_facility_mfl, allFacilities) }}</span>
                      <span v-if="invoice.crm_token_facility_mfl" class="font-mono text-[11px] text-cx-ink-3">{{ invoice.crm_token_facility_mfl }}</span>
                    </span>
                  </div>

                  <div class="flex items-center gap-3 shrink-0 flex-wrap justify-end">
                    <div class="text-right">
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
              <h2 class="text-sm font-semibold uppercase tracking-[0.08em] text-cx-ink-3">Pending Token Orders</h2>
              <div class="space-y-3">
                <article
                  v-for="order in allOrders"
                  :key="order.name"
                  class="bg-cx-surface rounded-cx border border-cx-border p-4 shadow-cx flex items-center justify-between"
                >
                  <div>
                    <span class="font-semibold text-xs text-cx-ink">{{ packageLabel(order.crm_token_package_item, context.token_packages) }}</span>
                    <span class="text-xs text-cx-ink-3 ml-2">For {{ facilityLabel(order.crm_token_facility_mfl, allFacilities) }} · Order #{{ order.name }}</span>
                  </div>
                  <div class="flex items-center gap-3">
                    <span class="text-xs font-semibold text-cx-ink">{{ money(order.grand_total, order.currency) }}</span>
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
                  <table class="w-full text-left border-collapse text-xs">
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
          <div v-if="activeView === 'profile'" class="space-y-6 max-w-4xl">
            <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div>
                <h1 class="text-4xl font-bold text-cx-ink tracking-tight leading-tight">My Profile & Identification</h1>
                <p class="text-xs text-cx-ink-3 mt-0.5">Manage your National ID and contact details.</p>
              </div>
              <button
                type="button"
                class="rounded-cx-sm bg-cx-brand px-4 py-2 text-xs font-semibold text-cx-contrast shadow-cx hover:bg-cx-brand-strong transition inline-flex items-center gap-1.5 self-start sm:self-auto"
                @click="openEditProfileModal()"
              >
                <span><CxIcon name="pencil" class="mr-1 inline-block size-4 align-[-0.15em]" />Edit Profile Details</span>
              </button>
            </div>

            <!-- Profile Cards Grid -->
            <div class="grid gap-6 md:grid-cols-2">
              <!-- Card 1: National Identification -->
              <div class="rounded-cx border border-cx-border bg-cx-surface p-6 shadow-cx space-y-4">
                <div class="flex items-center justify-between">
                  <span class="text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink-3">National Identification</span>
                  <span
                    class="rounded-full px-2.5 py-0.5 text-[11px] font-semibold border"
                    :class="userProfile.national_id_verified ? 'bg-cx-success-soft text-cx-success-ink border-cx-success-border' : 'bg-cx-well text-cx-ink-2 border-cx-border'"
                  >
                    {{ userProfile.national_id_verified ? 'Verified' : (userProfile.national_id ? 'On file' : 'Not added') }}
                  </span>
                </div>

                <div class="rounded-cx-sm bg-cx-well border border-cx-border p-4 space-y-2">
                  <div class="text-xs text-cx-ink-3 font-medium">Kenyan National ID Number:</div>
                  <div class="flex items-center justify-between">
                    <span class="font-mono text-xl font-bold tracking-wider text-cx-ink">
                      {{ showUnmaskedId ? (userProfile.national_id || 'Not on file') : (userProfile.masked_national_id || 'Not on file') }}
                    </span>
                    <button
                      type="button"
                      class="rounded-cx-sm border border-cx-border bg-cx-surface px-2.5 py-1 text-xs font-semibold text-cx-ink-2 hover:bg-cx-well transition inline-flex items-center gap-1"
                      @click="showUnmaskedId = !showUnmaskedId"
                      :title="showUnmaskedId ? 'Mask National ID' : 'Reveal National ID'"
                    >
                      <span><CxIcon :name="showUnmaskedId ? 'shield-check' : 'eye'" class="mr-1 inline-block size-4 align-[-0.15em]" />{{ showUnmaskedId ? 'Mask' : 'Reveal' }}</span>
                    </button>
                  </div>
                </div>

                <p class="text-xs text-cx-ink-3 leading-relaxed">
                  Your National ID supports ownership checks when linking facilities. Manage it here; registry search is available from Facilities.
                </p>

                <div class="pt-2 border-t border-cx-border-soft">
                  <button
                    type="button"
                    class="text-xs font-semibold text-cx-ink-3 hover:text-cx-ink"
                    @click="openEditProfileModal()"
                  >
                    Change ID Number
                  </button>
                </div>
              </div>

              <!-- Card 2: Legal Organization & Identity -->
              <div class="rounded-cx border border-cx-border bg-cx-surface p-6 shadow-cx space-y-4">
                <div class="flex items-center justify-between">
                  <span class="text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink-3">Enterprise Entity</span>
                  <span class="rounded-full bg-cx-brand-soft text-cx-brand-ink border border-cx-brand-soft-border px-2.5 py-0.5 text-[11px] font-semibold">
                    Primary Account
                  </span>
                </div>

                <div class="space-y-3 text-xs">
                  <div class="rounded-cx-sm bg-cx-well border border-cx-border-soft p-3 space-y-1">
                    <span class="text-cx-ink-3 font-medium block">Parent Legal Organization</span>
                    <strong class="font-semibold text-sm text-cx-ink block">{{ primaryOrganizationName }}</strong>
                  </div>

                  <div class="grid grid-cols-2 gap-2 text-xs">
                    <div class="rounded-cx-sm bg-cx-well border border-cx-border-soft p-2.5">
                      <span class="text-cx-ink-3 block text-[11px]">Primary Network</span>
                      <strong class="text-cx-ink block truncate">{{ userProfile.primary_network || 'CareVerse Partner Network' }}</strong>
                    </div>
                    <div class="rounded-cx-sm bg-cx-well border border-cx-border-soft p-2.5">
                      <span class="text-cx-ink-3 block text-[11px]">Managed Clinics</span>
                      <strong class="text-cx-ink block">{{ allFacilities.length }} facilities</strong>
                    </div>
                  </div>

                  <div class="rounded-cx-sm bg-cx-well border border-cx-border-soft p-3 space-y-1">
                    <span class="text-cx-ink-3 font-medium block">Signatory / User</span>
                    <strong class="text-cx-ink block">{{ userProfile.full_name || context.user }}</strong>
                    <span class="text-cx-ink-3 font-mono text-[11px] block">{{ userProfile.email }}</span>
                    <span class="text-cx-ink-3 font-mono text-[11px] block">Phone: {{ userProfile.mobile_no || 'Not set' }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- ============================================================== -->
          <!-- VIEW G: NETWORK SUPPORT & CONTACTS                             -->
          <!-- ============================================================== -->
          <div v-if="activeView === 'support'" class="space-y-6 max-w-3xl">
            <div>
              <h1 class="text-4xl font-bold text-cx-ink tracking-tight leading-tight">Network Support & Contacts</h1>
              <p class="text-xs text-cx-ink-3 mt-0.5">Contact the support team for help with your account, facilities, or HMIS implementation.</p>
            </div>

            <div class="bg-cx-surface rounded-cx border border-cx-border p-6 shadow-cx space-y-4">
              <div class="space-y-2.5">
                <div class="rounded-cx-sm bg-cx-well border border-cx-border-soft p-3.5 text-xs flex items-center justify-between">
                  <span class="text-cx-ink-3 font-medium">Network Partner</span>
                  <span class="font-bold text-cx-ink">{{ primaryNetworkName }}</span>
                </div>
                <div class="rounded-cx-sm bg-cx-well border border-cx-border-soft p-3.5 text-xs flex items-center justify-between">
                  <span class="text-cx-ink-3 font-medium">Support email</span>
                  <a href="mailto:support@tiberbu.health" class="font-bold text-cx-brand hover:underline">support@tiberbu.health</a>
                </div>

              </div>
            </div>
          </div>
          </template>
        </main>

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
              <div v-for="candidate in hfrOwnerSearchResults" :key="candidate.fid || candidate.mfl_code" class="flex flex-col gap-3 rounded-cx-sm border border-cx-border bg-cx-surface p-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p class="text-xs font-semibold text-cx-ink">{{ candidate.name }}</p>
                  <p class="mt-1 text-[11px] text-cx-ink-3">MFL {{ candidate.mfl_code }} · {{ candidate.level || 'Facility' }} · {{ candidate.county }}{{ candidate.subcounty ? ` / ${candidate.subcounty}` : '' }}</p>
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
              <option value="facility_fid">FID</option>
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
              :key="cand.fid"
              class="rounded-cx-sm border p-3 flex items-center justify-between gap-3 hover:bg-cx-well transition"
              :class="facilityAlreadyLinked(cand) ? 'border-cx-success-border bg-cx-success-soft' : 'border-cx-border'"
            >
              <div>
                <span class="font-semibold text-xs text-cx-ink block">{{ cand.name }}</span>
                <span class="text-[11px] text-cx-ink-3">MFL {{ cand.mfl_code }} · {{ cand.level || 'Facility' }} · {{ cand.county || 'County unavailable' }} · {{ cand.owner_type || 'Registry record' }}</span>
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
      :title="__('Top Up Care Tokens')"
      size="3xl"
    >
      <div class="p-1 space-y-5">
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
              {{ fac.facility_name }} (MFL: {{ fac.mfl_code }}) · {{ fac.token_quantity || 0 }} tokens
            </option>
          </select>
        </div>

        <div class="space-y-2">
          <span class="text-xs font-semibold uppercase text-cx-ink-2 block">Select Package Tier</span>
          <div class="grid gap-3 sm:grid-cols-2">
            <button
              v-for="pkg in context.token_packages"
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
                <span class="text-cx-ink-4">{{ Number(pkg.gross_total) > 0 ? `${String(pkg.billing_period || 'Monthly').toLowerCase()} · incl. ${pkg.vat_label || 'VAT'}` : 'No charge' }}</span>
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

    <!-- MODAL 5: EDIT PROFILE & NATIONAL ID -->
    <Dialog
      v-model:open="profileModalOpen"
      :title="__('Edit Profile & National ID')"
      size="xl"
    >
      <div class="p-1 space-y-4">
        <div>
          <label class="block text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink-2 mb-1.5">
            Full Name
          </label>
          <input
            type="text"
            v-model="profileForm.full_name"
            placeholder="e.g. Salim Mwaura"
            class="w-full rounded-cx-sm border border-cx-border px-3.5 py-2 text-xs font-medium text-cx-ink focus:outline-none focus:border-cx-brand"
          />
        </div>

        <div>
          <label class="block text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink-2 mb-1.5">
            Kenyan National ID Number
          </label>
          <input
            type="text"
            v-model="profileForm.national_id"
            placeholder="6 to 10 digit National ID"
            maxlength="10"
            class="w-full rounded-cx-sm border border-cx-border px-3.5 py-2 text-xs font-mono font-semibold text-cx-ink focus:outline-none focus:border-cx-brand"
          />
          <p class="text-[11px] text-cx-ink-3 mt-1">
            Used to securely query and auto-discover facilities licensed under your ownership in the official Health Facility Registry.
          </p>
        </div>

        <div>
          <label class="block text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink-2 mb-1.5">
            Mobile Number
          </label>
          <input
            type="tel"
            v-model="profileForm.mobile_no"
            placeholder="e.g. 0712345678"
            class="w-full rounded-cx-sm border border-cx-border px-3.5 py-2 text-xs font-medium text-cx-ink focus:outline-none focus:border-cx-brand"
          />
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
