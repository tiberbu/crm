<template>
  <div class="fc-crud-section">
    <!-- Finance workbench header + primary action -->
    <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
      <div v-if="mode === 'list'" class="min-w-0">
        <p class="text-[10px] font-bold uppercase tracking-[0.08em] text-ink-red-6">
          Finance Workspace
        </p>
        <h2 class="mt-1 text-xl font-semibold tracking-tight text-ink-gray-9">
          {{ title || doctype }}
        </h2>
        <p class="mt-0.5 text-xs text-ink-gray-5">{{ subtitle }}</p>
      </div>
      <Breadcrumbs v-else :items="breadcrumbs" />
      <div v-if="mode === 'list'" class="flex flex-wrap items-center gap-2">
        <!-- Create-From (mapped-doc) actions — visible-but-disabled without create
             permission, matching the New gate. -->
        <Button
          v-for="flow in createFrom"
          :key="flow.key"
          variant="outline"
          theme="gray"
          :disabled="!canCreate"
          :title="!canCreate ? 'You do not have permission to create' : ''"
          @click="canCreate && goCreateFrom(flow)"
        >
          <template #prefix><FcIcon name="copy-plus" :size="15" /></template>
          {{ flow.label }}
        </Button>
        <Button variant="outline" theme="gray" @click="exportCsv">
          <template #prefix><FcIcon name="download" :size="15" /></template>
          Export CSV
        </Button>
        <Button variant="outline" theme="gray" @click="printAll">
          <template #prefix><FcIcon name="printer" :size="15" /></template>
          Print
        </Button>
        <Button
          v-if="!readOnly"
          variant="solid"
          theme="blue"
          :disabled="!canNew"
          :title="!canNew ? 'You do not have permission to create' : ''"
          @click="canNew && goNew()"
        >
          <template #prefix><FcIcon name="plus" :size="15" /></template>
          New
        </Button>
      </div>
    </div>

    <!-- LIST -->
    <template v-if="mode === 'list'">
      <div class="fc-card-frame mb-4">
        <div class="fc-toolbar-bar">
          <div class="flex flex-wrap items-center gap-2 flex-1">
            <slot name="filters" />
          </div>
        </div>

        <FinanceTable
          :columns="columns"
          :rows="rows"
          :loading="listLoading"
          :error="listError"
          :empty-label="emptyLabel"
          :page="page"
          :page-size="pageSize"
          collapsible
          @row-click="goView"
          @retry="refetch"
          @update:page="onPage"
        />
      </div>
    </template>

    <!-- VIEW -->
    <FinanceDetail
      v-else-if="mode === 'view'"
      :doctype="activeDoctype"
      :name="activeName"
      :read-only="readOnly"
      :allow-lifecycle-actions="allowLifecycleActions"
      @edit="goEdit"
      @mapped="onMappedFromDetail"
      @deleted="onMutated"
      @close="goList"
    />

    <!-- CREATE FROM: inline submitted-source picker -> mapped seed -->
    <CreateFromPicker
      v-else-if="mode === 'createFrom' && activeFlow"
      :flow="activeFlow"
      @mapped="onMapped"
      @created="onCreated"
      @close="goBackFromForm"
    />

    <!-- Use a mapped composer only for explicitly configured target doctypes;
         ordinary New and other mapped forms keep their existing behavior. -->
    <component
      :is="seedDoc ? mappedNewComponents[seedDoc.doctype] : newComponent"
      v-else-if="mode === 'new' && (seedDoc ? mappedNewComponents[seedDoc.doctype] : newComponent)"
      :seed="seedDoc"
      @saved="onSaved"
      @close="goBackFromForm"
    />

    <!-- NEW / EDIT via generic layout-driven form. `seed` pre-fills a new doc
         from a mapped source (Create From); ignored when editing (name set). -->
    <FinanceForm
      v-else-if="mode === 'new' || mode === 'edit'"
      :doctype="formDoctype"
      :name="mode === 'edit' ? activeName : null"
      :seed="mode === 'new' ? seedDoc : null"
      @saved="onSaved"
      @close="goBackFromForm"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { createResource, Button, Breadcrumbs } from 'frappe-ui'
import FinanceDetail from './FinanceDetail.vue'
import FinanceForm from './FinanceForm.vue'
import CreateFromPicker from './CreateFromPicker.vue'
import FcIcon from './FcIcon.vue'
import FinanceTable from '../FinanceTable.vue'
import { useBoot } from '../../composables/useBoot.js'
import { printUrl } from '../../constants/printFormats.js'
import { useCompanyContext } from '../../composables/useCompanyContext.js'

