<template>
  <div class="fc-finance-table">
    <!-- Loading state -->
    <div v-if="loading" class="overflow-hidden rounded-xl border border-outline-gray-1 bg-surface-white p-3 sm:p-4" role="status" aria-live="polite">
      <span class="sr-only">Loading finance records…</span>
      <div class="mb-3 hidden h-8 animate-pulse rounded bg-surface-gray-1 sm:block" />
      <div class="space-y-2">
        <div v-for="n in 5" :key="n" class="grid h-12 grid-cols-2 gap-3 rounded-lg bg-surface-gray-1 px-3 py-2 sm:grid-cols-4">
          <span class="animate-pulse rounded bg-surface-gray-2" />
          <span class="animate-pulse rounded bg-surface-gray-2" />
          <span class="hidden animate-pulse rounded bg-surface-gray-2 sm:block" />
          <span class="hidden animate-pulse rounded bg-surface-gray-2 sm:block" />
        </div>
      </div>
    </div>

    <!-- Error state -->
    <FinanceErrorState v-else-if="error" :error="error" @retry="$emit('retry')" />

    <!-- Empty state -->
    <div v-else-if="!rows || !rows.length" class="rounded-xl border border-dashed border-outline-gray-2 bg-surface-white px-5 py-10 text-center" role="status">
      <span class="mx-auto flex size-10 items-center justify-center rounded-xl bg-surface-gray-1 text-ink-gray-5">
        <span class="lucide-inbox size-5" aria-hidden="true" />
      </span>
      <p class="mt-3 text-sm font-medium text-ink-gray-7">{{ emptyLabel || 'No records found.' }}</p>
      <p class="mt-1 text-xs text-ink-gray-5">Try another status or check the selected Company.</p>
    </div>

    <!-- Desktop table -->
    <div
      v-else-if="!isMobile"
      class="overflow-x-auto rounded-xl border border-outline-gray-1 bg-surface-white shadow-sm"
    >
      <table class="w-full text-sm">
        <caption class="sr-only">Finance records for the selected Company</caption>
        <thead
          class="sticky top-0 bg-surface-gray-1 border-b border-outline-gray-1"
        >
          <tr>
            <th
              v-for="col in columns"
              :key="col.key"
              :class="[
                'px-3 py-2.5 text-left text-xs font-semibold text-ink-gray-5 uppercase tracking-wide whitespace-nowrap',
                col.align === 'right' ? 'text-right' : '',
              ]"
            >
              {{ col.label }}
            </th>
            <th
              v-if="$slots.actions"
              class="px-3 py-2.5 text-right text-xs font-semibold text-ink-gray-5 uppercase tracking-wide"
            >
              Actions
            </th>
          </tr>
        </thead>
        <tbody class="divide-y divide-outline-gray-1">
          <tr
            v-for="row in rows"
            :key="row.name"
            class="cursor-pointer transition-colors hover:bg-surface-gray-1 focus-visible:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-blue-3"
            tabindex="0"
            :aria-label="`Open ${row.name || 'finance record'}`"
            @click="$emit('row-click', row)"
            @keydown.enter.self.prevent="$emit('row-click', row)"
            @keydown.space.self.prevent="$emit('row-click', row)"
          >
            <td
              v-for="col in columns"
              :key="col.key"
              :class="[
                'px-3 py-2.5 text-ink-gray-7',
                col.align === 'right' ? 'text-right' : '',
              ]"
            >
              <StatusPill v-if="col.type === 'status'" :status="row[col.key]" />
              <span v-else-if="col.type === 'currency'" class="font-medium">
                {{ formatCurrency(row[col.key], row.currency) }}
              </span>
              <span v-else-if="col.type === 'date'" class="text-xs">{{
                row[col.key] || '—'
              }}</span>
              <a
                v-else-if="col.type === 'link' && linkHref(row, col)"
                :href="linkHref(row, col)"
                class="font-medium text-ink-blue-6 underline underline-offset-2 hover:text-ink-blue-7"
                @click.stop
              >{{ row[col.key] }}</a>
              <span v-else-if="col.type === 'link'" class="text-ink-gray-5">
                {{ linkFallback(row, col) }}
              </span>
              <span v-else>{{ row[col.key] ?? '—' }}</span>
            </td>
            <td v-if="$slots.actions" class="px-3 py-2.5 text-right">
              <slot name="actions" :row="row" />
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Mobile card layout -->
    <div v-else class="space-y-3">
      <div
        v-for="row in rows"
        :key="row.name"
        class="rounded-xl border border-outline-gray-1 bg-surface-white p-3 shadow-sm"
      >
        <div class="flex items-start justify-between gap-2 mb-2">
          <div>
            <button type="button" class="rounded text-left font-medium text-ink-gray-8 text-sm hover:text-ink-red-7 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-blue-3" :aria-label="`Open ${row.name || 'finance record'}`" @click="$emit('row-click', row)">
              {{ row[columns[0]?.key] || row.name }}
            </button>
            <p class="text-xs text-ink-gray-5 mt-0.5">
              <a
                v-if="columns[1]?.type === 'link' && linkHref(row, columns[1])"
                :href="linkHref(row, columns[1])"
                class="underline underline-offset-2 text-ink-blue-6 hover:text-ink-blue-7"
                @click.stop
              >{{ row[columns[1]?.key] }}</a>
              <template v-else-if="columns[1]?.type === 'link'">
                {{ linkFallback(row, columns[1]) }}
              </template>
              <template v-else>{{ row[columns[1]?.key] }}</template>
            </p>
          </div>
          <div class="text-right flex-shrink-0">
            <p
              v-if="amountCol"
              class="font-semibold text-ink-gray-7 text-sm"
            >
              {{ formatCurrency(row[amountCol.key], row.currency) }}
            </p>
            <StatusPill v-if="statusCol" :status="row[statusCol.key]" />
          </div>
        </div>
        <div v-if="$slots.actions" class="mt-2 flex flex-col gap-1.5">
          <slot name="actions" :row="row" />
        </div>
      </div>
    </div>

    <!-- Pagination -->
    <div
      v-if="rows && rows.length && (rows.length === pageSize || page > 0)"
      class="flex items-center justify-end gap-2 mt-3"
    >
      <button
        :disabled="page <= 0"
        class="px-3 py-1 text-xs rounded border border-outline-gray-2 disabled:opacity-40 hover:bg-surface-gray-2 transition-colors"
        @click="$emit('update:page', page - 1)"
      >
        Previous
      </button>
      <span class="text-xs text-ink-gray-5">Page {{ page + 1 }}</span>
      <button
        :disabled="rows.length < pageSize"
        class="px-3 py-1 text-xs rounded border border-outline-gray-2 disabled:opacity-40 hover:bg-surface-gray-2 transition-colors"
        @click="$emit('update:page', page + 1)"
      >
        Next
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import StatusPill from './StatusPill.vue'
import { useBreakpoint } from '../composables/useBreakpoint.js'
import { useCurrency } from '../composables/useCurrency.js'
import FinanceErrorState from './FinanceErrorState.vue'

