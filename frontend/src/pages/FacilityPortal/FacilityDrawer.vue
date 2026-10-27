<script setup>
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import CxIcon from './components/CxIcon.vue'
import { facilityId } from '@/utils/facilityId'
import { invoiceStatus, packageLabel } from '@/utils/portalOrderState'

const props = defineProps({
  facility: { type: Object, required: true },
  invoices: { type: Array, default: () => [] },
  orders: { type: Array, default: () => [] },
  tokenPackages: { type: Array, default: () => [] },
  copiedMfl: { type: String, default: '' },
  defaultCurrency: { type: String, default: 'KES' },
})

const emit = defineEmits([
  'close',
  'open-top-up',
  'open-calculator',
  'pay',
  'create-invoice',
  'copy-mfl',
])

const drawerRef = ref(null)
const closeButtonRef = ref(null)
let returnFocusTo = null

function closeDrawer() {
  emit('close')
  nextTick(() => returnFocusTo?.focus?.())
}

function handleDialogKeydown(event) {
  if (event.key === 'Escape') {
    event.preventDefault()
    closeDrawer()
    return
  }

  if (event.key !== 'Tab') return
  const focusable = [...(drawerRef.value?.querySelectorAll('button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])') || [])]
  if (!focusable.length) return
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

onMounted(() => {
  returnFocusTo = document.activeElement instanceof HTMLElement ? document.activeElement : null
  closeButtonRef.value?.focus()
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleDialogKeydown)
})

onMounted(() => document.addEventListener('keydown', handleDialogKeydown))

function money(value, currency) {
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: currency || props.defaultCurrency || 'KES',
    maximumFractionDigits: 0,
  }).format(value || 0)
}
</script>

