<template>
  <div class="flex h-full overflow-hidden bg-surface-gray-1">
    <div class="flex w-full flex-col">
      <header class="border-b border-outline-gray-2 bg-surface-white px-6 py-4">
        <h1 class="text-xl font-semibold text-ink-gray-9">{{ __('Customer 360') }}</h1>
        <p class="mt-1 text-sm text-ink-gray-5">
          {{
            __('Trace any customer: partner origin, package payment, orders, site provisioning and billing in one view.')
          }}
        </p>
        <div ref="searchBox" class="relative mt-3 max-w-xl" @keydown.esc="onEscape">
          <TextInput
            v-model="query"
            :placeholder="__('Search organization, deal, facility or Facility ID… (min 3 characters)')"
            class="w-full"
            data-testid="c360-search"
            @focus="reopenResults"
            @click="reopenResults"
          >
            <template #prefix>
              <LucideSearch class="size-4 text-ink-gray-5" />
            </template>
            <template v-if="query" #suffix>
              <button
                type="button"
                class="flex items-center rounded text-ink-gray-5 hover:text-ink-gray-8 focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
                :aria-label="__('Clear search')"
                :title="__('Clear search')"
                data-testid="c360-search-clear"
                @click="clearSearch"
              >
                <LucideX class="size-4" />
              </button>
            </template>
          </TextInput>

          <!-- Search results dropdown -->
          <div
            v-if="resultsOpen && (searchResource.loading || searched)"
            class="absolute left-0 right-0 top-full z-20 mt-1 max-h-[60vh] overflow-y-auto rounded-lg border border-outline-gray-2 bg-surface-white shadow-lg"
            role="dialog"
            :aria-label="__('Search results')"
            data-testid="c360-results"
          >
            <div
              class="sticky top-0 flex items-center justify-between border-b border-outline-gray-2 bg-surface-white px-4 py-2"
            >
              <span class="text-xs text-ink-gray-5">
                {{ searchResource.loading ? __('Searching…') : resultCountLabel }}
              </span>
              <button
                type="button"
                class="flex items-center rounded p-1 text-ink-gray-5 hover:bg-surface-gray-2 hover:text-ink-gray-8"
                :aria-label="__('Close results')"
                :title="__('Close results')"
                data-testid="c360-results-close"
                @click="closeResults"
              >
                <LucideX class="size-4" />
              </button>
            </div>
            <div
              v-if="searchResource.loading"
              class="flex items-center gap-2 px-4 py-6 text-sm text-ink-gray-5"
            >
              <Spinner size="sm" />
              {{ __('Searching…') }}
            </div>
            <template v-else-if="hasResults">
              <div
                v-if="results.organizations?.length"
                class="border-b border-outline-gray-2 px-4 py-3"
              >
                <h2 class="mb-2 text-xs font-medium text-ink-gray-5">{{
                  __('Organizations')
                }}</h2>
                <button
                  v-for="org in results.organizations"
                  :key="'org-' + org.name"
                  class="mb-1 flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm hover:bg-surface-gray-2"
                  :aria-label="__('Open 360 for {0}', [org.label])"
                  @click="openOrganization(org.name)"
                >
                  <span class="text-ink-gray-9">{{ org.label }}</span>
                  <Badge
                    :label="__('Organization')"
                    size="sm"
                    theme="gray"
                    variant="subtle"
                  />
                </button>
              </div>
              <div
                v-if="results.deals?.length"
                class="border-b border-outline-gray-2 px-4 py-3"
              >
                <h2 class="mb-2 text-xs font-medium text-ink-gray-5">{{ __('Deals') }}</h2>
                <button
                  v-for="deal in results.deals"
                  :key="'deal-' + deal.name"
                  class="mb-1 flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm hover:bg-surface-gray-2"
                  :aria-label="__('Open 360 for {0}', [deal.name])"
                  @click="openDeal(deal.name)"
                >
                  <span class="text-ink-gray-9">
                    {{ deal.name }}
                    <span class="text-ink-gray-5"> · {{ deal.organization }}</span>
                  </span>
                  <Badge
                    :label="deal.status || __('Deal')"
                    size="sm"
                    theme="blue"
                    variant="subtle"
                  />
                </button>
              </div>
              <div v-if="results.facilities?.length" class="px-4 py-3">
                <h2 class="mb-2 text-xs font-medium text-ink-gray-5">{{
                  __('Facilities')
                }}</h2>
                <button
                  v-for="facility in results.facilities"
                  :key="'fac-' + facility.name"
                  class="mb-1 flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-surface-gray-2"
                  :aria-label="__('Open 360 for {0}', [facility.label])"
                  data-testid="c360-facility-result"
                  @click="openFacility(facility.name)"
                >
                  <span class="min-w-0">
                    <span class="block truncate text-ink-gray-9">{{ facility.label }}</span>
                    <span class="block truncate text-xs text-ink-gray-5">
                      {{ __('Facility ID') }}: {{ facilityId(facility) || __('Not linked yet') }}
                      · {{ __('MFL') }}: {{ facility.mfl_code || '—' }}
                    </span>
                  </span>
                  <Badge :label="__('Facility')" size="sm" theme="gray" variant="subtle" />
                </button>
              </div>
            </template>
            <div v-else-if="searched" class="px-4 py-6 text-sm text-ink-gray-5">
              {{ __('No matches for “{0}”.', [query.trim()]) }}
            </div>
          </div>
        </div>
      </header>

      <!-- Facility scope bar -->
      <div
        v-if="scopeFacility"
        class="flex flex-col gap-3 border-b border-outline-gray-2 bg-surface-white px-6 py-3 sm:flex-row sm:items-center sm:justify-between"
        data-testid="c360-scope-bar"
      >
        <div class="min-w-0">
          <p class="truncate text-sm font-medium text-ink-gray-9" data-testid="c360-scope-facility">
            {{ scopeFacility.facility_name }}
          </p>
          <p class="text-xs text-ink-gray-5">
            {{ __('Facility ID') }}:
            <span class="tabular-nums">{{ facilityId(scopeFacility) || __('Not linked yet') }}</span>
            · {{ __('MFL') }}: <span class="tabular-nums">{{ scopeFacility.mfl_code || '—' }}</span>
            <template v-if="data?.organization">
              · {{ __('Owner') }}: {{ data.organization.organization_name }}
            </template>
          </p>
        </div>
        <div class="flex flex-col items-start gap-1 sm:items-end">
          <TabButtons
            v-if="canWiden"
            :model-value="scopeMode"
            :options="scopeOptions"
            data-testid="c360-scope-toggle"
            @update:model-value="setScope"
          />
          <p v-else class="text-xs text-ink-gray-5">
            {{ __('No owner organization on file') }}
          </p>
        </div>
      </div>
      <div
        v-if="hiddenRecords > 0"
        class="border-b border-outline-gray-2 bg-surface-white px-6 py-2 text-xs text-ink-gray-5"
        data-testid="c360-unattributed-note"
      >
        {{
          hiddenRecords === 1
            ? __("1 record isn't tied to one facility.")
            : __("{0} records aren't tied to one facility.", [hiddenRecords])
        }}
        <button
          type="button"
          class="text-ink-gray-8 underline hover:text-ink-gray-9"
          @click="setScope('organization')"
        >
          {{ __('Show all facilities') }}
        </button>
      </div>

      <!-- 360 view -->
      <div class="flex-1 overflow-y-auto">
        <div
          v-if="dataResource.error && !dataResource.loading"
          class="flex h-full items-center justify-center px-6 text-sm text-ink-gray-5"
        >
          {{ __('This record could not be opened.') }}
        </div>
        <div v-else-if="data" :class="{ 'opacity-60': dataResource.loading }">
          <Customer360Sections :data="data" />
        </div>
        <div
          v-else-if="selected"
          class="flex h-full items-center justify-center gap-2 text-sm text-ink-gray-5"
        >
          <Spinner size="sm" />
          {{ __('Loading customer 360…') }}
        </div>
        <div v-else class="flex h-full flex-col items-center justify-center gap-1">
          <p class="text-sm font-medium text-ink-gray-7">{{
            __('Search for a customer')
          }}</p>
          <p class="text-xs text-ink-gray-4">
            {{
              __(
                'Find an organization, a deal or a facility to open its 360 view.',
              )
            }}
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Badge, createResource, Spinner, TabButtons, TextInput } from 'frappe-ui'
import LucideSearch from '~icons/lucide/search'
import LucideX from '~icons/lucide/x'
import Customer360Sections from '@/components/Customer360/Customer360Sections.vue'
import { facilityId } from '@/utils/facilityId.js'
import {
	paramsForSelection,
	queryForSelection,
	selectionFromQuery,
	unattributedCount,
} from '@/utils/customer360.js'

