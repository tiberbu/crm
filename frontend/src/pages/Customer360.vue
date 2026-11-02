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
        <div class="relative mt-3 max-w-xl">
          <TextInput
            v-model="query"
            :placeholder="__('Search organization, deal or facility… (min 3 characters)')"
            icon="lucide-search"
            class="w-full"
          />
        </div>
      </header>

      <!-- Search results -->
      <div
        v-if="showResults && (searchResource.loading || searched)"
        class="mx-6 mt-4 max-w-2xl rounded-lg border border-outline-gray-2 bg-surface-white"
      >
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
              class="mb-1 flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm hover:bg-surface-gray-2"
              :aria-label="__('Open 360 for {0}', [facility.label])"
              @click="openFacility(facility)"
            >
              <span class="text-ink-gray-9">
                {{ facility.label }}
                <span class="text-ink-gray-5"> · {{ facility.mfl_code }}</span>
              </span>
              <Badge :label="__('Facility')" size="sm" theme="gray" variant="subtle" />
            </button>
          </div>
        </template>
        <div v-else-if="searched" class="px-4 py-6 text-sm text-ink-gray-5">
          {{ __('No matches for “{0}”.', [query.trim()]) }}
        </div>
      </div>

      <!-- 360 view -->
      <div class="flex-1 overflow-y-auto">
        <Customer360Sections v-if="data" :data="data" />
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
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, createResource, Spinner, TextInput } from 'frappe-ui'
import Customer360Sections from '@/components/Customer360/Customer360Sections.vue'

const router = useRouter()

const query = ref('')
const searched = ref(false)
const selected = ref(null)

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
const hasResults = computed(
	() =>
		(results.value.organizations?.length || 0) +
			(results.value.deals?.length || 0) +
			(results.value.facilities?.length || 0) >
		0,
)
const showResults = computed(() => !selected.value)

let debounceTimer = null
watch(query, (value) => {
	clearTimeout(debounceTimer)
	const trimmed = (value || '').trim()
	if (trimmed.length < 3) {
		searched.value = false
		searchResource.setData(null)
		return
	}
	debounceTimer = setTimeout(() => {
		searched.value = true
		searchResource.submit({ query: trimmed, limit: 10 })
	}, 600)
})

function selectReference(kind, name) {
	selected.value = { kind, name }
	dataResource.setData(null)
	dataResource.submit({ [kind]: name })
}

function openOrganization(name) {
	selectReference('organization', name)
}

function openDeal(name) {
	selectReference('deal', name)
}

// Facilities have no detail page of their own. A facility belongs to a customer,
// so open the parent organization's 360; without a parent, fall back to the
// facilities list page.
function openFacility(facility) {
	if (facility.organization) {
		openOrganization(facility.organization)
		return
	}
	router.push({ name: 'PrequalifiedFacilities' })
}
</script>