<template>
  <div class="fixed inset-0 z-40" role="dialog" aria-modal="true" aria-labelledby="facility-drawer-title">
    <div class="absolute inset-0 bg-cx-overlay" @click="closeDrawer"></div>
    <div ref="drawerRef" class="absolute right-0 top-0 flex h-full w-full max-w-lg flex-col border-l border-cx-border bg-cx-surface shadow-cx-raised" tabindex="-1">
      <!-- Drawer header -->
      <div class="flex h-16 shrink-0 items-center justify-between border-b border-cx-border px-5">
        <div class="min-w-0">
          <span class="text-[11px] font-semibold uppercase tracking-[0.08em] text-cx-ink-3">Facility details</span>
          <h2 id="facility-drawer-title" class="truncate text-base font-bold tracking-tight text-cx-ink">{{ facility.facility_name }}</h2>
        </div>
        <button
          type="button"
          ref="closeButtonRef"
          aria-label="Close facility details"
          class="rounded-cx-sm border border-cx-border p-1.5 text-cx-ink-3 hover:bg-cx-well"
          title="Close details"
          @click="closeDrawer"
        >
          <svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div class="flex-1 space-y-5 overflow-y-auto p-5">
        <!-- Identity & compliance -->
        <div class="space-y-2 rounded-cx-sm border border-cx-border bg-cx-well p-4 text-xs">
          <div class="flex items-center justify-between">
            <span class="font-medium text-cx-ink-3">Network</span>
            <span class="font-bold text-cx-ink"><CxIcon name="globe" class="inline-block size-4 align-[-0.15em]" /> {{ facility.network }}</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="font-medium text-cx-ink-3">KEPH Level</span>
            <span class="font-bold text-cx-ink">{{ facility.keph_level }}</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="font-medium text-cx-ink-3">Facility ID</span>
            <span class="font-mono font-semibold text-cx-ink">{{ facilityId(facility) || 'Not linked yet' }}</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="font-medium text-cx-ink-3">MFL Code</span>
            <button
              type="button"
              class="inline-flex items-center gap-1.5 rounded-cx-sm border border-cx-border-soft bg-cx-surface px-2 py-0.5 font-mono text-xs font-semibold text-cx-ink-2 hover:text-cx-brand"
              @click="emit('copy-mfl', facility.mfl_code)"
            >
              <span>{{ facility.mfl_code }}</span>
              <CxIcon :name="copiedMfl === facility.mfl_code ? 'check' : 'copy'" class="size-3.5" />
            </button>
          </div>
          <div class="flex items-center justify-between">
            <span class="font-medium text-cx-ink-3">Go-live readiness</span>
            <span
              class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold"
              :class="facility.go_live ? 'border-cx-success-border bg-cx-success-soft text-cx-success-ink' : 'border-cx-warning-border bg-cx-warning-soft text-cx-warning-ink'"
            >
              <span class="size-1.5 rounded-full" :class="facility.go_live ? 'bg-cx-success' : 'bg-amber-600'"></span>
              <span>{{ facility.membership_status === 'Lead Inquiry' ? 'Lead inquiry' : facility.go_live ? 'Ready for go-live' : 'Implementation in progress' }}</span>
            </span>
          </div>
          <div class="flex items-center justify-between border-t border-cx-border-soft pt-2">
            <span class="font-medium text-cx-ink-3">Organization</span>
            <span class="font-bold text-cx-ink">{{ facility.organization || '—' }}</span>
          </div>
          <div v-if="facility.source_type === 'ois'" class="flex items-center justify-between">
            <span class="font-medium text-cx-ink-3">Enrolled via</span>
            <span class="font-mono text-[11px] font-semibold text-cx-ink">{{ facility.ois_name }}</span>
          </div>
        </div>

        <!-- Token capacity -->
        <div class="space-y-3">
          <h3 class="text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink-3">Token capacity</h3>
          <div class="rounded-cx-sm border border-cx-border bg-cx-surface p-4">
            <div class="flex items-baseline gap-2">
              <span class="font-mono text-2xl font-bold tracking-tight text-cx-brand"><CxIcon name="coins" class="inline-block size-4 align-[-0.15em]" /> {{ (facility.token_balance?.status === 'ok' ? Number(facility.token_balance.balance) || 0 : 0).toLocaleString() }}</span>
              <span class="text-xs font-semibold text-cx-ink-3">Care Tokens available</span>
            </div>
            <p class="mt-1 text-[11px] text-cx-ink-3">
              Plan: <strong class="text-cx-ink">{{ facility.token_package || 'No active plan' }}</strong>
            </p>
            <p v-if="facility.recent_purchase" class="mt-1 font-mono text-[11px] text-cx-ink-3">
              Last purchase: {{ facility.recent_purchase.package_name }} · {{ money(facility.recent_purchase.amount, facility.recent_purchase.currency) }} on {{ facility.recent_purchase.date }}
            </p>
            <div class="mt-3 flex items-center gap-2">
              <button
                type="button"
                class="flex-1 rounded-cx-sm bg-cx-ink px-3 py-2 text-xs font-semibold text-cx-contrast transition hover:bg-cx-ink-hover"
                @click="emit('open-top-up', facility)"
              >
                + Top Up Tokens
              </button>
              <button
                type="button"
                class="rounded-cx-sm border border-cx-border bg-cx-surface p-2 text-cx-ink-2 hover:bg-cx-well"
                title="Sizing Calculator"
                @click="emit('open-calculator', facility)"
              >
                <CxIcon name="calculator" class="inline-block size-4 align-[-0.15em]" />
              </button>
            </div>
          </div>
        </div>

        <!-- Facility invoices -->
        <div class="space-y-3">
          <h3 class="text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink-3">Invoices</h3>
          <div v-if="!invoices.length" class="rounded-cx-sm border border-cx-border bg-cx-surface p-4 text-xs text-cx-ink-3">
            <span class="text-base"><CxIcon name="check-circle" class="inline-block size-4 align-[-0.15em]" /></span>
            <p class="mt-1 font-bold text-cx-ink-2">All invoices settled</p>
            <p class="mt-0.5">No outstanding balance for this facility.</p>
          </div>
          <div v-else class="space-y-2">
            <article
              v-for="invoice in invoices"
              :key="invoice.name"
              class="flex items-center justify-between gap-3 rounded-cx-sm border border-cx-border bg-cx-surface p-3.5"
            >
              <div class="min-w-0">
                <div class="flex items-center gap-2">
                  <span class="truncate font-semibold text-xs text-cx-ink">{{ invoice.invoice_number || invoice.name }}</span>
                  <span
                    class="rounded-cx-sm px-2 py-0.5 text-[11px] font-semibold"
                    :class="invoiceStatus(invoice).key === 'overdue' ? 'bg-cx-danger-soft text-cx-danger-ink' : 'bg-amber-100 text-cx-warning-ink'"
                  >
                    {{ invoiceStatus(invoice).label }}
                  </span>
                </div>
                <p class="mt-0.5 text-[11px] text-cx-ink-3">Due: {{ invoice.due_date || 'On Receipt' }}</p>
              </div>
              <div class="flex shrink-0 items-center gap-2">
                <span class="text-sm font-semibold text-cx-ink">{{ money(invoice.amount, invoice.currency) }}</span>
                <button
                  type="button"
                  class="rounded-cx-sm bg-cx-success px-2.5 py-1.5 text-[11px] font-semibold text-cx-contrast shadow-cx transition hover:bg-cx-success"
                  @click="emit('pay', invoice)"
                >
                  <CxIcon name="phone" class="inline-block size-4 align-[-0.15em]" /> Pay
                </button>
              </div>
            </article>
          </div>
        </div>

        <!-- Facility orders -->
        <div class="space-y-3">
          <h3 class="text-xs font-semibold uppercase tracking-[0.08em] text-cx-ink-3">Orders</h3>
          <div v-if="!orders.length" class="rounded-cx-sm border border-cx-border bg-cx-surface p-4 text-xs text-cx-ink-3">
            No open token orders for this facility.
          </div>
          <div v-else class="space-y-2">
            <article
              v-for="order in orders"
              :key="order.name"
              class="flex items-center justify-between gap-3 rounded-cx-sm border border-cx-border bg-cx-surface p-3.5"
            >
              <div class="min-w-0">
                <span class="block truncate text-xs font-semibold text-cx-ink">{{ packageLabel(order.crm_token_package_item, tokenPackages) }}</span>
                <span class="block font-mono text-[11px] text-cx-ink-3">Order #{{ order.name }}</span>
              </div>
              <div class="flex shrink-0 items-center gap-2">
                <span class="text-xs font-semibold text-cx-ink">{{ money(order.grand_total, order.currency) }}</span>
                <button
                  v-if="order.can_create_invoice"
                  type="button"
                  class="rounded-cx-sm bg-cx-ink px-2.5 py-1.5 text-[11px] font-semibold text-cx-contrast transition hover:bg-cx-ink-hover"
                  @click="emit('create-invoice', order)"
                >
                  Generate Invoice
                </button>
              </div>
            </article>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
