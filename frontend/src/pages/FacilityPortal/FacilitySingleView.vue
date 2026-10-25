<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import CxIcon from './components/CxIcon.vue'

const props = defineProps({
  facility: { type: Object, required: true },
  invoices: { type: Array, default: () => [] },
  orders: { type: Array, default: () => [] },
  payments: { type: Array, default: () => [] },
  tokenPackages: { type: Array, default: () => [] },
  defaultCurrency: { type: String, default: 'KES' },
  ensureProvisioningDraft: { type: Function, required: true },
  // Read-only refresh used while setup is in progress; never creates a draft.
  getProvisioningStatus: { type: Function, default: null },
})
const emit = defineEmits(['back', 'open-top-up', 'open-support', 'pay'])
const provisioning = ref(null)
const provisioningBusy = ref(true)
const provisioningError = ref('')
const errorDetailsOpen = ref(false)
const siteLinkCopied = ref(false)
let statusRequestSequence = 0
let pollTimer = null
// Deployment happens on a separate site and takes tens of minutes; a 5-minute
// read-only check is enough to notice when the site has been provisioned.
const POLL_INTERVAL_MS = 5 * 60 * 1000
// Phases whose setup journey the backend normalizes for display. Identity and
// connection problems keep their own FID-specific guidance below.
const JOURNEY_LABELS = {
  preparing: 'Preparing setup',
  queued: 'Request received',
  deploying: 'Deploying',
  configuring: 'Configuring',
  live: 'Live',
  blocked: 'Setup needs information',
  needs_attention: 'Needs attention',
}
const journey = computed(() => {
  const value = provisioning.value?.journey
  return value && JOURNEY_LABELS[value.phase] ? value : null
})
const journeySteps = computed(() => journey.value?.steps || [])
const liveSite = computed(() => journey.value?.phase === 'live' ? journey.value.site : null)
const pollingActive = computed(() => Boolean(journey.value?.poll && props.getProvisioningStatus))
const checkedAt = computed(() => {
  const value = journey.value?.checked_at
  const parsed = value ? new Date(value) : null
  return parsed && !Number.isNaN(parsed.getTime())
    ? parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : ''
})

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
// Older portal records may still serialize the HFR deployment identifier as
// `facility_fid` or `fid`. Never treat an MFL code or generic HIE ID as a FID.
const deploymentFid = computed(() => {
  const candidates = [props.facility.hfr_facility_id, props.facility.facility_fid, props.facility.fid, provisioning.value?.fid]
  return candidates.map((value) => String(value || '').trim()).find(Boolean) || ''
})
const submissionCreated = computed(() => provisioning.value?.submission?.state === 'created')
const submissionAlreadyExists = computed(() => provisioning.value?.submission?.state === 'already_exists')
const submissionUnknown = computed(() => provisioning.value?.submission?.state === 'unknown')

function stopPolling() {
  if (pollTimer) clearTimeout(pollTimer)
  pollTimer = null
}

function schedulePoll() {
  stopPolling()
  if (!pollingActive.value) return
  pollTimer = setTimeout(pollStatus, POLL_INTERVAL_MS)
}

// Silent refresh: keeps the last good state on failure and never flips the view
// into its loading state, so the stepper does not flash every 30 seconds.
async function pollStatus() {
  const requestSequence = statusRequestSequence
  const requestedMflCode = props.facility.mfl_code
  if (document.hidden) return schedulePoll()
  try {
    const result = await props.getProvisioningStatus(requestedMflCode)
    if (requestSequence === statusRequestSequence && result && typeof result === 'object' && result.status) {
      provisioning.value = result
    }
  } catch {
    // The next tick or a manual check retries.
  } finally {
    if (requestSequence === statusRequestSequence) schedulePoll()
  }
}

async function copySiteLink() {
  try {
    await navigator.clipboard.writeText(liveSite.value?.url || '')
    siteLinkCopied.value = true
    setTimeout(() => { siteLinkCopied.value = false }, 2000)
  } catch {
    siteLinkCopied.value = false
  }
}

