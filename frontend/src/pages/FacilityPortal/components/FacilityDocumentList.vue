<script setup>
// One tab of the facility page: a searchable, paged list of quotes, orders,
// invoices or payments. With `server` set (customer-linked facilities) rows come
// a page at a time from crm.api.facility_documents; otherwise the rows already in
// the portal context are paged locally. State lives in the map BillingJourney
// provides, so switching tabs (which unmounts the panel) keeps search, filter and page.
import { computed, inject, nextTick, onMounted, ref, watch } from 'vue'
import { call } from 'frappe-ui'
import CxIcon from './CxIcon.vue'
import {
  DOCUMENT_PAGE_SIZE,
  clampPage,
  filterRows,
  pageCount,
  pageOfRow,
  pageSlice,
  rangeText,
} from '@/utils/facilityTabs'

const props = defineProps({
  kind: { type: String, required: true },
  title: { type: String, required: true },
  rows: { type: Array, default: () => [] },
  server: { type: Object, default: null },
  // Key into the list-state map BillingJourney provides (search, filter, page, server rows).
  stateKey: { type: String, required: true },
  emptyText: { type: String, default: '' },
  pageSize: { type: Number, default: DOCUMENT_PAGE_SIZE },
})

const emit = defineEmits(['total'])
const listStates = inject('facilityListStates')
const state = computed(() => listStates[props.stateKey])

const statusOptions = computed(() =>
  props.kind === 'invoice'
    ? [
        { value: 'outstanding', label: 'Needs action' },
        { value: 'all', label: 'All invoices' },
      ]
    : [],
)

const loading = ref(false)
const error = ref('')
const highlighted = ref('')
const searchDraft = ref(state.value.search || '')
let searchTimer = null
let requestSeq = 0

const localFiltered = computed(() =>
  filterRows(props.rows, { kind: props.kind, status: state.value.status, search: state.value.search }),
)
const total = computed(() => (props.server ? state.value.serverTotal || 0 : localFiltered.value.length))
const visibleRows = computed(() =>
  props.server ? state.value.serverRows || [] : pageSlice(localFiltered.value, state.value.page, props.pageSize),
)
const pages = computed(() => pageCount(total.value, props.pageSize))
const range = computed(() => rangeText(state.value.page, total.value, props.pageSize))
const filtering = computed(() => Boolean(state.value.search) || state.value.status === 'outstanding')

async function load() {
  if (!props.server) return
  const seq = ++requestSeq
  loading.value = true
  error.value = ''
  try {
    const result = await call('crm.api.facility_documents.get_facility_documents', {
      customer: props.server.customer,
      mfl_code: props.server.mflCode,
      kind: props.kind,
      start: state.value.page * props.pageSize,
      page_length: props.pageSize,
      status: state.value.status,
      search: state.value.search,
    })
    if (seq !== requestSeq) return
    const data = result?.message || result || {}
    state.value.serverRows = data.rows || []
    state.value.serverTotal = Number(data.total) || 0
    state.value.loaded = true
    if (!state.value.search && state.value.status === 'all') emit('total', state.value.serverTotal)
  } catch {
    if (seq !== requestSeq) return
    error.value = 'We could not load these records.'
  } finally {
    if (seq === requestSeq) loading.value = false
  }
}

function setPage(page) {
  state.value.page = clampPage(page, total.value, props.pageSize)
  if (props.server) load()
}

function setStatus(value) {
  state.value.status = value
  state.value.page = 0
  if (props.server) load()
}

function onSearchInput(value) {
  searchDraft.value = value
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    state.value.search = String(value || '').trim()
    state.value.page = 0
    if (props.server) load()
  }, 300)
}

function clearFilters() {
  searchDraft.value = ''
  state.value.search = ''
  state.value.status = 'all'
  state.value.page = 0
  if (props.server) load()
}

// Cross-links: show the row and highlight it.
async function reveal(name) {
  if (props.server) {
    searchDraft.value = String(name)
    state.value.search = String(name)
    state.value.status = 'all'
    state.value.page = 0
    await load()
  } else {
    let page = pageOfRow(localFiltered.value, name, props.pageSize)
    if (page < 0) {
      searchDraft.value = ''
      state.value.search = ''
      state.value.status = 'all'
      page = pageOfRow(localFiltered.value, name, props.pageSize)
    }
    if (page >= 0) state.value.page = page
  }
  highlighted.value = String(name)
  await nextTick()
  const target = document.getElementById(`doc-${name}`)
  if (target) {
    target.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    target.focus({ preventScroll: true })
  }
  setTimeout(() => {
    if (highlighted.value === String(name)) highlighted.value = ''
  }, 2500)
}

defineExpose({ reveal, reload: load })

// The portal context reloads after a payment or a new invoice: refresh this page.
watch(
  () => props.rows,
  () => {
    if (props.server && state.value.loaded) load()
    else state.value.page = clampPage(state.value.page, localFiltered.value.length, props.pageSize)
  },
)