const route = useRoute()
const router = useRouter()

const query = ref('')
const searched = ref(false)
const resultsOpen = ref(false)
const searchBox = ref(null)

// The selection lives in the URL (?organization= · ?deal= · ?facility=&scope=).
const selected = computed(() => selectionFromQuery(route.query))

const searchResource = createResource({
	url: 'crm.api.customer_360.search_customer_360',
	params: { query: '', limit: 10 },
})
const dataResource = createResource({
	url: 'crm.api.customer_360.get_customer_360',
	params: {},
})

const data = computed(() => dataResource.data)
const results = computed(
	() =>
		searchResource.data || { organizations: [], deals: [], facilities: [] },
)
const resultCount = computed(
	() =>
		(results.value.organizations?.length || 0) +
		(results.value.deals?.length || 0) +
		(results.value.facilities?.length || 0),
)
const hasResults = computed(() => resultCount.value > 0)
const resultCountLabel = computed(() =>
	resultCount.value === 1 ? __('1 result') : __('{0} results', [resultCount.value]),
)

const scopeFacility = computed(() => data.value?.scope?.facility || null)
const scopeMode = computed(() => data.value?.scope?.mode || 'organization')
const canWiden = computed(() => Boolean(data.value?.scope?.can_widen))
const hiddenRecords = computed(() => unattributedCount(data.value?.scope))
const scopeOptions = computed(() => [
	{ value: 'facility', label: __('This facility') },
	{ value: 'organization', label: __('All facilities') },
])