async function loadStatus() {
  stopPolling()
  const requestSequence = ++statusRequestSequence
  const requestedMflCode = props.facility.mfl_code
  provisioningBusy.value = true
  provisioningError.value = ''
  try {
    const result = await props.ensureProvisioningDraft(requestedMflCode)
    if (requestSequence === statusRequestSequence) provisioning.value = result
  } catch (error) {
    if (requestSequence === statusRequestSequence) {
      provisioning.value = null
      provisioningError.value = error?.messages?.[0] || error?.message || 'We could not refresh implementation status. Your facility and billing records are unchanged. Try again shortly.'
    }
  } finally {
    if (requestSequence === statusRequestSequence) {
      provisioningBusy.value = false
      schedulePoll()
    }
  }
}
onMounted(loadStatus)
onUnmounted(stopPolling)
watch(() => props.facility.mfl_code, () => {
  provisioning.value = null
  loadStatus()
})

const statusLabel = computed(() => {
  if (provisioningBusy.value && !provisioning.value) return 'Checking status'
  if (provisioningError.value && !provisioning.value) return 'Status unavailable'
  if (journey.value) return journey.value.label || JOURNEY_LABELS[journey.value.phase]
  if (submissionBlockedMessage.value) return 'Setup needs information'
  if (submissionErrorMessage.value) return 'Setup request needs attention'
  if (submissionUnknown.value) return 'Checking setup request'
  if (submissionCreated.value) return 'Draft submitted for review'
  if (submissionAlreadyExists.value) return 'Draft already exists'
  const status = String(provisioning.value?.status || '').toLowerCase()
  if (status === 'deployed') return 'Live'
  if (status === 'draft') return 'Draft ready for review'
  if (status === 'not_submitted') return 'Setup not started'
  if (status === 'not_linked') return deploymentFid.value ? 'FID lookup needs attention' : 'HFR FID needed'
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
  if (journey.value) {
    const phase = journey.value.phase
    if (phase === 'live') return 'border-cx-success-border bg-cx-success-soft text-cx-success-ink'
    if (phase === 'needs_attention') return 'border-cx-danger-border bg-cx-danger-soft text-cx-danger-ink'
    if (phase === 'blocked') return 'border-cx-warning-border bg-cx-warning-soft text-cx-warning-ink'
    return 'border-cx-brand-soft-border bg-cx-brand-soft text-cx-brand-ink'
  }
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
  if (journey.value?.detail) return journey.value.detail
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
  if (status === 'not_linked') return deploymentFid.value
    ? `The portal has HFR FID ${deploymentFid.value}, but the setup service could not match it. Retry the status check; if it continues, contact network support and include this FID.`
    : 'This facility has no saved HFR deployment FID. Add or refresh the facility from the Health Facility Registry, then check again.'
  if (status.includes('error') || provisioning.value?.has_error) return 'The implementation team needs to review the latest deployment attempt.'
  return provisioning.value?.message || (provisioningBusy.value ? 'Checking the implementation service…' : 'Implementation status has not been checked.')
})

const progressValue = computed(() => {
  if (journey.value) return journey.value.progress ?? null
  if (provisioning.value?.progress == null || provisioning.value?.progress === '') return null
  const value = Number(provisioning.value?.progress)
  return Number.isFinite(value) ? Math.min(100, Math.max(0, Math.round(value))) : null
})

