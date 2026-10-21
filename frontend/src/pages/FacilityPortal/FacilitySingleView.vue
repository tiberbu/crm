<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import CxIcon from './components/CxIcon.vue'

const props = defineProps({
  facility: { type: Object, required: true },
  invoices: { type: Array, default: () => [] },
  orders: { type: Array, default: () => [] },
  payments: { type: Array, default: () => [] },
  tokenPackages: { type: Array, default: () => [] },
  defaultCurrency: { type: String, default: 'KES' },
  loadProvisioningStatus: { type: Function, required: true },
})
const emit = defineEmits(['back', 'open-top-up', 'open-support', 'pay'])
const provisioning = ref(null)
const provisioningBusy = ref(true)
const provisioningError = ref('')
let statusRequestSequence = 0

const submissionErrorMessage = computed(() => {
  return provisioning.value?.submission?.state === 'error'
    ? provisioning.value.submission.message || 'The setup request could not be completed.'
    : ''
})
const submissionBlockedMessage = computed(() => {
  return provisioning.value?.submission?.state === 'blocked'
    ? provisioning.value.submission.message || 'The setup request is waiting for required facility or billing information.'
    : ''
})
const canRetryStatusCheck = computed(() => {
  const submission = provisioning.value?.submission
  if (submission?.state === 'blocked') return true
  if (submission) return submission.retryable === true
  return provisioning.value?.retryable !== false
})
const submissionCreated = computed(() => provisioning.value?.submission?.state === 'created')
const submissionAlreadyExists = computed(() => provisioning.value?.submission?.state === 'already_exists')
const submissionUnknown = computed(() => provisioning.value?.submission?.state === 'unknown')

async function loadStatus() {
  const requestSequence = ++statusRequestSequence
  const requestedMflCode = props.facility.mfl_code
  provisioningBusy.value = true
  provisioningError.value = ''
  try {
    const result = await props.loadProvisioningStatus(requestedMflCode)
    if (requestSequence === statusRequestSequence) provisioning.value = result
  } catch (error) {
    if (requestSequence === statusRequestSequence) {
      provisioning.value = null
      provisioningError.value = error?.messages?.[0] || error?.message || 'We could not refresh implementation status. Your facility and billing records are unchanged. Try again shortly.'
    }
  } finally {
    if (requestSequence === statusRequestSequence) provisioningBusy.value = false
  }
}
onMounted(loadStatus)
watch(() => props.facility.mfl_code, () => {
  provisioning.value = null
  loadStatus()
})

const statusLabel = computed(() => {
  if (provisioningBusy.value && !provisioning.value) return 'Checking status'
  if (provisioningError.value && !provisioning.value) return 'Status unavailable'
  if (submissionBlockedMessage.value) return 'Setup needs information'
  if (submissionErrorMessage.value) return 'Setup request needs attention'
  if (submissionUnknown.value) return 'Checking setup request'
  if (submissionCreated.value) return 'Draft submitted for review'
  if (submissionAlreadyExists.value) return 'Draft already exists'
  const status = String(provisioning.value?.status || '').toLowerCase()
  if (status === 'deployed') return 'Live'
  if (status === 'draft') return 'Draft ready for review'
  if (status === 'not_submitted') return 'Setup not started'
  if (status === 'not_linked') return 'HFR FID needed'
  if (status.includes('error') || provisioning.value?.has_error) return 'Needs attention'
  if (status === 'not_configured') return 'Tracking not connected'
  if (status === 'route_not_provisioned') return 'Tracking not available yet'
  if (status === 'needs_support') return 'Needs implementation support'
  if (status === 'unavailable') return 'Status unavailable'
  return provisioning.value?.status || 'Not started'
})

