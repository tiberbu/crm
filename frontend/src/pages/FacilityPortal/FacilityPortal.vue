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

// Current Active Navigation View: 'dashboard' | 'facilities' | 'pricing' | 'billing' | 'hfr_sync' | 'profile' | 'support'
// The portal lands on the Dashboard — the at-a-glance portfolio story — and
// drills down from there instead of opening on the densest data table.
const activeView = ref('dashboard')

// Sidebar collapsed state for responsive layout
const sidebarCollapsed = ref(false)
const isMobileViewport = ref(false)
const mobileMoreOpen = ref(false)
const mobileMoreItems = computed(() => [
  { view: 'pricing', label: 'Plans & Pricing', icon: 'coins' },
  { view: 'hfr_sync', label: 'Registry Sync', icon: 'refresh' },
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
    window.location.href = '/login?redirect-to=/crm/facility-portal.html'
  },
  onError: () => {
    window.location.href = '/login'
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

// Search, Filter & Grouping state for Facilities Data Table
const searchQuery = ref('')
const selectedStatusFilter = ref('all') // 'all' | 'live' | 'verifying'
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
const hfrSearchBy = ref('mfl_code') // 'mfl_code' | 'registration_number'
const partnerIdInput = ref('')
const hfrSearchBusy = ref(false)
const hfrSearchResults = ref([])
const hfrLinkBusy = ref(false)
const hfrSelectedCandidate = ref(null)

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
    if (selectedStatusFilter.value === 'live' && !fac.go_live) return false
    if (selectedStatusFilter.value === 'verifying' && fac.go_live) return false

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
function openFacilityDrawer(facility) {
  facilityDrawerMfl.value = facility.mfl_code
  activeView.value = 'facility_detail'
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

// Dashboard: items that need the user's attention (invoices due/overdue,
// facilities still verifying on the registry)
const dashboardAttention = computed(() => {
  const items = []
  for (const inv of allInvoices.value) {
    const status = invoiceStatus(inv)
    items.push({
      key: `inv-${inv.name}`,
      icon: 'credit-card',
      text: `Invoice ${inv.invoice_number || inv.name} — ${money(inv.amount, inv.currency)} ${status.key === 'overdue' ? 'overdue' : 'due'}`,
      meta: `Facility: ${facilityLabel(inv.crm_token_facility_mfl, allFacilities.value)}`,
      view: 'billing',
    })
  }
  for (const fac of allFacilities.value) {
    if (!fac.go_live) {
      items.push({
        key: `verify-${fac.mfl_code}`,
        icon: 'refresh',
        text: `${fac.facility_name} is verifying on the Health Facility Registry`,
        meta: `MFL: ${fac.mfl_code} · ${fac.keph_level}`,
        view: 'facilities',
      })
    }
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
      title: `Receipt ${pay.name}`,
      text: `${pay.mode_of_payment || 'Payment'} · ${money(pay.amount, 'KES')}`,
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
function copyMfl(code) {
  if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(code)
    copiedMfl.value = code
    setTimeout(() => {
      if (copiedMfl.value === code) copiedMfl.value = ''
    }, 2000)
  }
}

function copyText(text, key) {
  if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(String(text))
    copiedKey.value = key
    setTimeout(() => {
      if (copiedKey.value === key) copiedKey.value = ''
    }, 2000)
  }
}

const paybillInfo = computed(() => {
  return context.value.paybill_info || {
    business_number: '4130669',
    business_name: 'Tiberbu Healthnet',
  }
})

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
  hfrSearchQuery.value = ''
  hfrSearchResults.value = []
  hfrSelectedCandidate.value = null
  partnerIdInput.value = ''
  addFacilityModalOpen.value = true
}

function openCalculatorModal(facility = null) {
  if (facility) {
    selectedFacilityMfl.value = facility.mfl_code
  }
  calculatorModalOpen.value = true
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
  mpesaInvoice.value = invoice
  mpesaCodeInput.value = ''
  mpesaPhoneInput.value = userProfile.value.mobile_no || ''
  mpesaModalOpen.value = true
}

function openMpesaModalForFacility(facility) {
  const invName = facility.invoice_summary?.invoice_name
  let inv = allInvoices.value.find((i) => i.name === invName)
  if (!inv) {
    inv = allInvoices.value.find(
      (i) => String(i.crm_token_facility_mfl).toLowerCase() === String(facility.mfl_code).toLowerCase(),
    )
  }
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
    mpesaModalOpen.value = false
    notice.value = {
      tone: 'success',
      text: data?.message || `M-Pesa payment ${code} recorded successfully! Your invoice will update upon reconciliation.`,
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
  hfrSelectedCandidate.value = null

  try {
    const res = await call('crm.api.customer_experience.lookup_hfr_facility', {
      query,
      search_by: hfrSearchBy.value,
    })
    const data = unwrap(res)
    hfrSearchResults.value = Array.isArray(data) ? data : []
    if (!hfrSearchResults.value.length) {
      notice.value = {
        tone: 'pending',
        text: `No Health Facility Registry records matched query "${query}". Try searching by the facility's 5-digit MFL code.`,
      }
    }
  } catch (error) {
    notice.value = {
      tone: 'error',
      text: error?.messages?.[0] || 'Unable to connect to Health Facility Registry.',
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
      text: `Order ${payload.sales_order || ''} successfully generated for ${selectedFacility.value.facility_name}. Settle payment under Billing & Invoices to activate tokens.`,
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

          <!-- 5. Health Facility Registry Sync -->
          <button
            type="button"
            class="w-full flex items-center gap-3 px-3 py-2.5 rounded-cx-sm text-xs font-semibold transition text-left"
            :class="
              activeView === 'hfr_sync'
                ? 'bg-cx-brand-soft text-cx-brand-ink shadow-cx'
                : 'text-cx-ink-3 hover:bg-cx-well hover:text-cx-ink'
            "
            @click="activeView = 'hfr_sync'"
          >
            <span class="text-base shrink-0"><CxIcon name="refresh" class="inline-block size-4 align-[-0.15em]" /></span>
            <span v-if="!sidebarCollapsed" class="truncate">Facility Registry Sync</span>
          </button>

          <!-- 6. My Profile (National ID & Identity) -->
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
        <!-- Top App Bar (Global Search & Quick Actions) -->
        <header class="cx-glass-chrome h-16 bg-cx-surface border-b border-cx-border px-3 sm:px-6 flex items-center justify-between shrink-0 sticky top-0 z-20">
          <!-- Search Bar -->
          <div class="relative w-28 sm:w-80 lg:w-96">
            <svg class="size-4 text-cx-ink-4 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="11" cy="11" r="8"></circle>
              <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
            </svg>
            <input
              ref="globalSearchRef"
              type="text"
              v-model="searchQuery"
              placeholder="Search your facilities by name"
              class="w-full rounded-cx-sm bg-cx-well border border-cx-border pl-9 pr-12 py-2 text-xs font-medium text-cx-ink placeholder:text-cx-ink-4 focus:bg-cx-surface focus:border-cx-brand focus:outline-none focus:ring-2 focus:ring-cx-brand-soft transition"
              @input="onGlobalSearchInput"
            />
            <span class="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-cx-sm bg-cx-band px-1.5 py-0.5 text-[11px] font-mono text-cx-ink-3">
              ⌘K
            </span>
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
            :payments="drawerFacility.payments || []"
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
                  Manage registered clinic branches, track Health Facility Registry verification, and monitor token capacity.
                </p>
              </div>

              <!-- Actions relevant to managing this facility portfolio -->
              <div class="flex items-center gap-2">
                <button
                  type="button"
                  class="inline-flex items-center gap-1.5 rounded-cx-sm border border-cx-border bg-cx-surface px-3.5 py-2 text-xs font-semibold text-cx-ink-2 hover:bg-cx-well shadow-cx"
                  @click="activeView = 'hfr_sync'"
                >
                  <span><CxIcon name="refresh" class="inline-block size-4 align-[-0.15em]" /> Find in Facility Registry</span>
                </button>
                <button
                  type="button"
                  class="inline-flex items-center gap-1.5 rounded-cx-sm bg-cx-brand px-4 py-2 text-xs font-semibold text-cx-contrast shadow-cx hover:bg-cx-brand-strong transition"
                  @click="openAddFacilityModal()"
                >
                  <span>+ Add Facility</span>
                </button>
              </div>
            </div>

            <!-- Table Filters Toolbar (from screenshot: Search, Bulk Action, View Mode, Filters) -->
            <div class="flex flex-wrap items-center justify-between gap-3 pt-2">
              <div class="flex items-center gap-2 flex-wrap">
                <!-- Search input -->
                <div class="relative w-64">
                  <input
                    type="text"
                    v-model="searchQuery"
                    placeholder="Search facilities by name"
                    class="w-full rounded-cx-sm bg-cx-surface border border-cx-border pl-8 pr-3 py-1.5 text-xs font-medium text-cx-ink placeholder:text-cx-ink-4 focus:outline-none focus:border-cx-brand shadow-cx"
                  />
                  <svg class="size-3.5 text-cx-ink-4 absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="11" cy="11" r="8"></circle>
                    <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                  </svg>
                </div>

                <!-- Status Filter -->
                <select
                  v-model="selectedStatusFilter"
                  class="rounded-cx-sm bg-cx-surface border border-cx-border px-3 py-1.5 text-xs font-semibold text-cx-ink-2 shadow-cx focus:outline-none focus:border-cx-brand"
                >
                  <option value="all">All Statuses</option>
                  <option value="live">Live on Registry</option>
                  <option value="verifying">Verification Pending</option>
                </select>

                <!-- Level Filter -->
                <select
                  v-model="selectedLevelFilter"
                  class="rounded-cx-sm bg-cx-surface border border-cx-border px-3 py-1.5 text-xs font-semibold text-cx-ink-2 shadow-cx focus:outline-none focus:border-cx-brand"
                >
                  <option value="all">All KEPH Levels</option>
                  <option value="Level 2">Level 2 Dispensary</option>
                  <option value="Level 3">Level 3 Health Centre</option>
                  <option value="Level 4">Level 4 Hospital</option>
                </select>

                <!-- Partner / Network Filter -->
                <select
                  v-model="selectedNetworkFilter"
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

            <!-- Empty portfolio state -->
            <div v-if="!allFacilities.length" class="rounded-cx border border-cx-border bg-cx-surface p-10 text-center">
              <span class="mb-2 block text-3xl"><CxIcon name="hospital" class="inline-block size-4 align-[-0.15em]" /></span>
              <p class="text-sm font-semibold text-cx-ink">No facilities in your portfolio yet</p>
              <p class="mx-auto mt-1 max-w-md text-xs text-cx-ink-3">
                Link your clinics from the Health Facility Registry — we can auto-discover the ones registered under your National ID.
              </p>
              <button
                type="button"
                class="mt-4 rounded-cx-sm bg-cx-brand px-4 py-2 text-xs font-semibold text-cx-contrast shadow-cx transition hover:bg-cx-brand-strong"
                @click="openAddFacilityModal()"
              >
                + Add Facility
              </button>
            </div>

            <!-- TABLE VIEW -->
          <div v-if="allFacilities.length && facilityViewMode === 'table' && !isMobileViewport" class="space-y-4">
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
                          <th class="py-3 px-4">Registry Status</th>
                          <th class="py-3 px-4">Plan & Recent Purchase</th>
                          <th class="py-3 px-4 text-right">Care Tokens</th>
                          <th class="py-3 px-4 text-right">Settlement & Actions</th>
                        </tr>
                      </thead>
                      <tbody class="divide-y divide-cx-border-soft">
                        <tr
                          v-for="facility in group.facilities"
                          :key="facility.mfl_code"
                          class="hover:bg-cx-band transition"
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
                              <span>{{ facility.go_live ? 'Live' : 'Verifying' }}</span>
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
                                v-if="facility.invoice_summary?.has_outstanding"
                                type="button"
                                class="rounded-cx-sm bg-cx-success px-2.5 py-1 text-xs font-semibold text-cx-contrast hover:bg-cx-success transition shadow-cx inline-flex items-center gap-1 shrink-0 cursor-pointer"
                                @click="openMpesaModalForFacility(facility)"
                                title="Pay outstanding invoice via M-Pesa"
                              >
                                <span><CxIcon name="phone" class="inline-block size-4 align-[-0.15em]" /> Pay M-Pesa: {{ money(facility.invoice_summary.outstanding_amount, facility.invoice_summary.currency) }} →</span>
                              </button>
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
                        <th class="py-3 px-4">Registry Status</th>
                        <th class="py-3 px-4">Plan & Recent Purchase</th>
                        <th class="py-3 px-4 text-right">Care Tokens</th>
                        <th class="py-3 px-4 text-right">Settlement & Actions</th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-cx-border-soft">
                      <tr
                        v-for="facility in filteredFacilities"
                        :key="facility.mfl_code"
                        class="hover:bg-cx-band transition"
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
                            <span>{{ facility.go_live ? 'Live' : 'Verifying' }}</span>
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
                              v-if="facility.invoice_summary?.has_outstanding"
                              type="button"
                              class="rounded-cx-sm bg-cx-success px-2.5 py-1 text-xs font-semibold text-cx-contrast hover:bg-cx-success transition shadow-cx inline-flex items-center gap-1 shrink-0 cursor-pointer"
                              @click="openMpesaModalForFacility(facility)"
                              title="Pay outstanding invoice via M-Pesa"
                            >
                              <span><CxIcon name="phone" class="inline-block size-4 align-[-0.15em]" /> Pay M-Pesa: {{ money(facility.invoice_summary.outstanding_amount, facility.invoice_summary.currency) }} →</span>
                            </button>
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
            <div v-else-if="allFacilities.length" class="space-y-6">
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
                      class="cx-glass-panel rounded-cx border border-cx-border bg-cx-surface p-5 shadow-cx flex flex-col justify-between hover:border-cx-brand transition"
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
                            {{ facility.go_live ? 'Live' : 'Verifying' }}
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
                          v-if="facility.invoice_summary?.has_outstanding"
                          type="button"
                          class="w-full rounded-cx-sm bg-cx-success px-3 py-2 text-xs font-semibold text-cx-contrast hover:bg-cx-success transition flex items-center justify-center gap-1.5 shadow-cx cursor-pointer"
                          @click="openMpesaModalForFacility(facility)"
                        >
                          <span><CxIcon name="phone" class="inline-block size-4 align-[-0.15em]" /> Pay M-Pesa: {{ money(facility.invoice_summary.outstanding_amount, facility.invoice_summary.currency) }} →</span>
                        </button>
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
                  class="cx-glass-panel rounded-cx border border-cx-border bg-cx-surface p-5 shadow-cx flex flex-col justify-between hover:border-cx-brand transition"
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
                        {{ facility.go_live ? 'Live' : 'Verifying' }}
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
                      v-if="facility.invoice_summary?.has_outstanding"
                      type="button"
                      class="w-full rounded-cx-sm bg-cx-success px-3 py-2 text-xs font-semibold text-cx-contrast hover:bg-cx-success transition flex items-center justify-center gap-1.5 shadow-cx cursor-pointer"
                      @click="openMpesaModalForFacility(facility)"
                    >
                      <span><CxIcon name="phone" class="inline-block size-4 align-[-0.15em]" /> Pay M-Pesa: {{ money(facility.invoice_summary.outstanding_amount, facility.invoice_summary.currency) }} →</span>
                    </button>
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
                    type="button"
                    class="shrink-0 text-xs font-semibold text-cx-brand hover:underline"
                    @click="activeView = item.view"
                  >
                    Review →
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
                    View Facility Registry →
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
                  class="flex flex-col justify-between rounded-cx border border-cx-border bg-cx-surface p-5 shadow-cx"
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
                        {{ fac.go_live ? 'Live' : 'Verifying' }}
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
                      v-if="fac.invoice_summary?.has_outstanding"
                      type="button"
                      class="flex w-full items-center justify-center gap-1.5 rounded-cx-sm bg-cx-success px-3 py-2 text-xs font-semibold text-cx-contrast shadow-cx transition hover:bg-cx-success"
                      @click="openMpesaModalForFacility(fac)"
                    >
                      <span><CxIcon name="phone" class="inline-block size-4 align-[-0.15em]" /> Pay M-Pesa: {{ money(fac.invoice_summary.outstanding_amount, fac.invoice_summary.currency) }} →</span>
                    </button>
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
                Tiberbu operates on transparent, transactional Care Tokens. Pay only for verified patient visits, labs, and e-claims with zero seat licenses or hidden server fees.
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
                      <span class="text-xs text-cx-ink-3 font-medium">/ month</span>
                    </div>
                    <span class="text-[11px] text-cx-ink-4 block mt-0.5">
                      {{ Number(pkg.gross_total) > 0 ? `${money(pkg.gross_total, pkg.currency)} incl. 16% VAT` : 'Zero commitment' }}
                    </span>
                  </div>

                  <!-- Token Quantity Pill -->
                  <div class="mt-4 inline-flex items-center gap-1.5 rounded-cx-sm bg-cx-brand-soft border border-cx-brand-soft-border px-3 py-1.5 text-xs font-semibold text-cx-brand">
                    <span><CxIcon name="coins" class="inline-block size-4 align-[-0.15em]" /></span>
                    <span>{{ (pkg.token_quantity || 100).toLocaleString() }} Care Tokens</span>
                  </div>
                </div>

                <!-- CTA Button -->
                <div class="mt-6 pt-4 border-t border-cx-border-soft">
                  <button
                    type="button"
                    class="w-full rounded-cx-sm bg-cx-brand py-2.5 px-4 text-xs font-semibold text-cx-contrast transition shadow-cx text-center hover:bg-cx-brand-strong"
                    @click="selectPlanFromPricingTab(pkg)"
                  >
                    {{ Number(pkg.price_ex_vat ?? pkg.price ?? 0) === 0 ? 'Activate Free Trial' : `Select ${pkg.display_name}` }}
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
              <p class="text-xs text-cx-ink-3 mt-0.5">Review outstanding statements, generate invoices for token orders, and pay instantly via M-Pesa.</p>
            </div>

            <!-- M-Pesa Paybill settlement details (primary payment method) -->
            <div class="rounded-cx border border-cx-success-border bg-cx-success-soft p-4">
              <div class="flex items-center gap-3">
                <div class="size-8 shrink-0 rounded-cx-sm bg-cx-success text-cx-contrast flex items-center justify-center font-semibold text-sm">M</div>
                <div class="min-w-0">
                  <span class="font-semibold text-xs text-cx-success-ink block">M-Pesa Paybill · {{ paybillInfo.business_name }}</span>
                  <span class="text-[11px] text-cx-success-ink">Primary settlement method — direct paybill with zero transaction processing surcharge</span>
                </div>
              </div>
              <div class="mt-3 grid gap-3 sm:grid-cols-3">
                <div class="rounded-cx-sm border border-cx-border bg-cx-surface p-3">
                  <span class="text-[11px] font-semibold uppercase tracking-[0.08em] text-cx-ink-3 block">Business No</span>
                  <div class="mt-1 flex items-center justify-between gap-2">
                    <span class="font-mono text-base font-bold text-cx-ink">{{ paybillInfo.business_number }}</span>
                    <button
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
                    Enter the invoice number shown on each invoice card below (e.g. <span class="font-mono">{{ allInvoices[0]?.name || 'ACC-SINV-2026-00001' }}</span>).
                  </p>
                </div>
                <div class="rounded-cx-sm border border-cx-border bg-cx-surface p-3">
                  <span class="text-[11px] font-semibold uppercase tracking-[0.08em] text-cx-ink-3 block">How to pay</span>
                  <p class="mt-1 text-[11px] text-cx-ink-3 leading-relaxed">
                    1. M-Pesa app → Lipa na M-Pesa → Paybill<br />
                    2. Business No, then Account No (invoice number)<br />
                    3. Amount &amp; PIN, then paste the transaction code on the invoice
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
                        class="rounded-cx-sm px-2 py-0.5 text-[11px] font-semibold"
                        :class="invoiceStatus(invoice).key === 'overdue' ? 'bg-cx-danger-soft text-cx-danger-ink' : 'bg-amber-100 text-cx-warning-ink'"
                      >
                        {{ invoiceStatus(invoice).label }}
                      </span>
                    </div>
                    <p class="text-xs text-cx-ink-3 mt-1">
                      Due: <strong>{{ invoice.due_date || 'On Receipt' }}</strong> · Issued: {{ invoice.posting_date }}
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
                      <span class="text-[11px] text-cx-ink-4 uppercase font-medium">Balance</span>
                    </div>
                    <button
                      type="button"
                      class="rounded-cx-sm bg-cx-success px-4 py-2 text-xs font-semibold text-cx-contrast shadow-cx hover:bg-cx-success transition inline-flex items-center gap-1.5"
                      @click="openMpesaModal(invoice)"
                    >
                      <span><CxIcon name="phone" class="inline-block size-4 align-[-0.15em]" /> Pay M-Pesa (No Fee)</span>
                    </button>
                    <button
                      type="button"
                      class="rounded-cx-sm border border-cx-border bg-cx-surface px-3 py-2 text-xs font-semibold text-cx-ink-2 hover:bg-cx-well transition disabled:opacity-50"
                      :disabled="busyId === invoice.name"
                      @click="payInvoice(invoice)"
                    >
                      <span>{{ busyId === invoice.name ? 'Connecting…' : 'Card / Paystack →' }}</span>
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
                  <h2 class="text-sm font-semibold uppercase tracking-[0.08em] text-cx-ink-3">Payment Receipts & History</h2>
                  <p class="text-xs text-cx-ink-3 mt-0.5">Verified payment receipts, M-Pesa confirmations, and bank settlements.</p>
                </div>
                <span class="text-xs text-cx-ink-3 font-semibold bg-cx-well px-2.5 py-1 rounded-cx-sm border border-cx-border">
                  {{ allPayments.length }} {{ allPayments.length === 1 ? 'receipt' : 'receipts' }}
                </span>
              </div>

              <div class="bg-cx-surface rounded-cx border border-cx-border shadow-cx overflow-hidden">
                <div class="overflow-x-auto">
                  <table class="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr class="border-b border-cx-border bg-cx-well text-[11px] font-semibold uppercase tracking-[0.08em] text-cx-ink-3">
                        <th class="py-3 px-4">Receipt #</th>
                        <th class="py-3 px-4">Date</th>
                        <th class="py-3 px-4">Mode & Reference</th>
                        <th class="py-3 px-4 text-right">Amount</th>
                        <th class="py-3 px-4 text-center">Status</th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-cx-border-soft">
                      <tr v-for="pay in allPayments" :key="pay.name" class="hover:bg-cx-band transition">
                        <td class="py-3 px-4 font-mono font-bold text-cx-ink">{{ pay.name }}</td>
                        <td class="py-3 px-4 text-cx-ink-3">{{ pay.posting_date }}</td>
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
                            :class="pay.status === 'Submitted' ? 'bg-cx-success-soft text-cx-success-ink border-cx-success-border' : 'bg-cx-warning-soft text-cx-warning-ink border-cx-warning-border'"
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
          <!-- VIEW E: HEALTH FACILITY REGISTRY SYNC                          -->
          <!-- ============================================================== -->
          <div v-if="activeView === 'hfr_sync'" class="space-y-6 max-w-4xl">
            <div>
              <h1 class="text-4xl font-bold text-cx-ink tracking-tight leading-tight">Health Facility Registry Sync</h1>
              <p class="text-xs text-cx-ink-3 mt-0.5">Synchronize facility records directly with the official Digital Health Agency (DHA) Health Facility Registry.</p>
            </div>

            <!-- 1-Click Discovery by National ID on File -->
            <div class="bg-cx-surface rounded-cx border border-cx-border p-6 shadow-cx space-y-4">
              <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <div>
                  <h3 class="font-semibold text-sm text-cx-ink flex items-center gap-2">
                    <span><CxIcon name="id" class="inline-block size-4 align-[-0.15em]" /></span>
                    <span>1-Click Auto-Discovery by National ID</span>
                  </h3>
                  <p class="text-xs text-cx-ink-3 mt-1">
                    Search for clinical branches linked to the National ID saved on your profile
                    <span v-if="userProfile.masked_national_id" class="font-mono font-bold text-cx-ink">({{ userProfile.masked_national_id }})</span>.
                  </p>
                </div>
                <button
                  type="button"
                  class="rounded-cx-sm bg-cx-brand px-4 py-2.5 text-xs font-semibold text-cx-contrast shadow-cx hover:bg-cx-brand-strong transition shrink-0 disabled:opacity-50 inline-flex items-center gap-1.5"
                  :disabled="hfrOwnerSearchBusy"
                  @click="discoverFacilitiesByOwnerId()"
                >
                  <span><CxIcon v-if="!hfrOwnerSearchBusy" name="search" class="mr-1 inline-block size-4 align-[-0.15em]" />{{ hfrOwnerSearchBusy ? 'Searching Registry…' : 'Discover Facilities by My ID' }}</span>
                </button>
              </div>

              <div v-if="hfrOwnerSearchComplete && hfrOwnerSearchError" class="mt-4 rounded-cx-sm border border-cx-danger-border bg-cx-danger-soft p-3 text-xs text-cx-danger-ink" role="alert">
                {{ hfrOwnerSearchError }}
              </div>
              <div v-else-if="hfrOwnerSearchComplete && !hfrOwnerSearchResults.length" class="mt-4 rounded-cx-sm border border-cx-border bg-cx-well p-4 text-xs text-cx-ink-2" role="status">
                <p class="font-semibold text-cx-ink">No facilities found for the ID on your profile.</p>
                <p class="mt-1 text-cx-ink-3">You can search the registry by MFL, FID, or registration number, or review your National ID in Account settings.</p>
              </div>

              <!-- Discovered Facilities List -->
              <div v-if="hfrOwnerSearchResults.length" class="mt-4 pt-4 border-t border-cx-border-soft space-y-2">
                <span class="text-xs font-semibold uppercase text-cx-ink-3">Discovered Facilities ({{ hfrOwnerSearchResults.length }})</span>
                <div class="space-y-2 max-h-72 overflow-y-auto">
                  <div
                    v-for="cand in hfrOwnerSearchResults"
                    :key="cand.fid || cand.mfl_code"
                    class="rounded-cx-sm border border-cx-border p-3.5 flex items-center justify-between gap-3 hover:bg-cx-well transition"
                  >
                    <div>
                      <div class="flex items-center gap-2">
                        <span class="font-semibold text-xs text-cx-ink">{{ cand.name }}</span>
                        <span v-if="cand.already_linked" class="rounded-cx-sm bg-cx-success-soft text-cx-success-ink text-[11px] font-semibold px-2 py-0.5">
                          ✓ In Portfolio
                        </span>
                      </div>
                      <span class="text-[11px] text-cx-ink-3 block mt-0.5">
                        MFL: {{ cand.mfl_code }} · {{ cand.level }} · {{ cand.county }} {{ cand.subcounty ? `/ ${cand.subcounty}` : '' }} · {{ cand.owner_type }}
                      </span>
                    </div>

                    <button
                      v-if="!cand.already_linked"
                      type="button"
                      class="rounded-cx-sm bg-cx-ink px-3 py-1.5 text-xs font-semibold text-cx-contrast hover:bg-cx-ink-hover transition shrink-0 disabled:opacity-50"
                      :disabled="hfrLinkBusy"
                      @click="linkHfrCandidate(cand)"
                    >
                      {{ hfrLinkBusy ? 'Linking…' : '+ Add to Portfolio' }}
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <!-- Registry identifier lookup -->
            <div class="bg-cx-surface rounded-cx border border-cx-border p-6 shadow-cx space-y-4">
              <h3 class="font-semibold text-sm text-cx-ink">Search the Health Facility Registry</h3>
              <p class="text-xs text-cx-ink-3 leading-relaxed">
                Look up a facility using its MFL code, HFR Facility ID (FID), or registration number.
              </p>

              <div class="pt-2 flex items-center gap-3">
                <button
                  type="button"
                  class="rounded-cx-sm border border-cx-border bg-cx-surface px-4 py-2.5 text-xs font-semibold text-cx-ink shadow-cx hover:bg-cx-well transition"
                  @click="openAddFacilityModal()"
                >
                  <span>Search by registry identifier</span>
                </button>
              </div>
            </div>
          </div>

          <!-- ============================================================== -->
          <!-- VIEW F: MY PROFILE & IDENTIFICATION                            -->
          <!-- ============================================================== -->
          <div v-if="activeView === 'profile'" class="space-y-6 max-w-4xl">
            <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div>
                <h1 class="text-4xl font-bold text-cx-ink tracking-tight leading-tight">My Profile & Identification</h1>
                <p class="text-xs text-cx-ink-3 mt-0.5">Manage your National ID, contact details, and facility registry search.</p>
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
                  Your National ID is used to search the Health Facility Registry. Review it before searching; you can also add a facility by its MFL code.
                </p>

                <div class="pt-2 border-t border-cx-border-soft flex items-center justify-between">
                  <button
                    type="button"
                    class="text-xs font-semibold text-cx-brand hover:underline"
                    @click="discoverFacilitiesByOwnerId(); activeView = 'hfr_sync'"
                  >
                    1-Click Registry Discovery →
                  </button>
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
              <p class="text-xs text-cx-ink-3 mt-0.5">Dedicated clinical onboarding lead and emergency support channels.</p>
            </div>

            <div class="bg-cx-surface rounded-cx border border-cx-border p-6 shadow-cx space-y-4">
              <div class="space-y-2.5">
                <div class="rounded-cx-sm bg-cx-well border border-cx-border-soft p-3.5 text-xs flex items-center justify-between">
                  <span class="text-cx-ink-3 font-medium">Network Partner</span>
                  <span class="font-bold text-cx-ink">{{ primaryNetworkName }}</span>
                </div>
                <div class="rounded-cx-sm bg-cx-well border border-cx-border-soft p-3.5 text-xs flex items-center justify-between">
                  <span class="text-cx-ink-3 font-medium">Clinical Helpdesk</span>
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

    <!-- MODAL 1: ADD FACILITY VIA HEALTH FACILITY REGISTRY -->
    <Dialog
      v-model:open="addFacilityModalOpen"
      :title="__('Add Facility via Health Facility Registry')"
      size="3xl"
    >
      <div class="p-1 space-y-5">
        <section class="rounded-cx-sm border border-cx-border bg-cx-well p-4">
          <label class="mb-1.5 block text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink-2" for="portfolio-partner-id">Partner ID</label>
          <input
            id="portfolio-partner-id"
            v-model="partnerIdInput"
            inputmode="numeric"
            maxlength="6"
            placeholder="Six-digit Partner ID (optional)"
            class="w-full rounded-cx-sm border border-cx-border bg-cx-surface px-3.5 py-2.5 text-sm font-medium text-cx-ink focus:border-cx-brand focus:outline-none"
          />
          <p class="mt-1.5 text-xs text-cx-ink-3">Enter the Partner ID for the facility’s network. Leave it blank to use the configured default.</p>
        </section>
        <!-- 1-Click National ID Discovery Banner if ID exists -->
        <div v-if="userProfile.masked_national_id" class="rounded-cx-sm bg-cx-brand-soft border border-cx-brand-soft-border p-3.5 flex items-center justify-between gap-3">
          <div>
            <span class="font-semibold text-xs text-cx-brand-ink block">Registered Owner ID: {{ userProfile.masked_national_id }}</span>
            <span class="text-[11px] text-cx-brand-ink">Auto-discover clinic branches licensed under this National ID with 1 click.</span>
          </div>
          <button
            type="button"
            class="rounded-cx-sm bg-cx-brand px-3 py-1.5 text-xs font-semibold text-cx-contrast hover:bg-cx-brand-strong transition shrink-0 disabled:opacity-50"
            :disabled="hfrOwnerSearchBusy"
            @click="discoverFacilitiesByOwnerId(); addFacilityModalOpen = false; activeView = 'hfr_sync'"
          >
            {{ hfrOwnerSearchBusy ? 'Searching…' : 'Discover by My ID →' }}
          </button>
        </div>

        <div>
          <label class="block text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink-2 mb-1.5">
            Search the Health Facility Registry by MFL, FID, or registration number
          </label>
          <div class="flex gap-2">
            <select
              v-model="hfrSearchBy"
              class="rounded-cx-sm border border-cx-border bg-cx-surface px-3 py-2 text-xs font-semibold text-cx-ink-2 shrink-0"
            >
              <option value="mfl_code">MFL Code</option>
              <option value="facility_fid">FID</option>
              <option value="registration_number">Registration #</option>
            </select>
            <input
              type="text"
              v-model="hfrSearchQuery"
              placeholder="Enter the selected registry identifier"
              class="flex-1 rounded-cx-sm border border-cx-border px-3.5 py-2 text-xs font-medium text-cx-ink focus:outline-none focus:border-cx-brand"
              @keyup.enter="executeHfrSearch()"
            />
            <button
              type="button"
              class="rounded-cx-sm bg-cx-brand px-4 py-2 text-xs font-semibold text-cx-contrast hover:bg-cx-brand-strong disabled:opacity-50 shrink-0"
              :disabled="hfrSearchBusy"
              @click="executeHfrSearch()"
            >
              {{ hfrSearchBusy ? 'Searching…' : 'Search' }}
            </button>
          </div>
        </div>

        <!-- Search Results -->
        <div v-if="hfrSearchResults.length" class="space-y-2">
          <span class="text-xs font-semibold uppercase text-cx-ink-3">Matching Registry Records ({{ hfrSearchResults.length }})</span>
          <div class="space-y-2 max-h-60 overflow-y-auto">
            <div
              v-for="cand in hfrSearchResults"
              :key="cand.fid"
              class="rounded-cx-sm border p-3 flex items-center justify-between gap-3 hover:bg-cx-well transition"
              :class="hfrSelectedCandidate?.fid === cand.fid ? 'border-cx-brand bg-cx-brand-soft' : 'border-cx-border'"
            >
              <div>
                <span class="font-semibold text-xs text-cx-ink block">{{ cand.name }}</span>
                <span class="text-[11px] text-cx-ink-3">MFL: {{ cand.mfl_code }} · {{ cand.level || 'Clinic' }} · {{ cand.county }} · {{ cand.owner_type }}</span>
              </div>
              <button
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
            <article
              v-for="pkg in context.token_packages"
              :key="pkg.item_code"
              class="rounded-cx-sm border p-4 cursor-pointer transition flex flex-col justify-between"
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
                <span class="text-cx-ink-4">{{ Number(pkg.gross_total) > 0 ? 'incl. 16% VAT' : 'No charge' }}</span>
                <span class="font-semibold" :class="selectedTopUpPackageCode === pkg.item_code ? 'text-cx-brand' : 'text-cx-ink-4'">
                  {{ selectedTopUpPackageCode === pkg.item_code ? 'Selected ✓' : 'Select' }}
                </span>
              </div>
            </article>
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

    <!-- MODAL 4: PAY VIA M-PESA PAYBILL -->
    <Dialog
      v-model:open="mpesaModalOpen"
      :title="__('Pay via M-Pesa Paybill')"
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
              <span class="text-xs text-cx-contrast block">Direct Instant Settlement with Zero Transaction Processing Surcharge</span>
            </div>
          </div>
          <span class="rounded-full bg-emerald-800/80 border border-emerald-500/50 px-2.5 py-1 text-[11px] font-semibold">
            Official Paybill
          </span>
        </div>

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
              class="mt-2.5 w-full rounded-cx-sm border border-cx-border bg-cx-surface py-1 px-2 text-xs font-semibold text-cx-ink-2 hover:bg-cx-well transition inline-flex items-center justify-center gap-1"
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
              <span class="text-[11px] text-cx-ink-3 block">KES Net Total</span>
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
          <strong class="text-cx-ink font-bold block mb-1">How to pay on your phone:</strong>
          <p>1. Open SIM Toolkit or M-Pesa App &gt; <strong>Lipa na M-Pesa</strong> &gt; <strong>Paybill</strong></p>
          <p>2. Enter Business Number <strong>{{ paybillInfo.business_number }}</strong> ({{ paybillInfo.business_name }})</p>
          <p>3. Enter Account Number <strong>{{ mpesaInvoice?.name }}</strong></p>
          <p>4. Enter Amount <strong>{{ money(mpesaInvoice?.amount || mpesaInvoice?.outstanding_amount, mpesaInvoice?.currency) }}</strong></p>
          <p>5. Enter your M-Pesa PIN and confirm payment</p>
        </div>

        <!-- M-Pesa Transaction Input Form -->
        <div class="space-y-3 pt-2 border-t border-cx-border-soft">
          <label class="block text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink">
            Submit M-Pesa Confirmation Code (from SMS)
          </label>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <input
                type="text"
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
            Or checkout using Credit/Debit Card via Paystack →
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
              {{ mpesaReportBusy ? 'Verifying Receipt…' : 'Confirm & Reconcile Payment →' }}
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
