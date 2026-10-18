<script setup>
import { computed, onMounted, ref } from 'vue'
import { call, Dialog } from 'frappe-ui'
import TokenCalculator from '@/components/TokenCalculator.vue'
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
  ois: [],
  customer_accounts: [],
  token_packages: [],
  calculator_config: {},
})

// Current Active Navigation View: 'dashboard' | 'facilities' | 'pricing' | 'billing' | 'hfr_sync' | 'profile' | 'support'
const activeView = ref('facilities')

// Sidebar collapsed state for responsive layout
const sidebarCollapsed = ref(false)

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

// Search & Filter state for Facilities Data Table
const searchQuery = ref('')
const selectedStatusFilter = ref('all') // 'all' | 'live' | 'verifying'
const selectedLevelFilter = ref('all') // 'all' | 'Level 2' | 'Level 3' | 'Level 4'
const selectedFacilityMfls = ref([]) // For table row checkbox selections
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
const hfrSearchBusy = ref(false)
const hfrSearchResults = ref([])
const hfrLinkBusy = ref(false)
const hfrSelectedCandidate = ref(null)

// Action feedback & busy states
const purchaseBusy = ref(false)
const busyId = ref('')
const notice = ref(null)
const bankTransferOis = ref('')
const copiedMfl = ref('')
const copiedKey = ref('')

// Collapsible feature categories state for GitHub-style pricing table
const expandedPricingCategories = ref({
  opd: true,
  diagnostics: true,
  ipd: true,
  billing: true,
  compliance: true,
})
const expandedFeatureDescriptions = ref({})

function toggleFeatureCategory(categoryKey) {
  expandedPricingCategories.value[categoryKey] = !expandedPricingCategories.value[categoryKey]
}

function toggleFeatureDescription(featureId) {
  expandedFeatureDescriptions.value[featureId] = !expandedFeatureDescriptions.value[featureId]
}

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

// Filtered facilities for data table
const filteredFacilities = computed(() => {
  return allFacilities.value.filter((fac) => {
    // Search query matching
    const q = searchQuery.value.trim().toLowerCase()
    if (q) {
      const matchName = fac.facility_name.toLowerCase().includes(q)
      const matchMfl = fac.mfl_code.toLowerCase().includes(q)
      const matchLevel = fac.keph_level.toLowerCase().includes(q)
      if (!matchName && !matchMfl && !matchLevel) return false
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

    return true
  })
})

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

// Selected Facility
const selectedFacility = computed(() => {
  if (selectedFacilityMfl.value) {
    const found = allFacilities.value.find(
      (f) => String(f.mfl_code).toLowerCase() === String(selectedFacilityMfl.value).toLowerCase(),
    )
    if (found) return found
  }
  return allFacilities.value[0] || null
})

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
    allFacilities.value[0]?.organization ||
    context.value.user ||
    'Healthcare Enterprise'
  )
})

const defaultCurrency = computed(() => {
  return (
    allInvoices.value[0]?.currency ||
    context.value.token_packages?.[0]?.currency ||
    'KES'
  )
})

// ---------------------------------------------------------------------------
// GitHub-Style Detailed Feature Comparison Matrix
// ---------------------------------------------------------------------------
const featureComparisonCategories = [
  {
    key: 'opd',
    title: 'Outpatient & Patient Registration (OPD)',
    description: 'Patient master index, intake, triage, and outpatient consultation workflows.',
    features: [
      {
        id: 'patient_reg',
        name: 'Patient Intake & Biometrics',
        description: 'Instant master patient index (MPI) creation, National ID and DHA Client Registry integration for deduplicated patient records.',
        values: ['400 MPI Intakes', '1,000 MPI Intakes', '2,800 MPI Intakes', 'Unlimited MPI Intakes'],
      },
      {
        id: 'opd_consult',
        name: 'Consultation Encounters & ICD-10',
        description: 'Doctor examination notes, standardized diagnosis coding (ICD-10 / Health Facility Registry), vitals capture, and referral tracking.',
        values: ['10 full encounters', '~70 OPD visits', '~200 OPD visits', '~440 OPD visits'],
      },
      {
        id: 'triage_vitals',
        name: 'Triage & Nursing Vitals Station',
        description: 'Automated blood pressure, pulse, temperature, and BMI charting with clinical alert triggers for high-risk patients.',
        values: ['Included', 'Included', 'Included', 'Priority Support'],
      },
      {
        id: 'chronic_care',
        name: 'Specialized Clinics & Chronic Care',
        description: 'Dedicated follow-up visit tracking for hypertension, diabetes, maternal child health (MCH), and oncology clinics.',
        values: ['Standard', 'Standard', 'Advanced Programs', 'Full Multi-Specialty'],
      },
    ],
  },
  {
    key: 'diagnostics',
    title: 'Diagnostics, Laboratory & Pharmacy',
    description: 'Electronic laboratory orders, e-prescriptions, and dispensary inventory tracking.',
    features: [
      {
        id: 'lab_orders',
        name: 'Laboratory Investigation Orders',
        description: 'Doctor-to-lab electronic ordering, lab sample barcoding, result verification, and automated normal-range flagging.',
        values: ['Basic Labs', 'Full OPD Labs', 'Full Labs + Bonus', 'High-Volume Pathology'],
      },
      {
        id: 'e_prescriptions',
        name: 'Electronic Prescriptions (e-Rx)',
        description: 'Direct prescription transmission to pharmacy, drug dosage validation, contraindication alerts, and generic substitutes.',
        values: ['Standard', 'Standard', 'Smart Formulary', 'Automated Dispensing'],
      },
      {
        id: 'pharmacy_stock',
        name: 'Dispensary Stock & Batch Tracking',
        description: 'Automatic deduction of inventory upon medication dispensing, expiry date tracking, and low-stock reorder notices.',
        values: ['Standard', 'Standard', 'Batch & Expiry', 'Multi-Store Inventory'],
      },
      {
        id: 'imaging_orders',
        name: 'Diagnostic Imaging (X-Ray & Ultrasound)',
        description: 'Order capture and report attachment for radiology, ultrasound, and ECG diagnostics.',
        values: ['Manual Upload', 'Standard Imaging', 'Integrated PACS/DICOM', 'High-Res Multi-Modality'],
      },
    ],
  },
  {
    key: 'ipd',
    title: 'Inpatient & Surgical Services (IPD)',
    description: 'Ward allocation, nursing medication charts, and procedural encounter tracking.',
    features: [
      {
        id: 'ward_beds',
        name: 'Inpatient Ward & Bed Tracking',
        description: 'Real-time bed occupancy overview, patient room transfers, nursing notes, and daily ward round tracking.',
        values: ['Not included', 'Day-care only', 'Up to 25 beds', 'Unlimited Wards & Beds'],
      },
      {
        id: 'surgical_proc',
        name: 'Minor & Major Surgical Procedures',
        description: 'Pre-op checklists, surgeon and anesthesia notes, theatre usage recording, and post-op recovery logs.',
        values: ['Not included', 'Minor procedures', 'Minor & General', 'Full Surgical Theatre'],
      },
      {
        id: 'discharge_claim',
        name: 'Discharge Summaries & IPD Invoicing',
        description: 'Consolidated itemized patient discharge bills with all medications, bed charges, and lab investigations mapped automatically.',
        values: ['Basic OPD Receipt', 'Itemized Invoice', 'Automated Claims', 'Complete Audit Pack'],
      },
    ],
  },
  {
    key: 'billing',
    title: 'Billing, M-Pesa POS & Insurance Claims',
    description: 'Cashier point-of-sale, SHA e-claims, and insurer pre-authorizations.',
    features: [
      {
        id: 'mpesa_c2b',
        name: 'M-Pesa STK Push & C2B POS',
        description: 'Cashier initiates instant M-Pesa prompt on patient phone; real-time payment confirmation without manual reference entry.',
        values: ['Manual Paybill', 'Automated STK Push', 'Automated STK Push', 'Multi-Till Enterprise'],
      },
      {
        id: 'sha_claims',
        name: 'Social Health Authority (SHA) e-Claims',
        description: 'Standardized digital claim generation mapped to SHA / NHIF benefit packages, pre-auth codes, and patient biometric token IDs.',
        values: ['Self-file export', 'SHA e-Claims Ready', 'Automated Claim Batch', 'Direct HIE Pipeline'],
      },
      {
        id: 'private_insurance',
        name: 'Private Insurance & Corporate Accounts',
        description: 'Smart pre-authorization tracking, deductible verification, and corporate debtor statement generation.',
        values: ['Cash-only', 'Basic Invoicing', 'Multi-Payer Direct', 'Complete Corporate POS'],
      },
    ],
  },
  {
    key: 'compliance',
    title: 'Health Facility Registry Compliance, Network & Support',
    description: 'National health registry synchronization and dedicated clinical SLA.',
    features: [
      {
        id: 'hfr_sync',
        name: 'Health Facility Registry Sync',
        description: 'Automated synchronization with official Health Facility Registry (HFR) validating facility license and KEPH level.',
        values: ['Quarterly', 'Monthly', 'Real-Time Sync', 'Continuous DHA Link'],
      },
      {
        id: 'data_protection',
        name: 'Data Protection Act (Kenya) Compliant',
        description: 'Locally hosted, encrypted patient data meeting Office of Data Protection Commissioner (ODPC) healthcare standards.',
        values: ['Compliant', 'Compliant', 'Compliant', 'Compliant + Audit Log'],
      },
      {
        id: 'sla_support',
        name: 'Support SLA & Dedicated Account Lead',
        description: 'Priority helpdesk response time and assigned Partner Network Lead for operational troubleshooting.',
        values: ['Community Email', 'Standard 24h SLA', 'Priority 4h + WhatsApp', 'Dedicated 1h Hotline'],
      },
    ],
  },
]

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
  notice.value = null
  try {
    const res = await call('crm.api.customer_experience.lookup_facilities_by_owner_id', {
      national_id: userProfile.value.national_id || undefined,
    })
    const data = unwrap(res)
    hfrOwnerSearchResults.value = Array.isArray(data) ? data : []
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
    notice.value = {
      tone: 'error',
      text: error?.messages?.[0] || 'Unable to discover facilities by National ID.',
    }
  } finally {
    hfrOwnerSearchBusy.value = false
  }
}