const statusTone = computed(() => {
  if (provisioningBusy.value && !provisioning.value) return 'border-cx-brand-soft-border bg-cx-brand-soft text-cx-brand-ink'
  if (provisioningError.value && !provisioning.value) return 'border-cx-warning-border bg-cx-warning-soft text-cx-warning-ink'
  if (submissionBlockedMessage.value) return 'border-cx-warning-border bg-cx-warning-soft text-cx-warning-ink'
  if (submissionErrorMessage.value) return 'border-cx-danger-border bg-cx-danger-soft text-cx-danger-ink'
  if (submissionUnknown.value) return 'border-cx-warning-border bg-cx-warning-soft text-cx-warning-ink'
  if (submissionCreated.value || submissionAlreadyExists.value) return 'border-cx-warning-border bg-cx-warning-soft text-cx-warning-ink'
  const status = String(provisioning.value?.status || '').toLowerCase()
  if (status === 'deployed') return 'border-cx-success-border bg-cx-success-soft text-cx-success-ink'
  if (status === 'draft' || status === 'not_submitted') return 'border-cx-warning-border bg-cx-warning-soft text-cx-warning-ink'
  if (status.includes('error') || status === 'needs_support' || provisioning.value?.has_error) return 'border-cx-danger-border bg-cx-danger-soft text-cx-danger-ink'
  return 'border-cx-border bg-cx-well text-cx-ink-2'
})

const statusGuidance = computed(() => {
  if (provisioningBusy.value && !provisioning.value) return 'Checking the setup service. If no setup exists, the service will prepare the request automatically when the facility is eligible.'
  if (provisioningError.value && !provisioning.value) return 'The latest status is not available right now. You can retry without affecting your facility or payments.'
  if (submissionBlockedMessage.value) return submissionBlockedMessage.value
  if (submissionErrorMessage.value) return submissionErrorMessage.value
  if (submissionUnknown.value) return provisioning.value.submission.message || 'The request response was unclear. We are checking whether a setup record was created before trying anything again.'
  if (submissionCreated.value) return provisioning.value.submission.message || 'A draft setup request was created. The implementation team will review it before deployment.'
  if (submissionAlreadyExists.value) return provisioning.value.submission.message || 'A setup request already exists. The implementation team will review it before deployment.'
  if (provisioning.value?.error_title) return provisioning.value.message || 'The implementation service could not return the latest status.'
  const status = String(provisioning.value?.status || '').toLowerCase()
  if (status === 'draft') return 'A setup record exists. The implementation team must review it and start deployment from the setup tool.'
  if (status === 'deployed') return 'The implementation service reports this facility as deployed.'
  if (status === 'not_submitted') return 'No setup record exists yet. The setup request will be prepared automatically once the facility has the required HFR, administrator, and billing details.'
  if (status === 'not_linked') return 'This facility has no saved HFR deployment FID. Add or refresh the facility from the Health Facility Registry, then check again.'
  if (status.includes('error') || provisioning.value?.has_error) return 'The implementation team needs to review the latest deployment attempt.'
  return provisioning.value?.message || (provisioningBusy.value ? 'Checking the implementation service…' : 'Implementation status has not been checked.')
})

const progressValue = computed(() => {
  if (provisioning.value?.progress == null || provisioning.value?.progress === '') return null
  const value = Number(provisioning.value?.progress)
  return Number.isFinite(value) ? Math.min(100, Math.max(0, Math.round(value))) : null
})