const props = defineProps({
  columns: { type: Array, default: () => [] },
  rows: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: Object, default: null },
  emptyLabel: { type: String, default: '' },
  page: { type: Number, default: 0 },
  pageSize: { type: Number, default: 20 },
})

defineEmits(['row-click', 'retry', 'update:page'])

const { isMobile } = useBreakpoint()
const { formatCurrency } = useCurrency()
const amountCol = computed(() =>
  props.columns.find((c) => c.type === 'currency'),
)
const statusCol = computed(() => props.columns.find((c) => c.type === 'status'))

function linkHref(row, col) {
  const name = row?.[col.linkKey]
  const doctype = col.linkDoctype
  if (
    !name ||
    !doctype ||
    row?.[col.availableKey || 'network_available'] !== true ||
    typeof name !== 'string' ||
    name.includes('/') ||
    name.includes('\\') ||
    [...name].some((character) => character.charCodeAt(0) < 32)
  ) {
    return ''
  }
  const slug = doctype.trim().toLowerCase().replace(/\s+/g, '-')
  const company = row.company
  const companyQuery = company ? `?company=${encodeURIComponent(company)}` : ''
  return `/app/${encodeURIComponent(slug)}/${encodeURIComponent(name)}${companyQuery}`
}

function linkFallback(row, col) {
  if (row?.[col.key]) return row[col.key]
  return row?.[col.linkKey] ? 'Network unavailable' : 'Network not linked'
}
</script>