const statusSource = computed(() => provisioning.value?.source === 'external_setup' ? 'Setup service' : provisioning.value?.source === 'hie_gateway' ? 'HIE gateway' : 'Status source pending')
const setupUnavailable = computed(() => provisioning.value?.status === 'unavailable' || Boolean(provisioningError.value) || Boolean(submissionErrorMessage.value) || submissionUnknown.value)
const setupConnectionReached = computed(() => Boolean(provisioning.value?.connection_reached))
const setupAlertMessage = computed(() => submissionErrorMessage.value || (submissionUnknown.value ? provisioning.value?.submission?.message : '') || provisioning.value?.message || provisioningError.value)
const errorDetails = computed(() => {
  const details = provisioning.value?.submission?.error_details || provisioning.value?.error_details || provisioningError.value
  return typeof details === 'string' ? details : details ? JSON.stringify(details, null, 2) : ''
})
const errorHttpStatus = computed(() => {
  try {
    return JSON.parse(errorDetails.value)?.http_status || ''
  } catch {
    return ''
  }
})
const errorCorrelationId = computed(() => provisioning.value?.submission?.correlation_id || provisioning.value?.correlation_id || '')
const goLiveReady = computed(() => journey.value?.phase === 'live' || String(provisioning.value?.status || '').toLowerCase() === 'deployed')
const configuredPackage = computed(() => props.tokenPackages.find((pkg) => pkg.item_code === props.facility.token_package_item_code) || null)
const selectedPackageTokens = computed(() => Number(props.facility.token_quantity || configuredPackage.value?.token_quantity || 0))
const selectedPackageCost = computed(() => Number(props.facility.package_gross_total ?? configuredPackage.value?.gross_total ?? props.facility.package_price ?? configuredPackage.value?.price ?? 0))
const hasConfiguredPackage = computed(() => Boolean(props.facility.token_package || configuredPackage.value || selectedPackageTokens.value > 0))
const facilityOutstandingInvoice = computed(() => props.invoices.find((invoice) => Number(invoice.amount || 0) > 0) || null)
const facilityPaymentPending = computed(() => props.invoices.some((invoice) => Number(invoice.amount || 0) > 0 && pendingPaymentForInvoice(invoice)))
const yesNo = (value) => value == null || value === '' ? '' : Number(value) ? 'Yes' : 'No'
const hfrProfileGroups = computed(() => {
  const details = [
    {
      title: 'Registration',
      items: [
        { label: 'Registration number', value: props.facility.registration_number },
        { label: 'License number', value: props.facility.license_number },
        { label: 'License type', value: props.facility.license_type },
        { label: 'License expiry', value: props.facility.license_expiry },
        { label: 'Board registration', value: props.facility.board_registration_number },
        { label: 'Regulatory body', value: props.facility.regulatory_body },
        { label: 'KRA PIN', value: props.facility.kra_pin },
      ],
    },
    {
      title: 'Location',
      items: [
        { label: 'County', value: props.facility.hfr_county || props.facility.county },
        { label: 'Sub-county', value: props.facility.hfr_sub_county },
        { label: 'Constituency', value: props.facility.hfr_constituency },
        { label: 'Ward', value: props.facility.hfr_ward },
        { label: 'Coordinates', value: props.facility.latitude != null && props.facility.longitude != null ? `${props.facility.latitude}, ${props.facility.longitude}` : '' },
      ],
    },
    {
      title: 'Facility profile',
      items: [
        { label: 'Type', value: props.facility.facility_type },
        { label: 'Category', value: props.facility.facility_category },
        { label: 'Level', value: props.facility.keph_level || props.facility.facility_level },
        { label: 'Owner', value: props.facility.facility_owner },
        { label: 'Owner type', value: props.facility.facility_owner_type },
        { label: 'Operational status', value: props.facility.operational_status },
        { label: 'Facility standing', value: props.facility.facility_standing },
      ],
    },
    {
      title: 'Capacity & hours',
      items: [
        { label: 'Beds', value: props.facility.number_of_beds },
        { label: 'Cots', value: props.facility.number_of_cots },
        { label: 'Open all day', value: yesNo(props.facility.open_whole_day) },
        { label: 'Open weekends', value: yesNo(props.facility.open_weekends) },
        { label: 'Open holidays', value: yesNo(props.facility.open_public_holidays) },
        { label: 'Open late night', value: yesNo(props.facility.open_late_night) },
      ],
    },
  ]

  return details.map((group) => ({
    ...group,
    items: group.items.filter((item) => item.value !== null && item.value !== undefined && item.value !== ''),
  }))
})

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
            <button v-if="errorDetails" type="button" class="mt-3 text-[11px] font-semibold text-cx-brand underline-offset-2 hover:underline" @click="errorDetailsOpen = true">View deployment diagnostics</button>
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
        <section v-if="liveSite" class="mt-5 max-w-3xl overflow-hidden rounded-cx-sm border border-cx-success-border bg-cx-success-soft/40" data-testid="hmis-live-site">
          <div class="flex flex-wrap items-center justify-between gap-3 px-4 py-4 sm:px-5">
            <div class="flex min-w-0 items-center gap-3">
              <span class="grid size-10 shrink-0 place-items-center rounded-full bg-cx-surface text-cx-success-ink shadow-sm"><CxIcon name="globe" class="size-5" /></span>
              <div class="min-w-0">
                <p class="text-[10px] font-semibold uppercase tracking-[0.13em] text-cx-success-ink">Your HMIS site</p>
                <p v-if="liveSite.url" class="mt-0.5 break-all font-mono text-sm font-semibold text-cx-ink sm:text-base">{{ liveSite.url }}</p>
                <p v-else class="mt-0.5 text-xs font-medium text-cx-ink-2">The site address is in the welcome email sent to your administrator.</p>
              </div>
            </div>
            <div v-if="liveSite.url" class="flex flex-wrap items-center gap-2">
              <button type="button" class="inline-flex items-center gap-1.5 rounded-cx-sm border border-cx-border bg-cx-surface px-3 py-2 text-[11px] font-semibold text-cx-ink-2 shadow-sm hover:bg-cx-well" @click="copySiteLink">
                <CxIcon :name="siteLinkCopied ? 'check' : 'copy'" class="size-3.5" /> {{ siteLinkCopied ? 'Copied' : 'Copy link' }}
              </button>
              <a :href="liveSite.login_url || liveSite.url" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1.5 rounded-cx-sm bg-cx-success px-3.5 py-2 text-xs font-semibold text-cx-contrast shadow-cx hover:opacity-90">
                Open HMIS <CxIcon name="arrow-right" class="size-3.5" />
              </a>
            </div>
          </div>
          <div class="border-t border-cx-success-border/60 bg-cx-surface/70 px-4 py-3.5 sm:px-5">
            <p class="text-[11px] font-semibold text-cx-ink">How to sign in</p>
            <ol class="mt-2 space-y-1.5">
              <li v-for="(step, index) in liveSite.instructions" :key="index" class="flex items-start gap-2.5 text-xs leading-relaxed text-cx-ink-2">
                <span class="grid size-5 shrink-0 place-items-center rounded-full bg-cx-success-soft text-[10px] font-bold text-cx-success-ink">{{ index + 1 }}</span>
                <span class="break-words">{{ step }}</span>
              </li>
            </ol>
          </div>
        </section>
        <section v-else-if="journeySteps.length" class="mt-5 max-w-3xl rounded-cx-sm border border-cx-border-soft bg-cx-surface/80 p-4 sm:p-5" data-testid="hmis-setup-journey" aria-live="polite">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p class="text-xs font-bold text-cx-ink">{{ journey.poll ? journey.headline : 'Where setup stopped' }}</p>
              <p v-if="journey.estimate" class="mt-1 inline-flex items-center gap-1.5 text-[11px] font-medium" :class="journey.estimate.overdue ? 'text-cx-warning-ink' : 'text-cx-ink-2'" data-testid="hmis-setup-estimate">
                <CxIcon name="clock" class="size-3.5" /> {{ journey.estimate.label }}
              </p>
            </div>
            <span v-if="progressValue != null" class="text-sm font-bold text-cx-ink">{{ progressValue }}%</span>
          </div>
          <div v-if="progressValue != null" class="mt-3 h-2 overflow-hidden rounded-full bg-cx-well" role="progressbar" :aria-valuenow="progressValue" aria-valuemin="0" aria-valuemax="100" aria-label="Reported deployment progress">
            <div class="h-full rounded-full bg-cx-brand transition-all duration-500" :style="{ width: `${progressValue}%` }"></div>
          </div>
          <ol class="mt-4 grid gap-2 sm:grid-cols-4">
            <li v-for="step in journeySteps" :key="step.key" class="flex items-center gap-2 sm:flex-col sm:items-start sm:gap-1.5" :data-state="step.state">
              <span class="grid size-6 shrink-0 place-items-center rounded-full border text-[10px] font-bold"
                :class="{
                  'border-cx-success-border bg-cx-success-soft text-cx-success-ink': step.state === 'done',
                  'border-cx-brand bg-cx-brand-soft text-cx-brand-ink': step.state === 'current',
                  'border-cx-danger-border bg-cx-danger-soft text-cx-danger-ink': step.state === 'error',
                  'border-cx-border bg-cx-well text-cx-ink-3': step.state === 'upcoming',
                }">
                <CxIcon v-if="step.state === 'done'" name="check" class="size-3.5" />
                <CxIcon v-else-if="step.state === 'error'" name="alert" class="size-3.5" />
                <span v-else-if="step.state === 'current'" class="size-2 animate-pulse rounded-full bg-cx-brand" />
                <span v-else class="size-1.5 rounded-full bg-cx-ink-3/40" />
              </span>
              <span class="text-[11px] leading-snug" :class="step.state === 'upcoming' ? 'text-cx-ink-3' : 'font-semibold text-cx-ink'">{{ step.label }}</span>
            </li>
          </ol>
        </section>
        <div v-else-if="progressValue != null" class="mt-6 max-w-3xl">
          <div class="mb-2 flex items-center justify-between text-xs"><span class="font-semibold text-cx-ink-2">Reported deployment progress</span><strong class="text-sm text-cx-ink">{{ progressValue }}%</strong></div>
          <div class="h-2.5 overflow-hidden rounded-full bg-cx-well"><div class="h-full rounded-full bg-cx-brand transition-all duration-500" :style="{ width: `${progressValue}%` }"></div></div>
        </div>
      </div>

      <div class="flex flex-wrap items-center gap-x-8 gap-y-3 border-t border-cx-border-soft bg-cx-surface/45 px-5 py-3.5 text-xs sm:px-7">
        <div class="flex items-baseline gap-2">
          <span class="text-cx-ink-3">Last attempt</span>
          <span class="font-medium text-cx-ink-2">{{ provisioning?.last_attempt || 'None recorded' }}</span>
        </div>
        <div class="flex items-baseline gap-2">
          <span class="text-cx-ink-3">Status source</span>
          <span class="font-medium text-cx-ink-2">{{ statusSource }}</span>
        </div>
        <div v-if="checkedAt" class="flex items-baseline gap-2">
          <span class="text-cx-ink-3">Last checked</span>
          <span class="font-medium text-cx-ink-2">{{ checkedAt }}</span>
        </div>
        <span v-if="pollingActive" class="inline-flex items-center gap-1.5 text-[11px] font-medium text-cx-brand-ink" data-testid="hmis-auto-refresh">
          <span class="size-1.5 animate-pulse rounded-full bg-cx-brand" /> Checks again every 5 minutes
        </span>
      </div>

      <section class="cx-glass-panel mx-4 my-5 overflow-hidden rounded-cx border border-white/70 bg-cx-surface/65 shadow-cx sm:mx-6 sm:my-6 sm:backdrop-blur-xl">
        <header class="flex flex-wrap items-start justify-between gap-3 px-4 py-4 sm:px-6">
          <div>
            <p class="text-[10px] font-semibold uppercase tracking-[0.14em] text-cx-brand">Health Facility Registry</p>
            <h3 class="mt-1 text-base font-semibold tracking-tight text-cx-ink">Facility profile</h3>
          </div>
          <div class="flex items-center gap-2">
            <span v-if="facility.hfr_sync_status" class="inline-flex items-center gap-1.5 rounded-full border border-cx-border-soft bg-cx-surface/70 px-2.5 py-1 text-[10px] font-medium text-cx-ink-2">
              <span class="size-1.5 rounded-full" :class="facility.hfr_sync_status === 'HFR Verified' ? 'bg-cx-success-ink' : 'bg-cx-warning-ink'" />
              {{ facility.hfr_sync_status }}
            </span>
            <span v-if="facility.hfr_last_synced" class="text-[10px] text-cx-ink-3">Synced {{ facility.hfr_last_synced }}</span>
          </div>
        </header>

        <div class="grid gap-px border-y border-white/60 bg-cx-border-soft/70 sm:grid-cols-[minmax(0,1.4fr)_minmax(12rem,0.6fr)]">
          <div class="bg-cx-brand-soft/45 px-4 py-4 sm:px-6 sm:py-5">
            <p class="text-[10px] font-semibold uppercase tracking-[0.13em] text-cx-ink-3">Deployment Facility ID · FID</p>
            <p v-if="deploymentFid" class="mt-1.5 break-all font-mono text-xl font-semibold tracking-tight text-cx-ink sm:text-2xl">{{ deploymentFid }}</p>
            <p v-else class="mt-1.5 text-sm font-semibold text-cx-warning-ink">Not linked to an HFR FID</p>
          </div>
          <div class="bg-cx-surface/65 px-4 py-4 sm:px-6 sm:py-5">
            <p class="text-[10px] font-semibold uppercase tracking-[0.13em] text-cx-ink-3">MFL code</p>
            <p class="mt-1.5 font-mono text-lg font-semibold tracking-tight text-cx-ink">{{ facility.mfl_code || '—' }}</p>
          </div>
        </div>

        <div class="grid sm:grid-cols-2 xl:grid-cols-4">
          <section v-for="(group, index) in hfrProfileGroups" :key="group.title" class="min-w-0 px-4 py-4 sm:px-5 sm:py-5" :class="index ? 'border-t border-cx-border-soft sm:border-l xl:border-t-0' : ''">
            <h4 class="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-cx-ink-3">{{ group.title }}</h4>
            <dl v-if="group.items.length" class="divide-y divide-cx-border-soft/80">
              <div v-for="item in group.items" :key="item.label" class="flex items-start justify-between gap-3 py-2 first:pt-1 last:pb-1">
                <dt class="text-[11px] leading-relaxed text-cx-ink-3">{{ item.label }}</dt>
                <dd class="max-w-[60%] break-words text-right text-[11px] font-medium leading-relaxed text-cx-ink-2">{{ item.value }}</dd>
              </div>
            </dl>
            <p v-else class="text-[11px] leading-relaxed text-cx-ink-3">No details recorded</p>
          </section>
        </div>
        <div v-if="!deploymentFid || (facility.hfr_sync_status && facility.hfr_sync_status !== 'HFR Verified')" class="flex flex-wrap items-center justify-between gap-3 border-t border-cx-border-soft bg-cx-warning-soft/25 px-4 py-3 sm:px-6">
          <p class="text-[11px] leading-relaxed text-cx-warning-ink">
            {{ !deploymentFid ? 'A verified HFR FID is required for deployment status and setup.' : `FID ${deploymentFid} is saved, but this profile has not been verified against the Health Facility Registry.` }}
          </p>
          <button type="button" class="text-[11px] font-semibold text-cx-warning-ink underline-offset-2 hover:underline" @click="emit('open-support', facility)">Contact network support</button>
        </div>
      </section>

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

    <div v-if="errorDetailsOpen" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm" role="presentation" tabindex="-1" @click.self="errorDetailsOpen = false" @keydown.esc="errorDetailsOpen = false">
      <section role="dialog" aria-modal="true" aria-labelledby="hmis-error-details-title" class="w-full max-w-3xl overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl">
        <header class="flex items-start justify-between gap-4 border-b border-slate-200 bg-white px-5 py-4">
          <div>
            <div class="flex flex-wrap items-center gap-2">
              <h2 id="hmis-error-details-title" class="text-sm font-bold text-slate-900">Deployment service diagnostics</h2>
              <span v-if="errorHttpStatus" class="rounded-full bg-red-50 px-2 py-0.5 font-mono text-[10px] font-semibold text-red-700">HTTP {{ errorHttpStatus }}</span>
            </div>
            <p class="mt-1 text-[11px] text-slate-600">MFL {{ facility.mfl_code }} · FID {{ deploymentFid || 'not linked' }}</p>
            <p v-if="errorCorrelationId" class="mt-1 break-all font-mono text-[10px] text-slate-500">Correlation ID: {{ errorCorrelationId }}</p>
          </div>
          <button type="button" class="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-[11px] font-semibold text-slate-700 hover:bg-slate-50" @click="errorDetailsOpen = false">Close</button>
        </header>
        <div class="bg-slate-950 px-5 py-4">
          <p class="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400">Upstream response / deployment log</p>
          <pre class="max-h-[60vh] overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-slate-100">{{ errorDetails }}</pre>
        </div>
        <p class="border-t border-slate-200 bg-slate-50 px-5 py-3 text-[11px] leading-relaxed text-slate-600">Credentials are redacted. If the response only says “Internal Server Error,” the deployment service did not include its traceback in the API response; share the correlation ID with the deployment administrator so they can find the server-side log.</p>
      </section>
    </div>
  </section>
</template>