const statusSource = computed(() => provisioning.value?.source === 'external_setup' ? 'Setup service' : provisioning.value?.source === 'hie_gateway' ? 'HIE gateway' : 'Status source pending')
const setupUnavailable = computed(() => provisioning.value?.status === 'unavailable' || Boolean(provisioningError.value) || Boolean(submissionErrorMessage.value) || submissionUnknown.value)
const setupConnectionReached = computed(() => Boolean(provisioning.value?.connection_reached))
const setupAlertMessage = computed(() => submissionErrorMessage.value || (submissionUnknown.value ? provisioning.value?.submission?.message : '') || provisioning.value?.message || provisioningError.value)
const goLiveReady = computed(() => String(provisioning.value?.status || '').toLowerCase() === 'deployed')
const configuredPackage = computed(() => props.tokenPackages.find((pkg) => pkg.item_code === props.facility.token_package_item_code) || null)
const selectedPackageTokens = computed(() => Number(props.facility.token_quantity || configuredPackage.value?.token_quantity || 0))
const selectedPackageCost = computed(() => Number(props.facility.package_gross_total ?? configuredPackage.value?.gross_total ?? props.facility.package_price ?? configuredPackage.value?.price ?? 0))
const hasConfiguredPackage = computed(() => Boolean(props.facility.token_package || configuredPackage.value || selectedPackageTokens.value > 0))
const facilityOutstandingInvoice = computed(() => props.invoices.find((invoice) => Number(invoice.amount || 0) > 0) || null)
const facilityPaymentPending = computed(() => props.invoices.some((invoice) => Number(invoice.amount || 0) > 0 && pendingPaymentForInvoice(invoice)))
const yesNo = (value) => value == null || value === '' ? '' : Number(value) ? 'Yes' : 'No'
const hfrProfileDetails = computed(() => [
  { label: 'MFL Code', value: props.facility.mfl_code },
  { label: 'Registration number', value: props.facility.registration_number },
  { label: 'Facility type', value: props.facility.facility_type },
  { label: 'Category', value: props.facility.facility_category },
  { label: 'Owner', value: props.facility.facility_owner },
  { label: 'Owner type', value: props.facility.facility_owner_type },
  { label: 'Regulatory body', value: props.facility.regulatory_body },
  { label: 'Board registration', value: props.facility.board_registration_number },
  { label: 'KRA PIN', value: props.facility.kra_pin },
  { label: 'Operational status', value: props.facility.operational_status },
  { label: 'County', value: props.facility.hfr_county || props.facility.county },
  { label: 'Sub-county', value: props.facility.hfr_sub_county },
  { label: 'Constituency', value: props.facility.hfr_constituency },
  { label: 'Ward', value: props.facility.hfr_ward },
  { label: 'Coordinates', value: props.facility.latitude != null && props.facility.longitude != null ? `${props.facility.latitude}, ${props.facility.longitude}` : '' },
  { label: 'License number', value: props.facility.license_number },
  { label: 'License type', value: props.facility.license_type },
  { label: 'License expiry', value: props.facility.license_expiry },
  { label: 'Facility standing', value: props.facility.facility_standing },
  { label: 'Number of beds', value: props.facility.number_of_beds },
  { label: 'Number of cots', value: props.facility.number_of_cots },
  { label: 'Open whole day', value: yesNo(props.facility.open_whole_day) },
  { label: 'Open weekends', value: yesNo(props.facility.open_weekends) },
  { label: 'Open public holidays', value: yesNo(props.facility.open_public_holidays) },
  { label: 'Open late night', value: yesNo(props.facility.open_late_night) },
  { label: 'Last HFR sync', value: props.facility.hfr_last_synced },
])

const freePackages = computed(() => props.tokenPackages.filter((pkg) => {
  const amount = Number(pkg.price_ex_vat ?? pkg.price ?? pkg.gross_total)
  return Number.isFinite(amount) && amount <= 0
}))
const paidPackages = computed(() => props.tokenPackages.filter((pkg) => {
  const amount = Number(pkg.price_ex_vat ?? pkg.price ?? pkg.gross_total)
  return Number.isFinite(amount) && amount > 0
}))

function money(amount, currency) {
  return new Intl.NumberFormat('en-KE', { style: 'currency', currency: currency || props.defaultCurrency, maximumFractionDigits: 0 }).format(amount || 0)
}

function invoiceStatus(invoice) {
  return invoice.status || 'Outstanding'
}

function pendingPaymentForInvoice(invoice) {
  return props.payments.find((payment) => {
    if (payment.status !== 'Pending Verification') return false
    const invoiceNames = payment.invoice_names?.length
      ? payment.invoice_names
      : payment.invoice
        ? [payment.invoice]
        : []
    return invoiceNames.some((name) => String(name) === String(invoice.name))
  }) || null
}

function reviewInvoice() {
  document.getElementById('facility-invoices')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}
</script>