const props = defineProps({
  doctype: { type: String, required: true },
  title: { type: String, default: '' },
  subtitle: {
    type: String,
    default: 'Live records, permissions, and next actions.',
  },
  columns: { type: Array, default: () => [] },
  listResourceUrl: { type: String, required: true },
  listParams: { type: Function, default: () => ({}) },
  emptyLabel: { type: String, default: 'No records found.' },
  pageSize: { type: Number, default: 20 },
  // Optional custom component used for the "New" flow instead of FinanceForm.
  newComponent: { type: [Object, Function], default: null },
  // Optional "Create From" (mapped-doc) flows. Each entry renders a button that
  // opens an inline source picker, calls a whitelisted accounting mapper, and seeds
  // FinanceForm with the returned (unsaved) target doc for review + save. Shape:
  //   { key, label, sourceDoctype, sourceLabel, subtitleField?, mapMethod, targetDoctype }
  createFrom: { type: Array, default: () => [] },
  // Optional custom composer overrides for mapped target doctypes.
  mappedNewComponents: { type: Object, default: () => ({}) },
  // Finance may inspect quotations and orders without editing their fields.
  // Create-from flows remain independently enabled where the section exposes
  // a native downstream operation (for example Quote -> Sales Order).
  readOnly: { type: Boolean, default: false },
  allowLifecycleActions: { type: Boolean, default: false },
  // Optional role allow-list for the "New" gate. Defaults to the native-DocType
  // create roles. Sections whose create goes through a custom endpoint (e.g.
  // Payments -> create_customer_payment, AR-gated) pass their own list so the
  // button's enabled state matches the backend and never shows a false-positive.
  createRoles: {
    type: Array,
    default: () => [
      'Accounts Manager',
      'Accounts User',
    ],
  },
})

const { getRoles, isAdministrator } = useBoot()
const { company } = useCompanyContext()

const mode = ref('list')
const activeName = ref(null)
const activeDoctype = ref(props.doctype)
const page = ref(0)

// Create-From state: the active flow config while picking a source, and the
// mapped (unsaved) target doc used to seed FinanceForm once a source is chosen.
const activeFlow = ref(null)
const seedDoc = ref(null)
const formDoctype = ref(props.doctype)

const listResource = createResource({
  url: props.listResourceUrl,
  makeParams() {
    return {
      ...props.listParams(page.value, props.pageSize),
      page: page.value,
      page_size: props.pageSize,
    }
  },
  auto: false,
})

const rows = ref([])
const listLoading = ref(false)
const listError = ref(null)
let listRequest = 0

const roles = computed(() => getRoles())
const canCreate = computed(
  () =>
    isAdministrator() || props.createRoles.some((r) => roles.value.includes(r)),
)
const canNew = computed(() => canCreate.value && !props.readOnly)

// Breadcrumb trail: Title / Record / Edit — routeless buttons (standalone page).
const breadcrumbs = computed(() => {
  const trail = [{ label: props.title || props.doctype, onClick: goList }]
  if (mode.value === 'view' && activeName.value) {
    trail.push({ label: activeName.value, onClick: () => {} })
  } else if (mode.value === 'edit' && activeName.value) {
    trail.push({
      label: activeName.value,
      onClick: () => goView({ name: activeName.value }),
    })
    trail.push({ label: 'Edit', onClick: () => {} })
  } else if (mode.value === 'createFrom' && activeFlow.value) {
    trail.push({ label: activeFlow.value.label, onClick: () => {} })
  } else if (mode.value === 'new') {
    // Seeded new docs (Create From) keep the flow label in the trail for context.
    trail.push({
      label: seedDoc.value && activeFlow.value ? activeFlow.value.label : 'New',
      onClick: () => {},
    })
  }
  return trail
})

function timeAgo(dateStr) {
  if (!dateStr) return '—'
  const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000)
  if (diff < 60) return 'just now'
  if (diff < 3600) return Math.floor(diff / 60) + ' min ago'
  if (diff < 86400) return Math.floor(diff / 3600) + ' hr ago'
  if (diff < 86400 * 7) return Math.floor(diff / 86400) + ' d ago'
  return new Date(dateStr).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

