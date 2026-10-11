<template>
  <div class="fc-finance-table fc-card-frame">
    <!-- Optional Collapsible Summary Strip -->
    <div
      v-if="summaryStats && summaryStats.length"
      class="fc-summary-strip border-b border-outline-gray-1"
    >
      <div
        v-for="stat in summaryStats"
        :key="stat.label"
        class="fc-summary-pill flex-shrink-0"
      >
        <span class="text-ink-gray-5">{{ stat.label }}:</span>
        <strong>{{ stat.value }}</strong>
      </div>
    </div>

    <!-- Loading state: Skeleton rows -->
    <div v-if="loading" class="p-4 space-y-3">
      <div
        v-for="n in 5"
        :key="n"
        class="h-12 bg-surface-gray-2 rounded-lg animate-pulse"
      />
    </div>

    <!-- Error state -->
    <div v-else-if="error" class="p-6">
      <FinanceErrorState :error="error" @retry="$emit('retry')" />
    </div>

    <!-- Empty state -->
    <div
      v-else-if="!rows || !rows.length"
      class="text-center py-12 px-4 text-sm text-ink-gray-5"
    >
      <p class="font-medium text-ink-gray-7">{{ emptyLabel || 'No records found.' }}</p>
      <p class="text-xs text-ink-gray-4 mt-1">Try clearing or adjusting your active filters.</p>
    </div>

    <!-- Desktop table with collapsible rows -->
    <div
      v-else-if="!isMobile"
      class="overflow-x-auto"
    >
      <table class="w-full text-sm border-collapse">
        <thead class="bg-surface-gray-1 border-b border-outline-gray-1 text-ink-gray-6">
          <tr>
            <th v-if="collapsible" class="w-8 px-3 py-2.5"></th>
            <th
              v-for="col in columns"
              :key="col.key"
              :class="[
                'px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider whitespace-nowrap',
                col.align === 'right' ? 'text-right' : '',
              ]"
            >
              {{ col.label }}
            </th>
            <th
              v-if="$slots.actions"
              class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider"
            >
              Actions
            </th>
          </tr>
        </thead>
        <tbody class="divide-y divide-outline-gray-1">
          <template v-for="row in rows" :key="row.name">
            <tr
              class="hover:bg-surface-gray-1 cursor-pointer transition-colors group"
              @click="handleRowClick(row)"
            >
              <!-- Expand toggle -->
              <td
                v-if="collapsible"
                class="w-8 px-3 py-3 text-ink-gray-4 group-hover:text-ink-gray-7"
                @click.stop="toggleExpand(row.name)"
              >
                <span
                  class="lucide-chevron-right size-4 transition-transform inline-block"
                  :class="{ 'rotate-90': expandedRowKeys.includes(row.name) }"
                />
              </td>
              <td
                v-for="col in columns"
                :key="col.key"
                :class="[
                  'px-4 py-3 text-ink-gray-8',
                  col.align === 'right' ? 'text-right' : '',
                ]"
              >
                <StatusPill v-if="col.type === 'status'" :status="row[col.key]" />
                <span v-else-if="col.type === 'currency'" class="font-semibold tabular-nums text-ink-gray-9">
                  {{ formatCurrency(row[col.key], row.currency) }}
                </span>
                <span v-else-if="col.type === 'date'" class="text-xs text-ink-gray-6">
                  {{ row[col.key] || '—' }}
                </span>
                <span v-else-if="col.type === 'owner'" class="text-xs text-ink-gray-5">
                  {{ row[col.key] || '—' }}
                </span>
                <span v-else class="truncate max-w-xs inline-block align-middle">
                  {{ row[col.key] ?? '—' }}
                </span>
              </td>
              <td
                v-if="$slots.actions"
                class="px-4 py-3 text-right"
                @click.stop
              >
                <slot name="actions" :row="row" />
              </td>
            </tr>

            <!-- Expanded Collapsible Drawer Row -->
            <tr v-if="collapsible && expandedRowKeys.includes(row.name)" class="bg-surface-gray-1/60">
              <td :colspan="columns.length + (collapsible ? 1 : 0) + ($slots.actions ? 1 : 0)" class="p-0">
                <div class="fc-row-details">
                  <slot name="expanded-row" :row="row">
                    <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 p-2">
                      <div>
                        <div class="text-[11px] font-medium text-ink-gray-5 uppercase">Record ID</div>
                        <div class="text-xs font-semibold text-ink-gray-8 mt-0.5">{{ row.name }}</div>
                      </div>
                      <div v-if="row.creation">
                        <div class="text-[11px] font-medium text-ink-gray-5 uppercase">Created</div>
                        <div class="text-xs text-ink-gray-7 mt-0.5">{{ row.creation }}</div>
                      </div>
                      <div v-if="row.modified">
                        <div class="text-[11px] font-medium text-ink-gray-5 uppercase">Last Modified</div>
                        <div class="text-xs text-ink-gray-7 mt-0.5">{{ row.modified }}</div>
                      </div>
                      <div v-if="row.owner">
                        <div class="text-[11px] font-medium text-ink-gray-5 uppercase">Owner</div>
                        <div class="text-xs text-ink-gray-7 mt-0.5">{{ row.owner }}</div>
                      </div>
                    </div>
                  </slot>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <!-- Mobile Card View inspired by CareVerse HQ MobileCardView -->
    <div v-else class="p-3 space-y-3">
      <div
        v-for="row in rows"
        :key="row.name"
        class="fc-mobile-card cursor-pointer"
        @click="handleRowClick(row)"
      >
        <div class="flex items-start justify-between gap-2 mb-2">
          <div class="min-w-0 flex-1">
            <p class="font-semibold text-ink-gray-9 text-sm truncate">
              {{ row[columns[0]?.key] || row.name }}
            </p>
            <p v-if="columns[1]" class="text-xs text-ink-gray-5 mt-0.5 truncate">
              {{ row[columns[1]?.key] }}
            </p>
          </div>
          <div class="text-right flex-shrink-0">
            <p v-if="amountCol" class="font-bold text-ink-gray-9 text-sm tabular-nums">
              {{ formatCurrency(row[amountCol.key], row.currency) }}
            </p>
            <StatusPill v-if="statusCol" :status="row[statusCol.key]" />
          </div>
        </div>

        <!-- Collapsible toggle button for mobile -->
        <div v-if="collapsible" class="mt-2 pt-2 border-t border-outline-gray-1 flex items-center justify-between text-xs text-ink-gray-5" @click.stop="toggleExpand(row.name)">
          <span>{{ expandedRowKeys.includes(row.name) ? 'Hide details' : 'Show details' }}</span>
          <span class="lucide-chevron-right size-3.5 transition-transform" :class="{ 'rotate-90': expandedRowKeys.includes(row.name) }" />
        </div>

        <!-- Mobile expanded details -->
        <div v-if="collapsible && expandedRowKeys.includes(row.name)" class="mt-2 pt-2 border-t border-outline-gray-2 text-xs">
          <slot name="expanded-row" :row="row">
            <div class="space-y-1 text-ink-gray-6">
              <div><span class="text-ink-gray-4">ID:</span> {{ row.name }}</div>
              <div v-if="row.modified"><span class="text-ink-gray-4">Modified:</span> {{ row.modified }}</div>
            </div>
          </slot>
        </div>

        <div v-if="$slots.actions" class="mt-3 pt-2 border-t border-outline-gray-1 flex flex-col gap-1.5" @click.stop>
          <slot name="actions" :row="row" />
        </div>
      </div>
    </div>

    <!-- Pagination -->
    <div
      v-if="rows && rows.length && (rows.length === pageSize || page > 0)"
      class="flex items-center justify-between px-4 py-3 bg-surface-gray-1 border-t border-outline-gray-1 text-xs"
    >
      <div class="text-ink-gray-5">
        Showing page {{ page + 1 }}
      </div>
      <div class="flex items-center gap-2">
        <button
          :disabled="page <= 0"
          class="px-3 py-1.5 rounded-md border border-outline-gray-2 bg-surface-white font-medium text-ink-gray-7 disabled:opacity-40 hover:bg-surface-gray-2 transition-colors"
          @click="$emit('update:page', page - 1)"
        >
          Previous
        </button>
        <button
          :disabled="rows.length < pageSize"
          class="px-3 py-1.5 rounded-md border border-outline-gray-2 bg-surface-white font-medium text-ink-gray-7 disabled:opacity-40 hover:bg-surface-gray-2 transition-colors"
          @click="$emit('update:page', page + 1)"
        >
          Next
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
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
  collapsible: { type: Boolean, default: true },
  summaryStats: { type: Array, default: () => [] },
})

const emit = defineEmits(['row-click', 'retry', 'update:page'])

const { isMobile } = useBreakpoint()
const { formatCurrency } = useCurrency()
const expandedRowKeys = ref([])

function toggleExpand(key) {
  if (expandedRowKeys.value.includes(key)) {
    expandedRowKeys.value = expandedRowKeys.value.filter((k) => k !== key)
  } else {
    expandedRowKeys.value.push(key)
  }
}

function handleRowClick(row) {
  emit('row-click', row)
}

const amountCol = computed(() =>
  props.columns.find((c) => c.type === 'currency'),
)
const statusCol = computed(() => props.columns.find((c) => c.type === 'status'))
</script>