function openTopUpModal(facility = null) {
  if (facility) {
    selectedFacilityMfl.value = facility.mfl_code
  } else if (!selectedFacilityMfl.value && allFacilities.value.length) {
    selectedFacilityMfl.value = allFacilities.value[0].mfl_code
  }
  if (!selectedTopUpPackageCode.value && context.value.token_packages?.length) {
    selectedTopUpPackageCode.value =
      context.value.token_packages.find((p) => p.item_code === 'CV-TOKEN-GROWTH')
        ?.item_code || context.value.token_packages[0].item_code
  }
  topUpModalOpen.value = true
}

function openAddFacilityModal() {
  hfrSearchQuery.value = ''
  hfrSearchResults.value = []
  hfrSelectedCandidate.value = null
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
  if (!selectedFacilityMfl.value && allFacilities.value.length) {
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

onMounted(async () => {
  try {
    await refreshContext()
    await loadUserProfile()
    await verifyReturnedPayment()
  } catch (error) {
    errorMessage.value = error?.messages?.[0] || 'Failed to load portal.'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="min-h-screen bg-[#f8fafc] text-slate-800 flex flex-col font-sans antialiased">
    <!-- Notice Toast Bar -->
    <div
      v-if="notice"
      class="border-b px-4 py-2.5 text-xs font-semibold flex items-center justify-between z-50 sticky top-0"
      :class="{
        'bg-emerald-50 text-emerald-900 border-emerald-200': notice.tone === 'success',
        'bg-amber-50 text-amber-900 border-amber-200': notice.tone === 'pending',
        'bg-rose-50 text-rose-900 border-rose-200': notice.tone === 'error',
      }"
    >
      <div class="flex items-center gap-2 max-w-5xl mx-auto w-full">
        <span>{{ notice.tone === 'success' ? '✓' : notice.tone === 'pending' ? '⏱' : '⚠️' }}</span>
        <span>{{ notice.text }}</span>
      </div>
      <button type="button" class="underline ml-4 shrink-0" @click="notice = null">Dismiss</button>
    </div>

    <div class="flex-1 flex overflow-hidden">
      <!-- 1. PERSISTENT COLLAPSIBLE SIDEBAR (Exact SaaS Pattern from Screenshot) -->
      <aside
        class="bg-white border-r border-slate-200 flex flex-col shrink-0 transition-all duration-200 select-none z-30"
        :class="sidebarCollapsed ? 'w-16' : 'w-64'"
      >
        <!-- Brand Header -->
        <div class="h-16 border-b border-slate-200 flex items-center justify-between px-4">
          <div class="flex items-center gap-2.5 overflow-hidden" v-if="!sidebarCollapsed">
            <div class="size-8 rounded-lg bg-[#bc1823] text-white flex items-center justify-center font-bold text-sm shadow-xs shrink-0">
              T
            </div>
            <div class="truncate">
              <span class="font-extrabold text-sm tracking-tight text-slate-900 block leading-tight">
                Tiberbu <span class="text-[#bc1823]">CareVerse</span>
              </span>
              <span class="text-[10px] font-semibold text-slate-600 uppercase tracking-wider block">
                HMIS Enterprise
              </span>
            </div>
          </div>
          <div v-else class="mx-auto">
            <div class="size-8 rounded-lg bg-[#bc1823] text-white flex items-center justify-center font-bold text-sm shadow-xs">
              T
            </div>
          </div>

          <button
            type="button"
            class="text-slate-600 hover:text-slate-800 p-1 rounded-md hover:bg-slate-100 transition hidden sm:inline-block"
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
            class="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-bold transition text-left"
            :class="
              activeView === 'dashboard'
                ? 'bg-blue-50 text-blue-700 shadow-xs'
                : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
            "
            @click="activeView = 'dashboard'"
          >
            <span class="text-base shrink-0">📊</span>
            <span v-if="!sidebarCollapsed" class="truncate">Dashboard</span>
          </button>

          <!-- 2. Facilities (Active in Screenshot) -->
          <button
            type="button"
            class="w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-xs font-bold transition text-left"
            :class="
              activeView === 'facilities'
                ? 'bg-blue-50 text-blue-700 shadow-xs'
                : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
            "
            @click="activeView = 'facilities'"
          >
            <div class="flex items-center gap-3 truncate">
              <span class="text-base shrink-0">🏥</span>
              <span v-if="!sidebarCollapsed" class="truncate">Facilities</span>
            </div>
            <span
              v-if="!sidebarCollapsed"
              class="rounded-full px-2 py-0.5 text-[10px] font-bold"
              :class="activeView === 'facilities' ? 'bg-blue-100 text-blue-800' : 'bg-slate-100 text-slate-600'"
            >
              {{ facilityCount }}
            </span>
          </button>

          <!-- 3. Plans & Pricing (GitHub Style) -->
          <button
            type="button"
            class="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-bold transition text-left"
            :class="
              activeView === 'pricing'
                ? 'bg-blue-50 text-blue-700 shadow-xs'
                : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
            "
            @click="activeView = 'pricing'"
          >
            <span class="text-base shrink-0">🪙</span>
            <span v-if="!sidebarCollapsed" class="truncate">Plans & Pricing</span>
          </button>

          <!-- 4. Billing & Invoices -->
          <button
            type="button"
            class="w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-xs font-bold transition text-left"
            :class="
              activeView === 'billing'
                ? 'bg-blue-50 text-blue-700 shadow-xs'
                : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
            "
            @click="activeView = 'billing'"
          >
            <div class="flex items-center gap-3 truncate">
              <span class="text-base shrink-0">💳</span>
              <span v-if="!sidebarCollapsed" class="truncate">Billing & Invoices</span>
            </div>
            <span
              v-if="!sidebarCollapsed && openInvoiceCount > 0"
              class="rounded-full bg-amber-500 text-white px-2 py-0.5 text-[10px] font-bold"
            >
              {{ openInvoiceCount }}
            </span>
          </button>

          <!-- 5. Health Facility Registry Sync -->
          <button
            type="button"
            class="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-bold transition text-left"
            :class="
              activeView === 'hfr_sync'
                ? 'bg-blue-50 text-blue-700 shadow-xs'
                : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
            "
            @click="activeView = 'hfr_sync'"
          >
            <span class="text-base shrink-0">🔄</span>
            <span v-if="!sidebarCollapsed" class="truncate">Facility Registry Sync</span>
          </button>

          <!-- 6. My Profile (National ID & Identity) -->
          <button
            type="button"
            class="w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-xs font-bold transition text-left"
            :class="
              activeView === 'profile'
                ? 'bg-blue-50 text-blue-700 shadow-xs'
                : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
            "
            @click="activeView = 'profile'"
          >
            <div class="flex items-center gap-3 truncate">
              <span class="text-base shrink-0">👤</span>
              <span v-if="!sidebarCollapsed" class="truncate">My Profile</span>
            </div>
            <span
              v-if="!sidebarCollapsed && userProfile.masked_national_id"
              class="rounded-full bg-slate-100 text-slate-700 font-mono px-2 py-0.5 text-[10px]"
            >
              {{ userProfile.masked_national_id }}
            </span>
          </button>

          <!-- 7. Network Support -->
          <button
            type="button"
            class="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-bold transition text-left"
            :class="
              activeView === 'support'
                ? 'bg-blue-50 text-blue-700 shadow-xs'
                : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
            "
            @click="activeView = 'support'"
          >
            <span class="text-base shrink-0">💬</span>
            <span v-if="!sidebarCollapsed" class="truncate">Network Support</span>
          </button>
        </nav>

        <!-- Sidebar Footer: Organization Identity -->
        <div class="p-3 border-t border-slate-200" v-if="!sidebarCollapsed">
          <div
            class="rounded-xl bg-slate-50 border border-slate-100 p-2.5 flex items-center justify-between cursor-pointer hover:bg-slate-100/80 transition"
            @click="activeView = 'profile'"
            title="View Profile & Identification"
          >
            <div class="truncate mr-2">
              <span class="text-xs font-bold text-slate-900 block truncate">
                {{ primaryOrganizationName }}
              </span>
              <span class="text-[10px] text-slate-600 block truncate font-mono">
                {{ userProfile.masked_national_id ? `ID: ${userProfile.masked_national_id}` : context.user }}
              </span>
            </div>
            <a
              href="/api/method/logout"
              title="Sign Out"
              class="text-slate-600 hover:text-rose-600 p-1.5 rounded hover:bg-white transition"
              @click.stop
            >
              <svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
              </svg>
            </a>
          </div>
        </div>
      </aside>

      <!-- 2. MAIN APPLICATION CONTENT -->
      <div class="flex-1 flex flex-col min-w-0 overflow-y-auto">
        <!-- Top App Bar (Global Search & Quick Actions) -->
        <header class="h-16 bg-white border-b border-slate-200 px-6 flex items-center justify-between shrink-0 sticky top-0 z-20">
          <!-- Search Bar -->
          <div class="relative w-80 lg:w-96">
            <svg class="size-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="11" cy="11" r="8"></circle>
              <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
            </svg>
            <input
              type="text"
              v-model="searchQuery"
              placeholder="Search facilities, MFL codes, invoices..."
              class="w-full rounded-xl bg-slate-50 border border-slate-200 pl-9 pr-12 py-2 text-xs font-medium text-slate-900 placeholder:text-slate-400 focus:bg-white focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/10 transition"
            />
            <span class="absolute right-2.5 top-1/2 -translate-y-1/2 rounded bg-slate-200/60 px-1.5 py-0.5 text-[10px] font-mono text-slate-500">
              ⌘K
            </span>
          </div>

          <!-- Top Actions -->
          <div class="flex items-center gap-3">
            <span class="hidden md:inline-flex items-center gap-1.5 rounded-full bg-emerald-50 border border-emerald-200 px-2.5 py-1 text-[11px] font-bold text-emerald-800">
              <span class="size-1.5 rounded-full bg-emerald-600 animate-pulse"></span>
              <span>Registry Verified</span>
            </span>

            <button
              type="button"
              class="inline-flex items-center gap-1.5 rounded-xl bg-blue-600 px-3.5 py-2 text-xs font-bold text-white shadow-xs hover:bg-blue-700 transition"
              @click="openAddFacilityModal()"
            >
              <span class="text-sm leading-none">+</span>
              <span>Add Facility</span>
            </button>

            <button
              type="button"
              class="inline-flex items-center gap-1.5 rounded-xl bg-[#bc1823] px-3.5 py-2 text-xs font-bold text-white shadow-xs hover:bg-[#a3141d] transition"
              @click="openTopUpModal()"
            >
              <span>🪙</span>
              <span>Top Up</span>
            </button>
          </div>
        </header>

        <!-- Dynamic Main Views -->
        <main class="p-6 max-w-7xl w-full mx-auto space-y-6">
          <!-- ============================================================== -->
          <!-- VIEW A: FACILITIES TABLE (Exact match to screenshot structure) -->
          <!-- ============================================================== -->
          <div v-if="activeView === 'facilities'" class="space-y-4">
            <!-- Breadcrumbs / Page Header -->
            <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div>
                <h1 class="text-2xl font-extrabold text-slate-900 tracking-tight">
                  Facilities
                </h1>
                <p class="text-xs text-slate-600 mt-0.5">
                  Manage registered clinic branches, track Health Facility Registry verification, and monitor token capacity.
                </p>
              </div>

              <!-- Top Table Actions (Export & Add Facility) -->
              <div class="flex items-center gap-2">
                <button
                  type="button"
                  class="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50 shadow-2xs"
                  @click="openAddFacilityModal()"
                >
                  <span>🔄 Sync Facility Registry</span>
                </button>
                <button
                  type="button"
                  class="inline-flex items-center gap-1.5 rounded-xl bg-blue-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-blue-700 transition"
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
                    placeholder="Search by name, MFL, county..."
                    class="w-full rounded-xl bg-white border border-slate-200 pl-8 pr-3 py-1.5 text-xs font-medium text-slate-800 placeholder:text-slate-400 focus:outline-none focus:border-blue-500 shadow-2xs"
                  />
                  <svg class="size-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="11" cy="11" r="8"></circle>
                    <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                  </svg>
                </div>

                <!-- Status Filter -->
                <select
                  v-model="selectedStatusFilter"
                  class="rounded-xl bg-white border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-2xs focus:outline-none focus:border-blue-500"
                >
                  <option value="all">All Statuses</option>
                  <option value="live">Live on Registry</option>
                  <option value="verifying">Verification Pending</option>
                </select>

                <!-- Level Filter -->
                <select
                  v-model="selectedLevelFilter"
                  class="rounded-xl bg-white border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-2xs focus:outline-none focus:border-blue-500"
                >
                  <option value="all">All KEPH Levels</option>
                  <option value="Level 2">Level 2 Dispensary</option>
                  <option value="Level 3">Level 3 Health Centre</option>
                  <option value="Level 4">Level 4 Hospital</option>
                </select>
              </div>

              <!-- View Switcher -->
              <div class="flex items-center gap-1.5">
                <button
                  type="button"
                  class="rounded-lg border p-1.5 text-xs"
                  :class="facilityViewMode === 'table' ? 'bg-slate-100 border-slate-300 text-slate-900 font-bold' : 'bg-white border-slate-200 text-slate-500'"
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
                  class="rounded-lg border p-1.5 text-xs"
                  :class="facilityViewMode === 'cards' ? 'bg-slate-100 border-slate-300 text-slate-900 font-bold' : 'bg-white border-slate-200 text-slate-500'"
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

            <!-- TABLE VIEW -->
            <div v-if="facilityViewMode === 'table'" class="bg-white rounded-2xl border border-slate-200 shadow-2xs overflow-hidden">
              <div class="overflow-x-auto">
                <table class="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr class="border-b border-slate-200 bg-slate-50/75 text-[11px] font-bold uppercase tracking-wider text-slate-500">
                      <th class="py-3 px-4 w-10">
                        <input type="checkbox" class="rounded border-slate-300 text-blue-600 focus:ring-0" />
                      </th>
                      <th class="py-3 px-4">Facility & Network</th>
                      <th class="py-3 px-4">KEPH Level</th>
                      <th class="py-3 px-4">MFL Code</th>
                      <th class="py-3 px-4">Registry Status</th>
                      <th class="py-3 px-4">Plan & Recent Purchase</th>
                      <th class="py-3 px-4 text-right">Care Tokens</th>
                      <th class="py-3 px-4 text-right">Settlement & Actions</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-slate-100">
                    <tr
                      v-for="facility in filteredFacilities"
                      :key="facility.mfl_code"
                      class="hover:bg-slate-50/80 transition"
                    >
                      <!-- Checkbox -->
                      <td class="py-3.5 px-4">
                        <input
                          type="checkbox"
                          :value="facility.mfl_code"
                          v-model="selectedFacilityMfls"
                          class="rounded border-slate-300 text-blue-600 focus:ring-0"
                        />
                      </td>

                      <!-- Name & Location & Network -->
                      <td class="py-3.5 px-4 font-semibold text-slate-900">
                        <div class="flex items-center gap-3">
                          <div class="size-8 rounded-lg bg-blue-50 text-blue-700 flex items-center justify-center font-bold text-xs shrink-0 border border-blue-100">
                            🏥
                          </div>
                          <div>
                            <span class="font-bold text-slate-900 block">{{ facility.facility_name }}</span>
                            <span class="inline-flex items-center gap-1 rounded bg-slate-100 text-slate-700 px-1.5 py-0.5 text-[10px] font-medium mt-0.5 border border-slate-200/60">
                              <span>🌐</span>
                              <span>{{ facility.network }}</span>
                            </span>
                          </div>
                        </div>
                      </td>

                      <!-- Level -->
                      <td class="py-3.5 px-4">
                        <span class="inline-flex items-center rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-700 border border-slate-200">
                          {{ facility.keph_level }}
                        </span>
                      </td>

                      <!-- MFL Code -->
                      <td class="py-3.5 px-4">
                        <button
                          type="button"
                          class="font-mono text-xs font-semibold text-slate-700 hover:text-blue-600 inline-flex items-center gap-1.5 bg-slate-50 px-2 py-0.5 rounded border border-slate-200/60"
                          @click="copyMfl(facility.mfl_code)"
                        >
                          <span>{{ facility.mfl_code }}</span>
                          <span class="text-[10px] text-slate-600">{{ copiedMfl === facility.mfl_code ? '✓' : '📋' }}</span>
                        </button>
                      </td>

                      <!-- Status Badge -->
                      <td class="py-3.5 px-4">
                        <span
                          class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-bold border"
                          :class="
                            facility.go_live
                              ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                              : 'bg-amber-50 text-amber-800 border-amber-200'
                          "
                        >
                          <span class="size-1.5 rounded-full" :class="facility.go_live ? 'bg-emerald-600' : 'bg-amber-600'"></span>
                          <span>{{ facility.go_live ? 'Live' : 'Verifying' }}</span>
                        </span>
                      </td>

                      <!-- Plan & Recent Purchase -->
                      <td class="py-3.5 px-4 font-medium text-slate-700">
                        <span class="font-bold text-slate-900 block">{{ facility.token_package || 'No active plan' }}</span>
                        <span v-if="facility.recent_purchase" class="text-[11px] text-slate-500 font-mono block mt-0.5">
                          {{ facility.recent_purchase.package_name }}: {{ money(facility.recent_purchase.amount, facility.recent_purchase.currency) }} · {{ facility.recent_purchase.date }}
                        </span>
                      </td>

                      <!-- Tokens -->
                      <td class="py-3.5 px-4 text-right">
                        <span class="font-extrabold text-[#bc1823] font-mono text-sm inline-flex items-center gap-1">
                          <span>🪙</span>
                          <span>{{ (facility.token_quantity || 0).toLocaleString() }}</span>
                        </span>
                      </td>

                      <!-- Actions & Direct M-Pesa Settlement -->
                      <td class="py-3.5 px-4 text-right">
                        <div class="flex items-center justify-end gap-1.5 flex-wrap">
                          <button
                            v-if="facility.invoice_summary?.has_outstanding"
                            type="button"
                            class="rounded-lg bg-emerald-600 px-2.5 py-1 text-xs font-bold text-white hover:bg-emerald-700 transition shadow-xs inline-flex items-center gap-1 shrink-0"
                            @click="openMpesaModalForFacility(facility)"
                            title="Pay outstanding invoice via M-Pesa"
                          >
                            <span>📱 Pay M-Pesa: {{ money(facility.invoice_summary.outstanding_amount, facility.invoice_summary.currency) }} →</span>
                          </button>
                          <button
                            type="button"
                            class="rounded-lg bg-slate-900 px-2.5 py-1 text-xs font-bold text-white hover:bg-black transition shadow-xs"
                            @click="openTopUpModal(facility)"
                          >
                            Top Up
                          </button>
                          <button
                            type="button"
                            class="rounded-lg border border-slate-200 bg-white p-1 text-slate-600 hover:bg-slate-50"
                            title="Sizing Calculator"
                            @click="openCalculatorModal(facility)"
                          >
                            🧮
                          </button>
                        </div>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <!-- Footer summary -->
              <div class="p-4 bg-slate-50 border-t border-slate-200 flex items-center justify-between text-xs text-slate-500 font-medium">
                <span>Showing {{ filteredFacilities.length }} of {{ allFacilities.length }} registered clinics</span>
                <span>All records verified via Digital Health Agency (DHA) Health Facility Registry</span>
              </div>
            </div>

            <!-- CARDS VIEW (Optional toggle) -->
            <div v-else class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              <article
                v-for="facility in filteredFacilities"
                :key="facility.mfl_code"
                class="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs flex flex-col justify-between hover:border-blue-400 transition"
              >
                <div>
                  <div class="flex items-start justify-between gap-2">
                    <div>
                      <h3 class="font-bold text-base text-slate-900">{{ facility.facility_name }}</h3>
                      <p class="text-xs text-slate-500 mt-0.5">{{ facility.keph_level }} · MFL: {{ facility.mfl_code }}</p>
                      <span class="inline-flex items-center gap-1 rounded bg-slate-100 text-slate-700 px-1.5 py-0.5 text-[10px] font-medium mt-1 border border-slate-200/60">
                        <span>🌐</span>
                        <span>{{ facility.network }}</span>
                      </span>
                    </div>
                    <span
                      class="rounded-full px-2 py-0.5 text-[10px] font-bold border shrink-0"
                      :class="facility.go_live ? 'bg-emerald-50 text-emerald-800 border-emerald-200' : 'bg-amber-50 text-amber-800 border-amber-200'"
                    >
                      {{ facility.go_live ? 'Live' : 'Verifying' }}
                    </span>
                  </div>

                  <div class="mt-4 rounded-xl bg-slate-50 border border-slate-100 p-3 space-y-1.5 text-xs">
                    <div class="flex justify-between text-slate-600">
                      <span>Active Plan:</span>
                      <strong class="text-slate-900">{{ facility.token_package || 'None' }}</strong>
                    </div>
                    <div v-if="facility.recent_purchase" class="flex justify-between text-slate-600 text-[11px]">
                      <span>Recent Order:</span>
                      <span class="font-mono text-slate-800">{{ money(facility.recent_purchase.amount, facility.recent_purchase.currency) }} ({{ facility.recent_purchase.date }})</span>
                    </div>
                    <div class="flex justify-between text-slate-600">
                      <span>Token Runway:</span>
                      <strong class="text-[#bc1823]">🪙 {{ (facility.token_quantity || 0).toLocaleString() }} tokens</strong>
                    </div>
                    <div v-if="facility.invoice_summary?.has_outstanding" class="flex justify-between items-center pt-1.5 border-t border-slate-200/60">
                      <span class="font-bold text-amber-800">Due Balance:</span>
                      <strong class="font-bold text-amber-900">{{ money(facility.invoice_summary.outstanding_amount, facility.invoice_summary.currency) }}</strong>
                    </div>
                  </div>
                </div>

                <div class="mt-4 pt-3 border-t border-slate-100 space-y-2">
                  <button
                    v-if="facility.invoice_summary?.has_outstanding"
                    type="button"
                    class="w-full rounded-xl bg-emerald-600 px-3 py-2 text-xs font-bold text-white hover:bg-emerald-700 transition flex items-center justify-center gap-1.5 shadow-xs"
                    @click="openMpesaModalForFacility(facility)"
                  >
                    <span>📱 Pay M-Pesa: {{ money(facility.invoice_summary.outstanding_amount, facility.invoice_summary.currency) }} →</span>
                  </button>
                  <div class="flex items-center gap-2">
                    <button
                      type="button"
                      class="flex-1 rounded-xl bg-slate-900 px-3 py-2 text-xs font-bold text-white hover:bg-black transition"
                      @click="openTopUpModal(facility)"
                    >
                      + Top Up Tokens
                    </button>
                    <button
                      type="button"
                      class="rounded-xl border border-slate-200 bg-white p-2 text-slate-700 hover:bg-slate-50"
                      @click="openCalculatorModal(facility)"
                      title="Sizing Calculator"
                    >
                      🧮
                    </button>
                  </div>
                </div>
              </article>
            </div>
          </div>

          <!-- ============================================================== -->
          <!-- VIEW B: DASHBOARD / EXECUTIVE RUNWAY OVERVIEW                   -->
          <!-- ============================================================== -->
          <div v-if="activeView === 'dashboard'" class="space-y-6">
            <div>
              <h1 class="text-2xl font-extrabold text-slate-900 tracking-tight">Executive Dashboard</h1>
              <p class="text-xs text-slate-600 mt-0.5">Overview of health system capacity, live registry compliance, and financial settlement.</p>
            </div>

            <!-- Top 3 Executive Metrics -->
            <div class="grid gap-4 sm:grid-cols-3">
              <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs space-y-3">
                <span class="text-xs font-bold uppercase tracking-wider text-slate-600 block">Total Token Runway</span>
                <div class="flex items-baseline gap-2">
                  <span class="text-3xl font-extrabold text-[#bc1823] tracking-tight leading-none">{{ totalTokenCount.toLocaleString() }}</span>
                  <span class="text-xs font-bold text-slate-600">Care Tokens</span>
                </div>
                <p class="text-xs text-slate-600 leading-relaxed">
                  Supports approx. <strong>~{{ Math.floor(totalTokenCount / 15) }} clinical patient encounters</strong> across all registered clinics.
                </p>
                <div class="pt-2 border-t border-slate-100">
                  <button type="button" class="text-xs font-bold text-[#bc1823] hover:underline" @click="openTopUpModal()">
                    + Top Up Runway Capacity →
                  </button>
                </div>
              </div>

              <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs space-y-3">
                <span class="text-xs font-bold uppercase tracking-wider text-slate-600 block">Health Facility Registry Compliance</span>
                <div class="flex items-baseline gap-2">
                  <span class="text-3xl font-extrabold text-slate-900 tracking-tight leading-none">{{ liveFacilitiesCount }} / {{ facilityCount }}</span>
                  <span class="text-xs font-bold text-emerald-700">Clinics Live</span>
                </div>
                <p class="text-xs text-slate-600 leading-relaxed">
                  Synchronized with the official Health Facility Registry (HFR) & Partner Network.
                </p>
                <div class="pt-2 border-t border-slate-100">
                  <button type="button" class="text-xs font-bold text-blue-600 hover:underline" @click="activeView = 'facilities'">
                    View Facility Registry →
                  </button>
                </div>
              </div>

              <div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-2xs space-y-3" :class="openInvoiceCount > 0 ? 'border-amber-200 bg-amber-50/40' : ''">
                <span class="text-xs font-bold uppercase tracking-wider text-slate-600 block">Settlement & Invoices</span>
                <div class="flex items-baseline gap-2">
                  <span class="text-3xl font-extrabold tracking-tight leading-none" :class="openInvoiceCount > 0 ? 'text-amber-900' : 'text-slate-900'">
                    {{ openInvoiceCount > 0 ? money(totalOutstandingAmount) : 'Paid' }}
                  </span>
                  <span v-if="openInvoiceCount > 0" class="text-xs font-bold text-amber-700">Due</span>
                </div>
                <p class="text-xs text-slate-600 leading-relaxed">
                  {{ openInvoiceCount > 0 ? `${openInvoiceCount} invoice awaiting payment via M-Pesa / Bank` : 'All invoices settled with zero outstanding balance.' }}
                </p>
                <div class="pt-2 border-t border-slate-100">
                  <button type="button" class="text-xs font-bold text-slate-800 hover:underline" @click="activeView = 'billing'">
                    Go to Invoices & Billing →
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- ============================================================== -->
          <!-- VIEW C: PLANS & PRICING (GitHub-Style Minimalist Architecture)  -->
          <!-- ============================================================== -->
          <div v-if="activeView === 'pricing'" class="space-y-8">
            <div class="max-w-3xl">
              <span class="inline-flex items-center gap-1.5 rounded-full border border-blue-200 bg-blue-50 px-3 py-0.5 text-xs font-bold uppercase tracking-wider text-blue-800">
                Consumption-Based HMIS Pricing
              </span>
              <h1 class="text-3xl font-extrabold text-slate-900 tracking-tight mt-2">
                CareVerse Token Plans & Capacity
              </h1>
              <p class="text-sm text-slate-600 mt-2 leading-relaxed">
                Tiberbu operates on transparent, transactional Care Tokens. Pay only for verified patient visits, labs, and e-claims with zero seat licenses or hidden server fees.
              </p>
            </div>

            <!-- Top 4 Minimalist Pricing Cards (GitHub Style) -->
            <div class="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
              <article
                v-for="pkg in context.token_packages"
                :key="pkg.item_code"
                class="rounded-2xl border bg-white p-6 shadow-2xs flex flex-col justify-between transition hover:border-slate-300 hover:shadow-xs"
                :class="pkg.item_code === 'CV-TOKEN-GROWTH' ? 'border-2 border-blue-600 ring-4 ring-blue-500/10' : 'border-slate-200'"
              >
                <div>
                  <!-- Tier Header -->
                  <div class="flex items-center justify-between">
                    <h3 class="font-extrabold text-lg text-slate-900">{{ pkg.display_name }}</h3>
                    <span
                      v-if="pkg.item_code === 'CV-TOKEN-GROWTH'"
                      class="rounded-full bg-blue-100 text-blue-800 px-2.5 py-0.5 text-[10px] font-bold uppercase"
                    >
                      Most Popular
                    </span>
                    <span
                      v-else-if="Number(pkg.price_ex_vat ?? pkg.price ?? 0) === 0"
                      class="rounded-full bg-slate-100 text-slate-700 px-2 py-0.5 text-[10px] font-bold"
                    >
                      Free Trial
                    </span>
                  </div>

                  <!-- Short plain-language description -->
                  <p class="text-xs text-slate-500 mt-2 min-h-10 leading-normal">
                    {{ pkg.coverage_summary || pkg.description }}
                  </p>

                  <!-- Price -->
                  <div class="mt-4 pt-4 border-t border-slate-100">
                    <div class="flex items-baseline gap-1">
                      <span class="text-2xl font-extrabold text-slate-900">
                        {{ Number(pkg.price_ex_vat ?? pkg.price ?? 0) === 0 ? 'KES 0' : money(pkg.price_ex_vat ?? pkg.price, pkg.currency) }}
                      </span>
                      <span class="text-xs text-slate-500 font-medium">/ month</span>
                    </div>
                    <span class="text-[11px] text-slate-400 block mt-0.5">
                      {{ Number(pkg.gross_total) > 0 ? `${money(pkg.gross_total, pkg.currency)} incl. 16% VAT` : 'Zero commitment' }}
                    </span>
                  </div>

                  <!-- Token Quantity Pill -->
                  <div class="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-red-50 border border-red-200/70 px-3 py-1.5 text-xs font-bold text-[#bc1823]">
                    <span>🪙</span>
                    <span>{{ (pkg.token_quantity || 100).toLocaleString() }} Care Tokens</span>
                  </div>
                </div>

                <!-- CTA Button -->
                <div class="mt-6 pt-4 border-t border-slate-100">
                  <button
                    type="button"
                    class="w-full rounded-xl py-2.5 px-4 text-xs font-bold transition shadow-xs text-center"
                    :class="
                      pkg.item_code === 'CV-TOKEN-GROWTH'
                        ? 'bg-blue-600 text-white hover:bg-blue-700'
                        : 'bg-slate-900 text-white hover:bg-black'
                    "
                    @click="selectPlanFromPricingTab(pkg)"
                  >
                    {{ Number(pkg.price_ex_vat ?? pkg.price ?? 0) === 0 ? 'Activate Free Trial' : `Select ${pkg.display_name}` }}
                  </button>
                </div>
              </article>
            </div>

            <!-- GitHub-Style Collapsible Detailed Feature Comparison Table -->
            <div class="bg-white rounded-2xl border border-slate-200 shadow-2xs overflow-hidden mt-12">
              <div class="p-6 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div>
                  <h2 class="text-xl font-bold text-slate-900 tracking-tight">
                    Detailed Feature & Workflow Comparison
                  </h2>
                  <p class="text-xs text-slate-600 mt-1">
                    Expand any module to see plain-language clinical workflow descriptions and what is covered in each tier.
                  </p>
                </div>
                <button
                  type="button"
                  class="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50"
                  @click="openCalculatorModal()"
                >
                  <span>🧮 Launch Sizing Calculator</span>
                </button>
              </div>

              <!-- Table Headers -->
              <div class="overflow-x-auto">
                <table class="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr class="border-b border-slate-200 bg-slate-50 text-slate-700 font-extrabold">
                      <th class="py-4 px-6 w-2/5">Clinical & Operational Capabilities</th>
                      <th class="py-4 px-4 text-center w-36">Free Trial</th>
                      <th class="py-4 px-4 text-center w-36">Starter</th>
                      <th class="py-4 px-4 text-center w-36 bg-blue-50/50 text-blue-900">Growth</th>
                      <th class="py-4 px-4 text-center w-36">Scale</th>
                    </tr>
                  </thead>

                  <tbody>
                    <template v-for="category in featureComparisonCategories" :key="category.key">
                      <!-- Collapsible Category Header Row -->
                      <tr
                        class="bg-slate-100/75 border-y border-slate-200 cursor-pointer hover:bg-slate-200/60 transition select-none"
                        @click="toggleFeatureCategory(category.key)"
                      >
                        <td colspan="5" class="py-3 px-6 font-extrabold text-slate-900 text-xs">
                          <div class="flex items-center justify-between">
                            <div class="flex items-center gap-2">
                              <span class="text-slate-400 text-[10px]">
                                {{ expandedPricingCategories[category.key] ? '▼' : '►' }}
                              </span>
                              <span>{{ category.title }}</span>
                            </div>
                            <span class="text-[11px] font-normal text-slate-500">
                              {{ category.description }}
                            </span>
                          </div>
                        </td>
                      </tr>

                      <!-- Category Features (Rendered if expanded) -->
                      <template v-if="expandedPricingCategories[category.key]">
                        <template v-for="feature in category.features" :key="feature.id">
                          <tr
                            class="border-b border-slate-100 hover:bg-slate-50/80 transition cursor-pointer"
                            @click="toggleFeatureDescription(feature.id)"
                          >
                            <td class="py-3.5 px-6">
                              <div class="font-bold text-slate-900 flex items-center gap-1.5">
                                <span>{{ feature.name }}</span>
                                <span class="text-slate-400 text-[10px]" title="Click for plain language description">ℹ️</span>
                              </div>
                              <p
                                v-if="expandedFeatureDescriptions[feature.id]"
                                class="mt-1.5 text-[11px] text-slate-500 bg-slate-50 p-2.5 rounded-lg border border-slate-100 leading-relaxed"
                              >
                                {{ feature.description }}
                              </p>
                            </td>
                            <td class="py-3.5 px-4 text-center text-slate-600 font-medium">
                              {{ feature.values[0] }}
                            </td>
                            <td class="py-3.5 px-4 text-center text-slate-600 font-medium">
                              {{ feature.values[1] }}
                            </td>
                            <td class="py-3.5 px-4 text-center font-bold text-blue-900 bg-blue-50/20">
                              {{ feature.values[2] }}
                            </td>
                            <td class="py-3.5 px-4 text-center text-slate-800 font-medium">
                              {{ feature.values[3] }}
                            </td>
                          </tr>
                        </template>
                      </template>
                    </template>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <!-- ============================================================== -->
          <!-- VIEW D: BILLING & INVOICES                                      -->
          <!-- ============================================================== -->
          <div v-if="activeView === 'billing'" class="space-y-6">
            <div>
              <h1 class="text-2xl font-extrabold text-slate-900 tracking-tight">Billing & Invoices</h1>
              <p class="text-xs text-slate-600 mt-0.5">Review outstanding statements, generate invoices for token orders, and pay instantly via M-Pesa.</p>
            </div>

            <!-- Invoices List -->
            <div class="space-y-4">
              <div v-if="!allInvoices.length" class="bg-white rounded-2xl border border-slate-200 p-8 text-center text-xs text-slate-500">
                <span class="text-3xl block mb-2">🎉</span>
                <p class="font-bold text-slate-800 text-sm">All invoices settled</p>
                <p class="mt-1">There are no outstanding balances due on your account.</p>
              </div>

              <div v-else class="space-y-3">
                <article
                  v-for="invoice in allInvoices"
                  :key="invoice.name"
                  class="bg-white rounded-2xl border border-slate-200 p-5 shadow-2xs flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4"
                >
                  <div>
                    <div class="flex items-center gap-2">
                      <span class="font-bold text-sm text-slate-900">{{ invoice.invoice_number || invoice.name }}</span>
                      <span
                        class="rounded px-2 py-0.5 text-[10px] font-bold"
                        :class="invoiceStatus(invoice).key === 'overdue' ? 'bg-rose-100 text-rose-800' : 'bg-amber-100 text-amber-800'"
                      >
                        {{ invoiceStatus(invoice).label }}
                      </span>
                    </div>
                    <p class="text-xs text-slate-500 mt-1">
                      Due: <strong>{{ invoice.due_date || 'On Receipt' }}</strong> · Issued: {{ invoice.posting_date }}
                    </p>
                  </div>

                  <div class="flex items-center gap-3 shrink-0 flex-wrap justify-end">
                    <div class="text-right">
                      <span class="text-base font-extrabold text-slate-900 block leading-tight">{{ money(invoice.amount, invoice.currency) }}</span>
                      <span class="text-[10px] text-slate-400 uppercase font-medium">Balance</span>
                    </div>
                    <button
                      type="button"
                      class="rounded-xl bg-emerald-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-emerald-700 transition inline-flex items-center gap-1.5"
                      @click="openMpesaModal(invoice)"
                    >
                      <span>📱 Pay M-Pesa (No Fee)</span>
                    </button>
                    <button
                      type="button"
                      class="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition disabled:opacity-50"
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
            <div v-if="allOrders.length" class="space-y-3 pt-6 border-t border-slate-200">
              <h2 class="text-sm font-bold uppercase tracking-wider text-slate-600">Pending Token Orders</h2>
              <div class="space-y-3">
                <article
                  v-for="order in allOrders"
                  :key="order.name"
                  class="bg-white rounded-2xl border border-slate-200 p-4 shadow-2xs flex items-center justify-between"
                >
                  <div>
                    <span class="font-bold text-xs text-slate-900">{{ packageLabel(order.crm_token_package_item, context.token_packages) }}</span>
                    <span class="text-xs text-slate-500 ml-2">For {{ facilityLabel(order.crm_token_facility_mfl, allFacilities) }} · Order #{{ order.name }}</span>
                  </div>
                  <div class="flex items-center gap-3">
                    <span class="text-xs font-bold text-slate-800">{{ money(order.grand_total, order.currency) }}</span>
                    <button
                      v-if="order.can_create_invoice"
                      type="button"
                      class="rounded-xl bg-slate-900 px-3 py-1.5 text-xs font-bold text-white hover:bg-black transition"
                      @click="createInvoice(order)"
                    >
                      Generate Invoice
                    </button>
                  </div>
                </article>
              </div>
            </div>
          </div>

          <!-- ============================================================== -->
          <!-- VIEW E: HEALTH FACILITY REGISTRY SYNC                          -->
          <!-- ============================================================== -->
          <div v-if="activeView === 'hfr_sync'" class="space-y-6 max-w-4xl">
            <div>
              <h1 class="text-2xl font-extrabold text-slate-900 tracking-tight">Health Facility Registry Sync</h1>
              <p class="text-xs text-slate-600 mt-0.5">Synchronize facility records directly with the official Digital Health Agency (DHA) Health Facility Registry.</p>
            </div>

            <!-- 1-Click Discovery by National ID on File -->
            <div class="bg-white rounded-2xl border border-slate-200 p-6 shadow-2xs space-y-4">
              <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <div>
                  <h3 class="font-bold text-sm text-slate-900 flex items-center gap-2">
                    <span>🆔</span>
                    <span>1-Click Auto-Discovery by National ID</span>
                  </h3>
                  <p class="text-xs text-slate-600 mt-1">
                    Discover all clinical branches registered under your verified National ID on file
                    <span v-if="userProfile.masked_national_id" class="font-mono font-bold text-slate-800">({{ userProfile.masked_national_id }})</span>.
                  </p>
                </div>
                <button
                  type="button"
                  class="rounded-xl bg-blue-600 px-4 py-2.5 text-xs font-bold text-white shadow-xs hover:bg-blue-700 transition shrink-0 disabled:opacity-50 inline-flex items-center gap-1.5"
                  :disabled="hfrOwnerSearchBusy"
                  @click="discoverFacilitiesByOwnerId()"
                >
                  <span>{{ hfrOwnerSearchBusy ? 'Searching Registry…' : '🔍 Discover Facilities by My ID' }}</span>
                </button>
              </div>

              <!-- Discovered Facilities List -->
              <div v-if="hfrOwnerSearchResults.length" class="mt-4 pt-4 border-t border-slate-100 space-y-2">
                <span class="text-xs font-bold uppercase text-slate-600">Discovered Facilities ({{ hfrOwnerSearchResults.length }})</span>
                <div class="space-y-2 max-h-72 overflow-y-auto">
                  <div
                    v-for="cand in hfrOwnerSearchResults"
                    :key="cand.fid || cand.mfl_code"
                    class="rounded-xl border border-slate-200 p-3.5 flex items-center justify-between gap-3 hover:bg-slate-50 transition"
                  >
                    <div>
                      <div class="flex items-center gap-2">
                        <span class="font-bold text-xs text-slate-900">{{ cand.name }}</span>
                        <span v-if="cand.already_linked" class="rounded bg-emerald-100 text-emerald-800 text-[10px] font-bold px-2 py-0.5">
                          ✓ In Portfolio
                        </span>
                      </div>
                      <span class="text-[11px] text-slate-500 block mt-0.5">
                        MFL: {{ cand.mfl_code }} · {{ cand.level }} · {{ cand.county }} {{ cand.subcounty ? `/ ${cand.subcounty}` : '' }} · {{ cand.owner_type }}
                      </span>
                    </div>

                    <button
                      v-if="!cand.already_linked"
                      type="button"
                      class="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-bold text-white hover:bg-black transition shrink-0 disabled:opacity-50"
                      :disabled="hfrLinkBusy"
                      @click="linkHfrCandidate(cand)"
                    >
                      {{ hfrLinkBusy ? 'Linking…' : '+ Add to Portfolio' }}
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <!-- Manual Search by MFL Code -->
            <div class="bg-white rounded-2xl border border-slate-200 p-6 shadow-2xs space-y-4">
              <h3 class="font-bold text-sm text-slate-900">Manual Facility Search (by MFL or Registration #)</h3>
              <p class="text-xs text-slate-600 leading-relaxed">
                If you have a clinic branch registered under a partner, trustee, or corporate registration number, search and link it directly via its 5-digit Master Facility List (MFL) code.
              </p>

              <div class="pt-2 flex items-center gap-3">
                <button
                  type="button"
                  class="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs font-bold text-slate-800 shadow-2xs hover:bg-slate-50 transition"
                  @click="openAddFacilityModal()"
                >
                  <span>+ Search by MFL Code or Registration #</span>
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
                <h1 class="text-2xl font-extrabold text-slate-900 tracking-tight">My Profile & Identification</h1>
                <p class="text-xs text-slate-600 mt-0.5">Manage your verified National ID, legal organization entity, and Health Facility Registry linkage.</p>
              </div>
              <button
                type="button"
                class="rounded-xl bg-blue-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-blue-700 transition inline-flex items-center gap-1.5 self-start sm:self-auto"
                @click="openEditProfileModal()"
              >
                <span>✏️ Edit Profile Details</span>
              </button>
            </div>

            <!-- Profile Cards Grid -->
            <div class="grid gap-6 md:grid-cols-2">
              <!-- Card 1: National Identification -->
              <div class="rounded-2xl border border-slate-200 bg-white p-6 shadow-2xs space-y-4">
                <div class="flex items-center justify-between">
                  <span class="text-xs font-bold uppercase tracking-wider text-slate-500">National Identification</span>
                  <span
                    class="rounded-full px-2.5 py-0.5 text-[10px] font-bold border"
                    :class="userProfile.national_id ? 'bg-emerald-50 text-emerald-800 border-emerald-200' : 'bg-amber-50 text-amber-800 border-amber-200'"
                  >
                    {{ userProfile.national_id ? 'Verified Key' : 'Action Required' }}
                  </span>
                </div>

                <div class="rounded-xl bg-slate-50 border border-slate-200 p-4 space-y-2">
                  <div class="text-xs text-slate-500 font-medium">Kenyan National ID Number:</div>
                  <div class="flex items-center justify-between">
                    <span class="font-mono text-xl font-extrabold tracking-wider text-slate-900">
                      {{ showUnmaskedId ? (userProfile.national_id || 'Not on file') : (userProfile.masked_national_id || 'Not on file') }}
                    </span>
                    <button
                      type="button"
                      class="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-bold text-slate-700 hover:bg-slate-100 transition inline-flex items-center gap-1"
                      @click="showUnmaskedId = !showUnmaskedId"
                      :title="showUnmaskedId ? 'Mask National ID' : 'Reveal National ID'"
                    >
                      <span>{{ showUnmaskedId ? '🔒 Mask' : '👁️ Reveal' }}</span>
                    </button>
                  </div>
                </div>

                <p class="text-xs text-slate-500 leading-relaxed">
                  Your National ID is used to securely query the Digital Health Agency (DHA) Health Facility Registry and verify ownership of your clinical branches without manual MFL entry.
                </p>

                <div class="pt-2 border-t border-slate-100 flex items-center justify-between">
                  <button
                    type="button"
                    class="text-xs font-bold text-blue-600 hover:underline"
                    @click="discoverFacilitiesByOwnerId(); activeView = 'hfr_sync'"
                  >
                    1-Click Registry Discovery →
                  </button>
                  <button
                    type="button"
                    class="text-xs font-semibold text-slate-600 hover:text-slate-900"
                    @click="openEditProfileModal()"
                  >
                    Change ID Number
                  </button>
                </div>
              </div>

              <!-- Card 2: Legal Organization & Identity -->
              <div class="rounded-2xl border border-slate-200 bg-white p-6 shadow-2xs space-y-4">
                <div class="flex items-center justify-between">
                  <span class="text-xs font-bold uppercase tracking-wider text-slate-500">Enterprise Entity</span>
                  <span class="rounded-full bg-blue-50 text-blue-800 border border-blue-200 px-2.5 py-0.5 text-[10px] font-bold">
                    Primary Account
                  </span>
                </div>

                <div class="space-y-3 text-xs">
                  <div class="rounded-xl bg-slate-50 border border-slate-100 p-3 space-y-1">
                    <span class="text-slate-500 font-medium block">Parent Legal Organization</span>
                    <strong class="font-extrabold text-sm text-slate-900 block">{{ primaryOrganizationName }}</strong>
                  </div>

                  <div class="grid grid-cols-2 gap-2 text-xs">
                    <div class="rounded-xl bg-slate-50 border border-slate-100 p-2.5">
                      <span class="text-slate-500 block text-[11px]">Primary Network</span>
                      <strong class="text-slate-800 block truncate">{{ userProfile.primary_network || 'CareVerse Partner Network' }}</strong>
                    </div>
                    <div class="rounded-xl bg-slate-50 border border-slate-100 p-2.5">
                      <span class="text-slate-500 block text-[11px]">Managed Clinics</span>
                      <strong class="text-slate-800 block">{{ allFacilities.length }} facilities</strong>
                    </div>
                  </div>

                  <div class="rounded-xl bg-slate-50 border border-slate-100 p-3 space-y-1">
                    <span class="text-slate-500 font-medium block">Signatory / User</span>
                    <strong class="text-slate-900 block">{{ userProfile.full_name || context.user }}</strong>
                    <span class="text-slate-500 font-mono text-[11px] block">{{ userProfile.email }}</span>
                    <span class="text-slate-600 font-mono text-[11px] block">Phone: {{ userProfile.mobile_no || 'Not set' }}</span>
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
              <h1 class="text-2xl font-extrabold text-slate-900 tracking-tight">Network Support & Contacts</h1>
              <p class="text-xs text-slate-600 mt-0.5">Dedicated clinical onboarding lead and emergency support channels.</p>
            </div>

            <div class="bg-white rounded-2xl border border-slate-200 p-6 shadow-2xs space-y-4">
              <div class="space-y-2.5">
                <div class="rounded-xl bg-slate-50 border border-slate-100 p-3.5 text-xs flex items-center justify-between">
                  <span class="text-slate-600 font-medium">Network Partner</span>
                  <span class="font-bold text-slate-900">{{ primaryNetworkName }}</span>
                </div>
                <div class="rounded-xl bg-slate-50 border border-slate-100 p-3.5 text-xs flex items-center justify-between">
                  <span class="text-slate-600 font-medium">Clinical Helpdesk</span>
                  <a href="mailto:support@tiberbu.health" class="font-bold text-[#bc1823] hover:underline">support@tiberbu.health</a>
                </div>
                <div class="rounded-xl bg-slate-50 border border-slate-100 p-3.5 text-xs flex items-center justify-between">
                  <span class="text-slate-600 font-medium">WhatsApp Hotline</span>
                  <span class="font-bold text-slate-900 font-mono">+254 700 000 000</span>
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>

    <!-- MODAL 1: ADD FACILITY VIA HEALTH FACILITY REGISTRY -->
    <Dialog
      v-model:open="addFacilityModalOpen"
      :title="__('Add Facility via Health Facility Registry')"
      size="3xl"
    >
      <div class="p-1 space-y-5">
        <!-- 1-Click National ID Discovery Banner if ID exists -->
        <div v-if="userProfile.masked_national_id" class="rounded-xl bg-blue-50/70 border border-blue-200 p-3.5 flex items-center justify-between gap-3">
          <div>
            <span class="font-bold text-xs text-blue-900 block">Registered Owner ID: {{ userProfile.masked_national_id }}</span>
            <span class="text-[11px] text-blue-700">Auto-discover clinic branches licensed under this National ID with 1 click.</span>
          </div>
          <button
            type="button"
            class="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-blue-700 transition shrink-0 disabled:opacity-50"
            :disabled="hfrOwnerSearchBusy"
            @click="discoverFacilitiesByOwnerId(); addFacilityModalOpen = false; activeView = 'hfr_sync'"
          >
            {{ hfrOwnerSearchBusy ? 'Searching…' : 'Discover by My ID →' }}
          </button>
        </div>

        <div>
          <label class="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
            Search Health Facility Registry by MFL Code or Registration Number
          </label>
          <div class="flex gap-2">
            <select
              v-model="hfrSearchBy"
              class="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-700 shrink-0"
            >
              <option value="mfl_code">MFL Code</option>
              <option value="registration_number">Registration #</option>
            </select>
            <input
              type="text"
              v-model="hfrSearchQuery"
              placeholder="e.g. 12094"
              class="flex-1 rounded-xl border border-slate-200 px-3.5 py-2 text-xs font-medium text-slate-900 focus:outline-none focus:border-blue-500"
              @keyup.enter="executeHfrSearch()"
            />
            <button
              type="button"
              class="rounded-xl bg-blue-600 px-4 py-2 text-xs font-bold text-white hover:bg-blue-700 disabled:opacity-50 shrink-0"
              :disabled="hfrSearchBusy"
              @click="executeHfrSearch()"
            >
              {{ hfrSearchBusy ? 'Searching…' : 'Search' }}
            </button>
          </div>
        </div>

        <!-- Search Results -->
        <div v-if="hfrSearchResults.length" class="space-y-2">
          <span class="text-xs font-bold uppercase text-slate-600">Matching Registry Records ({{ hfrSearchResults.length }})</span>
          <div class="space-y-2 max-h-60 overflow-y-auto">
            <div
              v-for="cand in hfrSearchResults"
              :key="cand.fid"
              class="rounded-xl border p-3 flex items-center justify-between gap-3 hover:bg-slate-50 transition"
              :class="hfrSelectedCandidate?.fid === cand.fid ? 'border-blue-500 bg-blue-50/30' : 'border-slate-200'"
            >
              <div>
                <span class="font-bold text-xs text-slate-900 block">{{ cand.name }}</span>
                <span class="text-[11px] text-slate-500">MFL: {{ cand.mfl_code }} · {{ cand.level || 'Clinic' }} · {{ cand.county }} · {{ cand.owner_type }}</span>
              </div>
              <button
                type="button"
                class="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-bold text-white hover:bg-black transition shrink-0 disabled:opacity-50"
                :disabled="hfrLinkBusy"
                @click="linkHfrCandidate(cand)"
              >
                {{ hfrLinkBusy ? 'Linking…' : 'Link Facility' }}
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
          <label class="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
            Target Facility
          </label>
          <select
            v-model="selectedFacilityMfl"
            class="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-xs sm:text-sm font-bold text-slate-900 shadow-2xs focus:border-blue-500"
          >
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
          <span class="text-xs font-bold uppercase text-slate-700 block">Select Package Tier</span>
          <div class="grid gap-3 sm:grid-cols-2">
            <article
              v-for="pkg in context.token_packages"
              :key="pkg.item_code"
              class="rounded-xl border p-4 cursor-pointer transition flex flex-col justify-between"
              :class="
                selectedTopUpPackageCode === pkg.item_code
                  ? 'border-2 border-blue-600 bg-blue-50/20 ring-2 ring-blue-500/10'
                  : 'border-slate-200 hover:border-slate-300 bg-white'
              "
              @click="selectedTopUpPackageCode = pkg.item_code"
            >
              <div>
                <div class="flex items-center justify-between">
                  <span class="font-bold text-sm text-slate-900">{{ pkg.display_name }}</span>
                  <span class="font-bold text-xs text-blue-700">
                    {{ Number(pkg.price_ex_vat ?? pkg.price ?? 0) === 0 ? 'Free' : money(pkg.gross_total || pkg.price, pkg.currency) }}
                  </span>
                </div>
                <div class="mt-2 text-xs font-bold text-slate-900">🪙 {{ (pkg.token_quantity || 0).toLocaleString() }} Tokens</div>
                <p class="mt-1 text-[11px] text-slate-500 leading-normal">{{ pkg.coverage_summary || pkg.description }}</p>
              </div>
              <div class="mt-3 pt-2 border-t border-slate-100 flex items-center justify-between text-[11px]">
                <span class="text-slate-400">{{ Number(pkg.gross_total) > 0 ? 'incl. 16% VAT' : 'No charge' }}</span>
                <span class="font-bold" :class="selectedTopUpPackageCode === pkg.item_code ? 'text-blue-600' : 'text-slate-400'">
                  {{ selectedTopUpPackageCode === pkg.item_code ? 'Selected ✓' : 'Select' }}
                </span>
              </div>
            </article>
          </div>
        </div>

        <div class="pt-4 border-t border-slate-100 flex items-center justify-end gap-3">
          <button type="button" class="rounded-xl border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50" @click="topUpModalOpen = false">
            Cancel
          </button>
          <button
            type="button"
            class="rounded-xl bg-[#bc1823] px-5 py-2.5 text-xs font-bold text-white shadow-xs hover:bg-[#a3141d] disabled:opacity-50"
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
        <div class="rounded-2xl bg-emerald-700 text-white p-4 shadow-sm flex items-center justify-between">
          <div class="flex items-center gap-3">
            <div class="size-10 rounded-xl bg-white text-emerald-800 flex items-center justify-center font-extrabold text-base shadow-xs">
              M
            </div>
            <div>
              <span class="font-extrabold text-sm tracking-tight block">Lipa na M-Pesa · Paybill</span>
              <span class="text-xs text-emerald-100 block">Direct Instant Settlement with Zero Transaction Processing Surcharge</span>
            </div>
          </div>
          <span class="rounded-full bg-emerald-800/80 border border-emerald-500/50 px-2.5 py-1 text-[11px] font-bold">
            Official Paybill
          </span>
        </div>

        <!-- 3 Copyable Cards Grid -->
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <!-- 1. Paybill Number -->
          <div class="rounded-xl border border-slate-200 bg-slate-50/80 p-3 flex flex-col justify-between">
            <span class="text-[11px] font-bold uppercase tracking-wider text-slate-500 block">Business No</span>
            <div class="mt-1">
              <span class="font-mono text-lg font-extrabold text-slate-900 block leading-tight">{{ paybillInfo.business_number }}</span>
              <span class="text-[10px] text-slate-500 block truncate">{{ paybillInfo.business_name }}</span>
            </div>
            <button
              type="button"
              class="mt-2.5 w-full rounded-lg border border-slate-200 bg-white py-1 px-2 text-xs font-bold text-slate-700 hover:bg-slate-100 transition inline-flex items-center justify-center gap-1"
              @click="copyText(paybillInfo.business_number, 'paybill_biz')"
            >
              <span>{{ copiedKey === 'paybill_biz' ? '✓ Copied' : '📋 Copy' }}</span>
            </button>
          </div>

          <!-- 2. Account Number -->
          <div class="rounded-xl border border-slate-200 bg-slate-50/80 p-3 flex flex-col justify-between">
            <span class="text-[11px] font-bold uppercase tracking-wider text-slate-500 block">Account No</span>
            <div class="mt-1">
              <span class="font-mono text-sm font-extrabold text-slate-900 block truncate leading-tight">{{ mpesaInvoice?.name }}</span>
              <span class="text-[10px] text-slate-500 block">Invoice Reference</span>
            </div>
            <button
              type="button"
              class="mt-2.5 w-full rounded-lg border border-slate-200 bg-white py-1 px-2 text-xs font-bold text-slate-700 hover:bg-slate-100 transition inline-flex items-center justify-center gap-1"
              @click="copyText(mpesaInvoice?.name, 'paybill_acc')"
            >
              <span>{{ copiedKey === 'paybill_acc' ? '✓ Copied' : '📋 Copy' }}</span>
            </button>
          </div>

          <!-- 3. Exact Amount -->
          <div class="rounded-xl border border-slate-200 bg-slate-50/80 p-3 flex flex-col justify-between">
            <span class="text-[11px] font-bold uppercase tracking-wider text-slate-500 block">Amount Due</span>
            <div class="mt-1">
              <span class="font-mono text-lg font-extrabold text-emerald-700 block leading-tight">{{ money(mpesaInvoice?.amount || mpesaInvoice?.outstanding_amount, mpesaInvoice?.currency) }}</span>
              <span class="text-[10px] text-slate-500 block">KES Net Total</span>
            </div>
            <button
              type="button"
              class="mt-2.5 w-full rounded-lg border border-slate-200 bg-white py-1 px-2 text-xs font-bold text-slate-700 hover:bg-slate-100 transition inline-flex items-center justify-center gap-1"
              @click="copyText(Math.round(mpesaInvoice?.amount || mpesaInvoice?.outstanding_amount || 0), 'paybill_amt')"
            >
              <span>{{ copiedKey === 'paybill_amt' ? '✓ Copied' : '📋 Copy' }}</span>
            </button>
          </div>
        </div>

        <!-- Step-by-step instructions -->
        <div class="rounded-xl bg-slate-50 border border-slate-100 p-4 space-y-1.5 text-xs text-slate-600">
          <strong class="text-slate-900 font-bold block mb-1">How to pay on your phone:</strong>
          <p>1. Open SIM Toolkit or M-Pesa App &gt; <strong>Lipa na M-Pesa</strong> &gt; <strong>Paybill</strong></p>
          <p>2. Enter Business Number <strong>{{ paybillInfo.business_number }}</strong> ({{ paybillInfo.business_name }})</p>
          <p>3. Enter Account Number <strong>{{ mpesaInvoice?.name }}</strong></p>
          <p>4. Enter Amount <strong>{{ money(mpesaInvoice?.amount || mpesaInvoice?.outstanding_amount, mpesaInvoice?.currency) }}</strong></p>
          <p>5. Enter your M-Pesa PIN and confirm payment</p>
        </div>

        <!-- M-Pesa Transaction Input Form -->
        <div class="space-y-3 pt-2 border-t border-slate-100">
          <label class="block text-xs font-bold uppercase tracking-wider text-slate-800">
            Submit M-Pesa Confirmation Code (from SMS)
          </label>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <input
                type="text"
                v-model="mpesaCodeInput"
                placeholder="e.g. SB65A1TU7X"
                maxlength="15"
                class="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-xs font-mono font-extrabold uppercase tracking-wider text-slate-900 focus:outline-none focus:border-emerald-600 focus:ring-2 focus:ring-emerald-500/10 placeholder:text-slate-400 placeholder:normal-case placeholder:font-sans"
              />
              <span class="text-[10px] text-slate-400 mt-1 block">10-character code from Safaricom SMS</span>
            </div>
            <div>
              <input
                type="tel"
                v-model="mpesaPhoneInput"
                placeholder="M-Pesa Phone (e.g. 0712 345 678)"
                class="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-xs font-medium text-slate-900 focus:outline-none focus:border-emerald-600 focus:ring-2 focus:ring-emerald-500/10"
              />
              <span class="text-[10px] text-slate-400 mt-1 block">Phone used for the M-Pesa transaction</span>
            </div>
          </div>
        </div>

        <!-- Actions -->
        <div class="pt-4 border-t border-slate-100 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <button
            type="button"
            class="text-xs font-semibold text-slate-600 hover:text-blue-600 underline text-left"
            @click="payInvoice(mpesaInvoice); mpesaModalOpen = false"
          >
            Or checkout using Credit/Debit Card via Paystack →
          </button>
          <div class="flex items-center gap-2 justify-end">
            <button
              type="button"
              class="rounded-xl border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50"
              @click="mpesaModalOpen = false"
            >
              Cancel
            </button>
            <button
              type="button"
              class="rounded-xl bg-emerald-600 px-5 py-2.5 text-xs font-bold text-white shadow-xs hover:bg-emerald-700 disabled:opacity-50 transition"
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
          <label class="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
            Full Name
          </label>
          <input
            type="text"
            v-model="profileForm.full_name"
            placeholder="e.g. Salim Mwaura"
            class="w-full rounded-xl border border-slate-200 px-3.5 py-2 text-xs font-medium text-slate-900 focus:outline-none focus:border-blue-500"
          />
        </div>

        <div>
          <label class="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
            Kenyan National ID Number
          </label>
          <input
            type="text"
            v-model="profileForm.national_id"
            placeholder="6 to 10 digit National ID"
            maxlength="10"
            class="w-full rounded-xl border border-slate-200 px-3.5 py-2 text-xs font-mono font-bold text-slate-900 focus:outline-none focus:border-blue-500"
          />
          <p class="text-[11px] text-slate-500 mt-1">
            Used to securely query and auto-discover facilities licensed under your ownership in the official Health Facility Registry.
          </p>
        </div>

        <div>
          <label class="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
            Mobile Number
          </label>
          <input
            type="tel"
            v-model="profileForm.mobile_no"
            placeholder="e.g. 0712345678"
            class="w-full rounded-xl border border-slate-200 px-3.5 py-2 text-xs font-medium text-slate-900 focus:outline-none focus:border-blue-500"
          />
        </div>

        <div class="pt-4 border-t border-slate-100 flex items-center justify-end gap-3">
          <button
            type="button"
            class="rounded-xl border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50"
            @click="profileModalOpen = false"
          >
            Cancel
          </button>
          <button
            type="button"
            class="rounded-xl bg-blue-600 px-5 py-2.5 text-xs font-bold text-white shadow-xs hover:bg-blue-700 disabled:opacity-50 transition"
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