function formatDate(dateStr) {
  if (!dateStr) return '—'
  const date = new Date(dateStr)
  if (Number.isNaN(date.getTime())) return String(dateStr)
  return date.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

function formatDateTime(dateStr) {
  if (!dateStr) return '—'
  const date = new Date(dateStr)
  if (Number.isNaN(date.getTime())) return String(dateStr)
  return date.toLocaleString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function ownerLabel(owner) {
  if (!owner) return '—'
  return String(owner).split('@')[0]
}

async function refetch() {
  const request = ++listRequest
  const requestedCompany = company.value
  if (!requestedCompany) {
    rows.value = []
    listLoading.value = false
    listError.value = null
    return
  }
  listLoading.value = true
  listError.value = null
  try {
    const result = await listResource.fetch()
    if (request !== listRequest || requestedCompany !== company.value) return
    rows.value = result || []
  } catch (error) {
    if (request === listRequest && requestedCompany === company.value) {
      listError.value = error
    }
  } finally {
    if (request === listRequest) listLoading.value = false
  }
}

watch(
  company,
  () => {
    page.value = 0
    rows.value = []
    if (!company.value) {
      // Fail closed while the accessible-company list initializes or resets.
      // Invalidate any earlier response so it cannot repopulate this section.
      listRequest += 1
      listLoading.value = false
      listError.value = null
      return
    }
    refetch()
  },
  { immediate: true },
)
function onPage(p) {
  page.value = p
  refetch()
}

function resetCreateFrom() {
  activeFlow.value = null
  seedDoc.value = null
  formDoctype.value = props.doctype
}

function goList() {
  mode.value = 'list'
  activeName.value = null
  activeDoctype.value = props.doctype
  resetCreateFrom()
}
function goView(row) {
  activeName.value = row.name
  activeDoctype.value = props.doctype
  mode.value = 'view'
}
function goNew() {
  activeName.value = null
  resetCreateFrom()
  mode.value = 'new'
}
function goEdit() {
  mode.value = 'edit'
}
function goBackFromForm() {
  // Editing an existing doc returns to its detail; anything else (new / seeded
  // new / create-from picker) returns to the list.
  if (activeName.value) {
    resetCreateFrom()
    mode.value = 'view'
  } else {
    goList()
  }
}

// Open the inline source picker for a Create-From flow.
function goCreateFrom(flow) {
  seedDoc.value = null
  activeFlow.value = flow
  mode.value = 'createFrom'
}
// A source was picked and mapped -> seed a new form with the target doc.
function onMapped(doc) {
  seedDoc.value = doc
  activeName.value = null
  formDoctype.value = activeFlow.value?.targetDoctype || doc?.doctype || props.doctype
  mode.value = 'new'
}

function onMappedFromDetail(doc) {
  seedDoc.value = doc
  activeName.value = null
  formDoctype.value = doc?.doctype || (props.doctype === 'Quotation' ? 'Sales Order' : 'Payment Entry')
  activeFlow.value = { label: `Create ${formDoctype.value}` }
  mode.value = 'new'
}

function onCreated(result) {
  activeName.value = result?.name || null
  activeDoctype.value = props.doctype
  resetCreateFrom()
  refetch()
  mode.value = activeName.value ? 'view' : 'list'
}

function printRow(row) {
  window.open(printUrl(props.doctype, row.name), '_blank')
}

function exportCsv() {
  if (!rows.value.length) return
  const cols = props.columns
  const header = cols.map((c) => c.label).join(',')
  const body = rows.value
    .map((row) =>
      cols
        .map((c) => {
          const v = row[c.key] ?? ''
          return typeof v === 'string' && v.includes(',') ? `"${v}"` : v
        })
        .join(','),
    )
    .join('\n')
  const blob = new Blob([header + '\n' + body], { type: 'text/csv' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${props.title || props.doctype}.csv`
  a.click()
  URL.revokeObjectURL(a.href)
}

function printAll() {
  if (!rows.value.length) return
  // Build an in-memory HTML table and trigger browser print
  const cols = props.columns
  const header = cols.map((c) => `<th>${c.label}</th>`).join('')
  const body = rows.value
    .map(
      (row) =>
        '<tr>' +
        cols.map((c) => `<td>${row[c.key] ?? '—'}</td>`).join('') +
        '</tr>',
    )
    .join('')
  const title = props.title || props.doctype
  const html = `<!DOCTYPE html><html><head><title>${title}</title>
    <style>
      body { font-family: sans-serif; font-size: 11px; margin: 16px; }
      h2 { margin-bottom: 12px; }
      table { width: 100%; border-collapse: collapse; }
      th { background: #8B0C22; color: #fff; padding: 6px 8px; text-align: left; font-size: 10px; text-transform: uppercase; }
      td { padding: 5px 8px; border-bottom: 1px solid #e5e7eb; }
      tr:nth-child(even) td { background: #f9fafb; }
    </style></head><body>
    <h2>${title}</h2>
    <table><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table>
    <script>window.onload=()=>{ window.print(); window.close() }</scr${'ipt'}>
    </body></html>`
  const win = window.open('', '_blank')
  win.document.write(html)
  win.document.close()
}

function onSaved(doc) {
  const savedDoctype = formDoctype.value
  activeName.value = doc?.name || activeName.value
  activeDoctype.value = savedDoctype
  activeFlow.value = null
  seedDoc.value = null
  refetch()
  mode.value = activeName.value ? 'view' : 'list'
}
function onMutated() {
  refetch()
  goList()
}

defineExpose({
  refetch,
  resetPage: () => {
    page.value = 0
  },
})
</script>