let debounceTimer = null
watch(query, (value) => {
	clearTimeout(debounceTimer)
	const trimmed = (value || '').trim()
	if (trimmed.length < 3) {
		searched.value = false
		resultsOpen.value = false
		searchResource.setData(null)
		return
	}
	debounceTimer = setTimeout(() => {
		searched.value = true
		resultsOpen.value = true
		searchResource.submit({ query: trimmed, limit: 10 })
	}, 600)
})

// Load the 360 whenever the selection in the URL changes (search pick, scope toggle,
// back/forward, a shared link).
watch(
	selected,
	(selection, previous) => {
		const params = paramsForSelection(selection)
		if (!params) {
			dataResource.setData(null)
			return
		}
		// Switching scope on the same facility keeps the current view visible while loading.
		const sameFacility =
			previous?.kind === 'facility' &&
			selection.kind === 'facility' &&
			previous.name === selection.name
		if (!sameFacility) dataResource.setData(null)
		dataResource.submit(params)
	},
	{ immediate: true },
)

function select(selection) {
	resultsOpen.value = false
	router.push({ name: 'Customer360', query: queryForSelection(selection) })
}

function openOrganization(name) {
	select({ kind: 'organization', name })
}

function openDeal(name) {
	select({ kind: 'deal', name })
}

// A facility opens in its own scope; the owner's full picture is one toggle away.
function openFacility(name) {
	select({ kind: 'facility', name, scope: 'facility' })
}

function setScope(scope) {
	const selection = selected.value
	if (selection?.kind !== 'facility' || selection.scope === scope) return
	router.replace({
		name: 'Customer360',
		query: queryForSelection({ ...selection, scope }),
	})
}

// Clearing empties the search and closes its results; the open 360 stays.
function clearSearch() {
	clearTimeout(debounceTimer)
	query.value = ''
	searched.value = false
	resultsOpen.value = false
	searchResource.setData(null)
	searchBox.value?.querySelector('input')?.focus()
}

function closeResults() {
	resultsOpen.value = false
}

function reopenResults() {
	if (searched.value && (query.value || '').trim().length >= 3) {
		resultsOpen.value = true
	}
}

function onEscape() {
	if (resultsOpen.value) closeResults()
	else if (query.value) clearSearch()
}

function onPointerDown(event) {
	if (resultsOpen.value && searchBox.value && !searchBox.value.contains(event.target)) {
		closeResults()
	}
}

onMounted(() => document.addEventListener('pointerdown', onPointerDown))
onBeforeUnmount(() => {
	document.removeEventListener('pointerdown', onPointerDown)
	clearTimeout(debounceTimer)
})
</script>