onMounted(() => {
  if (props.server && !state.value.loaded) load()
})
</script>

<template>
  <section class="rounded-cx border border-cx-border bg-cx-surface p-4 shadow-cx sm:p-5" :data-testid="`stage-${kind}`" :aria-busy="loading">
    <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
      <h3 class="text-base font-semibold text-cx-ink">{{ title }}</h3>
      <div class="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
        <label class="relative w-full min-w-0 sm:w-56">
          <span class="sr-only">Search {{ title.toLowerCase() }}</span>
          <CxIcon name="search" class="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-cx-ink-3" />
          <input
            type="search"
            :value="searchDraft"
            :placeholder="`Search ${title.toLowerCase()}`"
            class="min-h-9 w-full rounded-cx-sm border border-cx-border bg-cx-surface py-1.5 pl-8 pr-2 text-xs text-cx-ink placeholder:text-cx-ink-3 focus:border-cx-brand focus:outline-none focus:ring-2 focus:ring-cx-brand/20"
            :data-testid="`stage-${kind}-search`"
            @input="onSearchInput($event.target.value)"
          />
        </label>
        <div v-if="statusOptions.length" class="flex w-full rounded-cx-sm border border-cx-border bg-cx-well p-0.5 sm:inline-flex sm:w-auto" role="group" :aria-label="`Filter ${title.toLowerCase()}`">
          <button
            v-for="option in statusOptions"
            :key="option.value"
            type="button"
            class="min-h-8 flex-1 whitespace-nowrap rounded-cx-sm px-2.5 text-xs font-semibold sm:flex-none"
            :class="state.status === option.value ? 'bg-cx-surface text-cx-ink shadow-cx' : 'text-cx-ink-2 hover:text-cx-ink'"
            :aria-pressed="state.status === option.value"
            :data-testid="`stage-${kind}-filter-${option.value}`"
            @click="setStatus(option.value)"
          >
            {{ option.label }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="error" class="flex flex-wrap items-center justify-between gap-2 rounded-cx-sm border border-cx-warning-border bg-cx-warning-soft/60 p-4 text-xs text-cx-warning-ink" role="alert">
      <span>{{ error }}</span>
      <button type="button" class="font-semibold underline" @click="load">Try again</button>
    </div>
    <div v-else-if="loading && !visibleRows.length" class="rounded-cx-sm bg-cx-well p-4 text-xs text-cx-ink-2">Loading…</div>
    <div v-else-if="!visibleRows.length" class="rounded-cx-sm bg-cx-well p-4 text-xs text-cx-ink-2" :data-testid="`stage-${kind}-empty`">
      <template v-if="filtering">
        No {{ title.toLowerCase() }} match this search or filter.
        <button type="button" class="ml-1 font-semibold text-cx-brand underline-offset-2 hover:underline" @click="clearFilters">Clear</button>
      </template>
      <template v-else>{{ emptyText }}</template>
    </div>
    <ul v-else class="divide-y divide-cx-border-soft" :class="loading ? 'opacity-60' : ''" :data-testid="`stage-${kind}-rows`">
      <li
        v-for="row in visibleRows"
        :key="row.name"
        class="rounded-cx-sm transition-colors"
        :class="highlighted === String(row.name) ? 'bg-cx-brand-soft/60 ring-2 ring-cx-brand/40' : ''"
      >
        <slot :row="row" />
      </li>
    </ul>

    <nav
      v-if="total > pageSize"
      class="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-cx-border-soft pt-3"
      :aria-label="`${title} pages`"
      :data-testid="`stage-${kind}-pager`"
    >
      <span class="text-xs text-cx-ink-2" aria-live="polite">{{ range }}</span>
      <div class="flex items-center gap-1">
        <button
          type="button"
          class="inline-flex min-h-9 items-center gap-1 rounded-cx-sm border border-cx-border px-2.5 text-xs font-semibold text-cx-ink-2 hover:bg-cx-well disabled:opacity-40"
          :disabled="state.page <= 0 || loading"
          :data-testid="`stage-${kind}-prev`"
          @click="setPage(state.page - 1)"
        >
          <CxIcon name="chevron-left" class="size-3.5" /> Previous
        </button>
        <span class="px-2 text-xs font-semibold text-cx-ink">{{ state.page + 1 }} / {{ pages }}</span>
        <button
          type="button"
          class="inline-flex min-h-9 items-center gap-1 rounded-cx-sm border border-cx-border px-2.5 text-xs font-semibold text-cx-ink-2 hover:bg-cx-well disabled:opacity-40"
          :disabled="state.page >= pages - 1 || loading"
          :data-testid="`stage-${kind}-next`"
          @click="setPage(state.page + 1)"
        >
          Next <CxIcon name="chevron-right" class="size-3.5" />
        </button>
      </div>
    </nav>
  </section>
</template>
