<script setup>
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

function money(value, currency) {
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: currency || props.defaultCurrency || 'KES',
    maximumFractionDigits: 0,
  }).format(value || 0)
}
</script>

<template>
  <div class="fixed inset-0 z-40" role="dialog" aria-modal="true">
    <div class="absolute inset-0 bg-slate-900/30" @click="emit('close')"></div>
    <div class="absolute right-0 top-0 flex h-full w-full max-w-lg flex-col border-l border-slate-200 bg-white shadow-2xl">
      <!-- Drawer header -->
      <div class="flex h-16 shrink-0 items-center justify-between border-b border-slate-200 px-5">
        <div class="min-w-0">
          <span class="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">Facility details</span>
          <h2 class="truncate text-base font-bold tracking-tight text-slate-900">{{ facility.facility_name }}</h2>
        </div>
        <button
          type="button"
          class="rounded-lg border border-slate-200 p-1.5 text-slate-600 hover:bg-slate-50"
          title="Close details"
          @click="emit('close')"
        >
          <svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div class="flex-1 space-y-5 overflow-y-auto p-5">
        <!-- Identity & compliance -->
        <div class="space-y-2 rounded-xl border border-slate-200 bg-slate-50 p-4 text-xs">
          <div class="flex items-center justify-between">
            <span class="font-medium text-slate-500">Network</span>
            <span class="font-bold text-slate-900">🌐 {{ facility.network }}</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="font-medium text-slate-500">KEPH Level</span>
            <span class="font-bold text-slate-900">{{ facility.keph_level }}</span>
          </div>
          <div class="flex items-center justify-between">
            <span class="font-medium text-slate-500">MFL Code</span>
            <button
              type="button"
              class="inline-flex items-center gap-1.5 rounded border border-slate-200/60 bg-white px-2 py-0.5 font-mono text-xs font-semibold text-slate-700 hover:text-blue-600"
              @click="emit('copy-mfl', facility.mfl_code)"
            >
              <span>{{ facility.mfl_code }}</span>
              <span class="text-[11px]">{{ copiedMfl === facility.mfl_code ? '✓' : '📋' }}</span>
            </button>
          </div>
          <div class="flex items-center justify-between">
            <span class="font-medium text-slate-500">Registry Status</span>
            <span
              class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold"
              :class="facility.go_live ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-amber-200 bg-amber-50 text-amber-800'"
            >
              <span class="size-1.5 rounded-full" :class="facility.go_live ? 'bg-emerald-600' : 'bg-amber-600'"></span>
              <span>{{ facility.go_live ? 'Live on Health Facility Registry' : 'Verifying' }}</span>
            </span>
          </div>
          <div class="flex items-center justify-between border-t border-slate-200/60 pt-2">
            <span class="font-medium text-slate-500">Organization</span>
            <span class="font-bold text-slate-900">{{ facility.organization || '—' }}</span>
          </div>
          <div v-if="facility.source_type === 'ois'" class="flex items-center justify-between">
            <span class="font-medium text-slate-500">Enrolled via</span>
            <span class="font-mono text-[11px] font-semibold text-slate-900">{{ facility.ois_name }}</span>
          </div>
        </div>

        <!-- Token capacity -->
        <div class="space-y-3">
          <h3 class="text-xs font-semibold uppercase tracking-[0.08em] text-slate-600">Token capacity</h3>
          <div class="rounded-xl border border-slate-200 bg-white p-4">
            <div class="flex items-baseline gap-2">
              <span class="font-mono text-2xl font-bold tracking-tight text-[#bc1823]">🪙 {{ (facility.token_quantity || 0).toLocaleString() }}</span>
              <span class="text-xs font-semibold text-slate-600">Care Tokens</span>
            </div>
            <p class="mt-1 text-[11px] text-slate-500">
              Plan: <strong class="text-slate-900">{{ facility.token_package || 'No active plan' }}</strong>
            </p>
            <p v-if="facility.recent_purchase" class="mt-1 font-mono text-[11px] text-slate-500">
              Last purchase: {{ facility.recent_purchase.package_name }} · {{ money(facility.recent_purchase.amount, facility.recent_purchase.currency) }} on {{ facility.recent_purchase.date }}
            </p>
            <div class="mt-3 flex items-center gap-2">
              <button
                type="button"
                class="flex-1 rounded-xl bg-slate-900 px-3 py-2 text-xs font-semibold text-white transition hover:bg-black"
                @click="emit('open-top-up', facility)"
              >
                + Top Up Tokens
              </button>
              <button
                type="button"
                class="rounded-xl border border-slate-200 bg-white p-2 text-slate-700 hover:bg-slate-50"
                title="Sizing Calculator"
                @click="emit('open-calculator', facility)"
              >
                🧮
              </button>
            </div>
          </div>
        </div>

        <!-- Facility invoices -->
        <div class="space-y-3">
          <h3 class="text-xs font-semibold uppercase tracking-[0.08em] text-slate-600">Invoices</h3>
          <div v-if="!invoices.length" class="rounded-xl border border-slate-200 bg-white p-4 text-xs text-slate-500">
            <span class="text-base">✅</span>
            <p class="mt-1 font-bold text-slate-700">All invoices settled</p>
            <p class="mt-0.5">No outstanding balance for this facility.</p>
          </div>
          <div v-else class="space-y-2">
            <article
              v-for="invoice in invoices"
              :key="invoice.name"
              class="flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-3.5"
            >
              <div class="min-w-0">
                <div class="flex items-center gap-2">
                  <span class="truncate font-semibold text-xs text-slate-900">{{ invoice.invoice_number || invoice.name }}</span>
                  <span
                    class="rounded px-2 py-0.5 text-[11px] font-semibold"
                    :class="invoiceStatus(invoice).key === 'overdue' ? 'bg-rose-100 text-rose-800' : 'bg-amber-100 text-amber-800'"
                  >
                    {{ invoiceStatus(invoice).label }}
                  </span>
                </div>
                <p class="mt-0.5 text-[11px] text-slate-500">Due: {{ invoice.due_date || 'On Receipt' }}</p>
              </div>
              <div class="flex shrink-0 items-center gap-2">
                <span class="text-sm font-semibold text-slate-900">{{ money(invoice.amount, invoice.currency) }}</span>
                <button
                  type="button"
                  class="rounded-lg bg-emerald-600 px-2.5 py-1.5 text-[11px] font-semibold text-white shadow-xs transition hover:bg-emerald-700"
                  @click="emit('pay', invoice)"
                >
                  📱 Pay
                </button>
              </div>
            </article>
          </div>
        </div>

        <!-- Facility orders -->
        <div class="space-y-3">
          <h3 class="text-xs font-semibold uppercase tracking-[0.08em] text-slate-600">Orders</h3>
          <div v-if="!orders.length" class="rounded-xl border border-slate-200 bg-white p-4 text-xs text-slate-500">
            No open token orders for this facility.
          </div>
          <div v-else class="space-y-2">
            <article
              v-for="order in orders"
              :key="order.name"
              class="flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-3.5"
            >
              <div class="min-w-0">
                <span class="block truncate text-xs font-semibold text-slate-900">{{ packageLabel(order.crm_token_package_item, tokenPackages) }}</span>
                <span class="block font-mono text-[11px] text-slate-500">Order #{{ order.name }}</span>
              </div>
              <div class="flex shrink-0 items-center gap-2">
                <span class="text-xs font-semibold text-slate-800">{{ money(order.grand_total, order.currency) }}</span>
                <button
                  v-if="order.can_create_invoice"
                  type="button"
                  class="rounded-lg bg-slate-900 px-2.5 py-1.5 text-[11px] font-semibold text-white transition hover:bg-black"
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