<template>
  <section class="mx-auto w-full max-w-6xl space-y-6 pb-8">
    <div class="flex flex-wrap items-center justify-between gap-4">
      <div>
        <button type="button" class="mb-3 inline-flex items-center gap-2 text-xs font-semibold text-cx-brand hover:underline" @click="emit('back')">
          <CxIcon name="chevron-left" class="size-4" /> Back to facilities
        </button>
        <p class="text-[11px] font-semibold uppercase tracking-[0.12em] text-cx-ink-3">Facility portfolio</p>
        <h1 class="mt-1 text-3xl font-bold tracking-tight text-cx-ink">{{ facility.facility_name }}</h1>
        <p class="mt-1 text-sm text-cx-ink-3">{{ facility.keph_level }} <span v-if="facility.county">· {{ facility.county }}</span></p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <button type="button" class="inline-flex items-center gap-2 rounded-cx-sm border border-cx-border bg-cx-surface px-3 py-2.5 text-xs font-semibold text-cx-ink-2 shadow-sm transition hover:bg-cx-well" @click="emit('open-support', facility)">
          <CxIcon name="chat" class="size-4" /> Network support
        </button>
        <button type="button" class="rounded-cx-sm bg-cx-brand px-4 py-2.5 text-xs font-semibold text-cx-contrast shadow-cx hover:bg-cx-brand-strong" @click="emit('open-top-up', facility, 'paid')">
          Top up tokens
        </button>
      </div>
    </div>

    <section class="overflow-hidden rounded-cx border border-cx-border bg-cx-surface shadow-cx">
      <div class="border-b border-cx-border-soft bg-gradient-to-br from-cx-surface via-cx-surface to-cx-well/70 p-5 sm:p-7">
        <div class="flex flex-wrap items-start justify-between gap-5">
          <div class="max-w-3xl">
            <p class="text-[11px] font-semibold uppercase tracking-[0.12em] text-cx-ink-3">Implementation</p>
            <div class="mt-2 flex flex-wrap items-center gap-3">
              <h2 class="text-2xl font-bold tracking-tight text-cx-ink">HMIS implementation</h2>
              <span class="inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold" :class="statusTone">{{ statusLabel }}</span>
            </div>
            <p class="mt-2 max-w-2xl text-sm leading-relaxed text-cx-ink-2">{{ statusGuidance }}</p>
          </div>
          <button type="button" class="rounded-cx-sm border border-cx-border bg-cx-surface px-3 py-2 text-xs font-semibold text-cx-ink-2 shadow-sm hover:bg-cx-well disabled:opacity-50" :disabled="provisioningBusy" @click="loadStatus">
            {{ provisioningBusy ? 'Checking…' : 'Check status' }}
          </button>
        </div>
        <div v-if="provisioningBusy && !provisioning" class="cx-glass-panel mt-5 flex max-w-3xl items-center gap-4 rounded-cx-sm border border-cx-brand-soft-border bg-cx-brand-soft/60 p-4" aria-live="polite" aria-busy="true">
          <span class="size-5 shrink-0 animate-spin rounded-full border-2 border-cx-brand/25 border-t-cx-brand" />
          <div class="min-w-0 flex-1 space-y-2">
            <p class="text-xs font-semibold text-cx-brand-ink">Checking status and preparing setup if needed</p>
            <div class="h-2 w-3/4 animate-pulse rounded-full bg-cx-brand/15" />
            <p class="text-[11px] text-cx-ink-3">This can take a few seconds. You can continue reviewing facility details.</p>
          </div>
        </div>
        <div v-else-if="setupUnavailable" class="cx-glass-panel mt-5 flex max-w-3xl items-start gap-3 rounded-cx-sm border border-cx-warning-border bg-cx-warning-soft/70 p-4" role="alert">
          <span class="grid size-9 shrink-0 place-items-center rounded-full bg-cx-surface/80 text-cx-warning-ink"><CxIcon name="alert" class="size-4" /></span>
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <p class="text-xs font-bold text-cx-ink">{{ provisioning?.error_title || 'Status could not be refreshed' }}</p>
              <span v-if="setupConnectionReached" class="rounded-full border border-cx-success-border bg-cx-success-soft px-2 py-0.5 text-[10px] font-semibold text-cx-success-ink">Service reached</span>
            </div>
            <p class="mt-1 text-xs leading-relaxed text-cx-ink-2">{{ setupAlertMessage }}</p>
            <p v-if="provisioning?.error_code === 'method_not_published'" class="mt-2 text-[11px] leading-relaxed text-cx-ink-3">Your portal reached the deployment service, but its status method is not published for portal access yet. Token selection and billing information below remain available.</p>
            <p v-if="submissionUnknown" class="mt-2 text-[11px] leading-relaxed text-cx-ink-3">The next check will look for an existing setup before any further submission is considered.</p>
          </div>
          <button v-if="canRetryStatusCheck" type="button" class="shrink-0 rounded-cx-sm border border-cx-border bg-cx-surface px-3 py-2 text-[11px] font-semibold text-cx-ink-2 shadow-sm hover:bg-cx-well" :disabled="provisioningBusy" @click="loadStatus">Retry check</button>
        </div>
        <div v-else-if="submissionBlockedMessage" class="cx-glass-panel mt-5 flex max-w-3xl items-start gap-3 rounded-cx-sm border border-cx-warning-border bg-cx-warning-soft/70 p-4" role="status">
          <span class="grid size-9 shrink-0 place-items-center rounded-full bg-cx-surface/80 text-cx-warning-ink"><CxIcon name="alert" class="size-4" /></span>
          <div class="min-w-0 flex-1">
            <p class="text-xs font-bold text-cx-ink">Setup request not sent</p>
            <p class="mt-1 text-xs leading-relaxed text-cx-ink-2">{{ submissionBlockedMessage }}</p>
            <p class="mt-2 text-[11px] leading-relaxed text-cx-ink-3">Update the missing facility or billing information, then check again. This check did not create a setup draft.</p>
          </div>
          <button type="button" class="shrink-0 rounded-cx-sm border border-cx-border bg-cx-surface px-3 py-2 text-[11px] font-semibold text-cx-ink-2 shadow-sm hover:bg-cx-well" :disabled="provisioningBusy" @click="loadStatus">{{ provisioningBusy ? 'Checking…' : 'Check again' }}</button>
        </div>
        <div v-if="progressValue != null" class="mt-6 max-w-3xl">
          <div class="mb-2 flex items-center justify-between text-xs"><span class="font-semibold text-cx-ink-2">Reported deployment progress</span><strong class="text-sm text-cx-ink">{{ progressValue }}%</strong></div>
          <div class="h-2.5 overflow-hidden rounded-full bg-cx-well"><div class="h-full rounded-full bg-cx-brand transition-all duration-500" :style="{ width: `${progressValue}%` }"></div></div>
        </div>
      </div>

      <div class="grid divide-y divide-cx-border-soft sm:grid-cols-3 sm:divide-x sm:divide-y-0">
        <div class="p-4 sm:px-6">
          <p class="text-[10px] font-semibold uppercase tracking-wide text-cx-ink-3">Last deployment attempt</p>
          <p class="mt-1.5 text-sm font-semibold text-cx-ink">{{ provisioning?.last_attempt || 'No attempt recorded' }}</p>
        </div>
        <div class="p-4 sm:px-6">
          <p class="text-[10px] font-semibold uppercase tracking-wide text-cx-ink-3">Status provided by</p>
          <p class="mt-1.5 text-sm font-semibold text-cx-ink">{{ statusSource }}</p>
        </div>
        <div class="p-4 sm:px-6">
          <p class="text-[10px] font-semibold uppercase tracking-wide text-cx-ink-3">HFR Facility ID (FID) for deployment lookup</p>
          <p v-if="facility.hfr_facility_id" class="mt-1.5 break-all font-mono text-sm font-semibold text-cx-ink">{{ facility.hfr_facility_id }}</p>
          <p v-else class="mt-1.5 text-xs font-semibold text-cx-warning-ink">No HFR FID is saved for this facility</p>
        </div>
      </div>

      <div class="border-t border-cx-border-soft px-4 py-5 sm:px-6">
        <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 class="text-sm font-semibold text-cx-ink">Health Facility Registry profile</h3>
            <p class="mt-1 text-xs text-cx-ink-3">Registry details saved for deployment setup and facility verification.</p>
          </div>
          <span v-if="facility.hfr_sync_status" class="rounded-full border border-cx-border bg-cx-well px-2.5 py-1 text-[10px] font-medium text-cx-ink-2">{{ facility.hfr_sync_status }}</span>
        </div>
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div v-for="detail in hfrProfileDetails" :key="detail.label" class="min-w-0 rounded-cx-sm border border-cx-border-soft bg-cx-well/50 px-3 py-2.5">
            <p class="text-[10px] font-semibold uppercase tracking-wide text-cx-ink-3">{{ detail.label }}</p>
            <p class="mt-1 break-words text-xs font-medium text-cx-ink-2">{{ detail.value || 'Not recorded' }}</p>
          </div>
        </div>
        <p v-if="facility.hfr_sync_status !== 'HFR Verified'" class="mt-3 text-[11px] leading-relaxed text-cx-warning-ink">This registry profile has not been verified from HFR. Refresh or relink it from the Health Facility Registry to load current facility details.</p>
        <p v-if="!facility.hfr_facility_id" class="mt-3 text-[11px] leading-relaxed text-cx-warning-ink">Deployment lookup requires the HFR FID. Refresh or relink this facility from the Health Facility Registry before submitting setup.</p>
      </div>

      <div class="border-t border-cx-border-soft px-4 py-4 sm:px-6">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 class="text-sm font-semibold text-cx-ink">Provisioned HMIS details</h3>
            <p class="mt-1 max-w-2xl text-xs leading-relaxed text-cx-ink-3">The published status API does not include service-unit configuration or a live site health check. These details will appear when the setup service exposes them.</p>
          </div>
          <span class="rounded-full border border-cx-border bg-cx-well px-2.5 py-1 text-[10px] font-medium text-cx-ink-3">Not reported by API</span>
        </div>
      </div>

      <div class="border-t border-cx-border-soft bg-cx-well/50 px-4 py-3 text-[11px] leading-relaxed text-cx-ink-3 sm:px-6">
        Facility identifiers: <span class="font-medium text-cx-ink-2">MFL {{ facility.mfl_code || '—' }}</span><span v-if="facility.registration_number"> · Registration {{ facility.registration_number }}</span><span v-if="facility.network"> · {{ facility.network }}</span>
      </div>

      <section v-if="!goLiveReady" class="border-t border-cx-border-soft bg-gradient-to-r from-cx-brand-soft/50 via-cx-surface to-cx-surface px-4 py-5 sm:px-6">
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div class="max-w-2xl">
            <div class="flex flex-wrap items-center gap-2">
              <h3 class="text-sm font-bold text-cx-ink">Go-live token allocation</h3>
              <span class="rounded-full border border-cx-warning-border bg-cx-warning-soft px-2.5 py-1 text-[10px] font-semibold text-cx-warning-ink">Required before setup</span>
            </div>
            <p class="mt-1 text-xs leading-relaxed text-cx-ink-2">The setup service requires a token quantity when a go-live setup request is created. Choose a free package or order paid tokens; after paying an invoice, wait for payment verification before setup proceeds.</p>
          </div>
          <div v-if="hasConfiguredPackage" class="rounded-cx-sm border border-cx-border bg-cx-surface/80 px-3 py-2 text-right shadow-sm">
            <p class="text-[10px] font-semibold uppercase tracking-wide text-cx-ink-3">Selected package</p>
            <p class="mt-1 text-xs font-bold text-cx-ink">{{ configuredPackage?.display_name || facility.token_package || 'Token package' }}</p>
            <p class="mt-0.5 text-[11px] text-cx-ink-2">{{ selectedPackageTokens.toLocaleString() }} tokens · {{ selectedPackageCost > 0 ? money(selectedPackageCost, facility.package_currency) : 'Free' }}</p>
          </div>
        </div>

        <div v-if="hasConfiguredPackage" class="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-cx-sm border border-cx-border-soft bg-cx-surface/80 p-3">
          <div class="flex items-start gap-2.5">
            <span class="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-cx-success-soft text-cx-success-ink"><CxIcon name="check" class="size-4" /></span>
            <div>
              <p class="text-xs font-semibold text-cx-ink">Package selection is on file</p>
              <p class="mt-0.5 text-[11px] leading-relaxed text-cx-ink-3">This is the package quantity on file, not a live remaining-token balance or confirmation that setup has received this quantity. The status API does not report token usage.</p>
              <p v-if="facilityPaymentPending" class="mt-1 text-[11px] font-semibold text-cx-warning-ink">A facility payment is awaiting verification. Wait for confirmation before paying that invoice again.</p>
              <p v-else-if="facilityOutstandingInvoice" class="mt-1 text-[11px] text-cx-ink-3">This facility has an outstanding invoice below. Review its status before ordering more tokens.</p>
            </div>
          </div>
          <button v-if="facilityOutstandingInvoice && !facilityPaymentPending" type="button" class="rounded-cx-sm border border-cx-border bg-cx-surface px-3 py-2 text-[11px] font-semibold text-cx-ink-2 hover:bg-cx-well" @click="reviewInvoice">Review invoice</button>
        </div>

        <div v-else class="mt-4 rounded-cx-sm border border-cx-warning-border bg-cx-warning-soft/50 p-3 text-xs leading-relaxed text-cx-warning-ink">
          No token package is selected for this facility yet. Choose a free allocation or select a paid package to create its order and invoice.
        </div>

        <div v-if="!hasConfiguredPackage" class="mt-4 flex flex-wrap gap-2">
          <button v-if="freePackages.length" type="button" class="rounded-cx-sm border border-cx-brand-soft-border bg-cx-brand-soft px-3.5 py-2.5 text-xs font-semibold text-cx-brand-ink transition hover:bg-cx-brand-soft/80" @click="emit('open-top-up', facility, 'free')">
            Choose free tokens
          </button>
          <button v-if="paidPackages.length" type="button" class="rounded-cx-sm bg-cx-brand px-3.5 py-2.5 text-xs font-semibold text-cx-contrast shadow-cx transition hover:bg-cx-brand-strong" @click="emit('open-top-up', facility, 'paid')">
            Choose paid tokens
          </button>
          <button v-if="!freePackages.length && !paidPackages.length" type="button" class="rounded-cx-sm border border-cx-border bg-cx-surface px-3.5 py-2.5 text-xs font-semibold text-cx-ink-2" @click="emit('open-support', facility)">
            Ask Network Support
          </button>
        </div>
        <div v-else-if="paidPackages.length" class="mt-4 flex flex-wrap items-center justify-between gap-3">
          <p class="text-[11px] leading-relaxed text-cx-ink-3">The portal can create token orders and show their invoices. The go-live setup request itself is reviewed by the implementation team.</p>
          <button type="button" class="rounded-cx-sm border border-cx-border bg-cx-surface px-3 py-2 text-[11px] font-semibold text-cx-ink-2 hover:bg-cx-well" @click="emit('open-top-up', facility, 'paid')">Buy more tokens</button>
        </div>
      </section>

      <div class="flex flex-wrap items-center justify-between gap-3 border-t border-cx-border-soft bg-cx-well/40 px-4 py-3 sm:px-6">
        <p class="text-[11px] text-cx-ink-3">Need help with go-live or token allocation?</p>
        <button type="button" class="inline-flex items-center gap-1.5 text-xs font-semibold text-cx-brand hover:underline" @click="emit('open-support', facility)">
          Contact Network Support <CxIcon name="chevron-right" class="size-3.5" />
        </button>
      </div>
    </section>

    <div class="grid gap-5 xl:grid-cols-2">
      <section id="facility-invoices" class="rounded-cx border border-cx-border bg-cx-surface p-5 shadow-cx">
        <div class="mb-4 flex items-center justify-between"><h2 class="text-base font-bold text-cx-ink">Invoices</h2><span class="rounded-full bg-cx-well px-2.5 py-1 text-[11px] font-semibold text-cx-ink-2">{{ invoices.length }}</span></div>
        <div v-if="!invoices.length" class="rounded-cx-sm bg-cx-well p-4 text-xs text-cx-ink-3">No outstanding invoices are linked to this facility.</div>
        <div v-else class="divide-y divide-cx-border-soft">
          <div v-for="invoice in invoices" :key="invoice.name" class="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0">
            <div>
              <p class="text-xs font-semibold text-cx-ink">{{ invoice.invoice_number || invoice.name }}</p>
              <p class="mt-1 text-[11px] text-cx-ink-3">Due {{ invoice.due_date || 'on receipt' }} · {{ pendingPaymentForInvoice(invoice) ? 'Payment verification pending' : invoiceStatus(invoice) }}</p>
              <p v-if="pendingPaymentForInvoice(invoice)" class="mt-1 text-[11px] font-semibold text-cx-warning-ink">
                M-Pesa report {{ pendingPaymentForInvoice(invoice).reference_no || pendingPaymentForInvoice(invoice).name }} is awaiting verification. Please wait before paying again.
              </p>
            </div>
            <div class="flex items-center gap-3">
              <strong class="text-sm text-cx-ink">{{ money(invoice.amount, invoice.currency) }}</strong>
              <button v-if="Number(invoice.amount) > 0 && !pendingPaymentForInvoice(invoice)" type="button" class="rounded-cx-sm bg-cx-success px-3 py-1.5 text-[11px] font-semibold text-cx-contrast" @click="emit('pay', invoice)">Choose payment</button>
              <span v-else-if="pendingPaymentForInvoice(invoice)" class="text-[11px] font-semibold text-cx-warning-ink">Verification pending</span>
            </div>
          </div>
        </div>
      </section>
      <section class="rounded-cx border border-cx-border bg-cx-surface p-5 shadow-cx">
        <div class="mb-4 flex items-center justify-between"><h2 class="text-base font-bold text-cx-ink">Payment history</h2><span class="rounded-full bg-cx-well px-2.5 py-1 text-[11px] font-semibold text-cx-ink-2">{{ payments.length }}</span></div>
        <div v-if="!payments.length" class="rounded-cx-sm bg-cx-well p-4 text-xs text-cx-ink-3">No payments have been matched to this facility’s invoices.</div>
        <div v-else class="divide-y divide-cx-border-soft">
          <div v-for="payment in payments" :key="`${payment.name}-${payment.invoice || ''}`" class="flex items-center justify-between gap-3 py-3 first:pt-0">
            <div>
              <p class="text-xs font-semibold text-cx-ink">{{ payment.mode_of_payment }} · {{ payment.reference_no || payment.name }}</p>
              <p class="mt-1 text-[11px] text-cx-ink-3">{{ payment.posting_date }}<span v-if="payment.invoice"> · Invoice {{ payment.invoice }}</span></p>
              <span class="mt-1 inline-flex rounded-full border px-2 py-0.5 text-[10px] font-semibold" :class="payment.status === 'Pending Verification' ? 'border-cx-warning-border bg-cx-warning-soft text-cx-warning-ink' : 'border-cx-success-border bg-cx-success-soft text-cx-success-ink'">{{ payment.status || 'Recorded' }}</span>
            </div>
            <strong class="shrink-0 text-sm text-cx-ink">{{ money(payment.amount) }}</strong>
          </div>
        </div>
      </section>
      <section class="rounded-cx border border-cx-border bg-cx-surface p-5 shadow-cx xl:col-span-2">
        <div class="mb-4 flex items-center justify-between"><h2 class="text-base font-bold text-cx-ink">Token orders</h2><span class="rounded-full bg-cx-well px-2.5 py-1 text-[11px] font-semibold text-cx-ink-2">{{ orders.length }}</span></div>
        <div v-if="!orders.length" class="rounded-cx-sm bg-cx-well p-4 text-xs text-cx-ink-3">No open orders are linked to this facility.</div>
        <div v-else class="grid gap-3 sm:grid-cols-2">
          <article v-for="order in orders" :key="order.name" class="rounded-cx-sm border border-cx-border-soft p-3"><p class="text-xs font-semibold text-cx-ink">{{ order.name }}</p><p class="mt-1 text-[11px] text-cx-ink-3">{{ order.transaction_date }} · {{ order.status }}</p><p class="mt-2 text-sm font-bold text-cx-ink">{{ money(order.grand_total, order.currency) }}</p></article>
        </div>
      </section>
    </div>
  </section>
</template>

