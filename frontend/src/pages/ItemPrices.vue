<template>
  <div class="flex h-full flex-col overflow-hidden">
    <div
      class="flex flex-wrap items-center justify-between gap-3 border-b border-outline-gray-2 px-5 py-3"
    >
      <div>
        <h1 class="text-xl font-semibold text-ink-gray-9">
          {{ __('Item Catalogue') }}
        </h1>
        <p class="mt-1 text-sm text-ink-gray-5">
          {{ __('Manage sellable items and their negotiated price lists.') }}
        </p>
      </div>
      <div class="flex items-center gap-2">
        <Button variant="subtle" size="sm" @click="openNewItemForm">
          {{ __('New Catalogue Item') }}
        </Button>
        <Button variant="solid" size="sm" @click="openNewListForm">{{
          __('New Price List')
        }}</Button>
      </div>
    </div>

    <div class="flex flex-1 flex-col overflow-auto p-5">
      <div
        v-if="showNewList"
        class="mb-5 flex flex-wrap items-end gap-3 rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-4 dark:bg-surface-gray-2"
      >
        <label
          class="flex min-w-64 flex-1 flex-col gap-1 text-xs font-medium text-ink-gray-6"
        >
          {{ __('Price List Name') }}
          <input
            v-model="newListName"
            class="rounded border border-outline-gray-2 bg-surface-white px-3 py-1.5 text-sm text-ink-gray-9 dark:bg-surface-gray-3 dark:text-ink-gray-3"
            placeholder="Negotiated Year 6"
          />
        </label>
        <Button
          variant="solid"
          size="sm"
          :loading="creatingList"
          @click="createPriceList"
          >{{ __('Create') }}</Button
        >
        <Button variant="subtle" size="sm" @click="showNewList = false">{{
          __('Cancel')
        }}</Button>
      </div>

      <div
        v-if="showNewItem"
        class="mb-5 flex flex-wrap items-end gap-3 rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-4 dark:bg-surface-gray-2"
      >
        <label
          class="flex min-w-48 flex-1 flex-col gap-1 text-xs font-medium text-ink-gray-6"
        >
          {{ __('Item Code') }}
          <input
            v-model="newCatalogueItemCode"
            class="rounded border border-outline-gray-2 bg-surface-white px-3 py-1.5 text-sm text-ink-gray-9 dark:bg-surface-gray-3 dark:text-ink-gray-3"
            :placeholder="__('CV-HIMS-KEPH-6')"
          />
        </label>
        <label
          class="flex min-w-64 flex-1 flex-col gap-1 text-xs font-medium text-ink-gray-6"
        >
          {{ __('Item Name') }}
          <input
            v-model="newCatalogueItemName"
            class="rounded border border-outline-gray-2 bg-surface-white px-3 py-1.5 text-sm text-ink-gray-9 dark:bg-surface-gray-3 dark:text-ink-gray-3"
            :placeholder="__('CareverseHIMS — Level 6')"
          />
        </label>
        <label
          class="flex w-28 flex-col gap-1 text-xs font-medium text-ink-gray-6"
        >
          {{ __('UOM') }}
          <input
            v-model="newCatalogueItemUom"
            class="rounded border border-outline-gray-2 bg-surface-white px-3 py-1.5 text-sm text-ink-gray-9 dark:bg-surface-gray-3 dark:text-ink-gray-3"
            placeholder="Nos"
          />
        </label>
        <Button
          variant="solid"
          size="sm"
          :loading="creatingItem"
          @click="createCatalogueItem"
          >{{ __('Add item') }}</Button
        >
        <Button variant="subtle" size="sm" @click="showNewItem = false">
          {{ __('Cancel') }}
        </Button>
      </div>

      <div
        v-if="showDuplicateList"
        class="mb-5 flex flex-wrap items-end gap-3 rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-4 dark:bg-surface-gray-2"
      >
        <div class="min-w-64 flex-1 text-xs text-ink-gray-6">
          {{ __('Copying prices from') }}
          <span class="font-medium text-ink-gray-8">{{
            selectedPriceList
          }}</span>
        </div>
        <label
          class="flex min-w-64 flex-1 flex-col gap-1 text-xs font-medium text-ink-gray-6"
        >
          {{ __('New Price List Name') }}
          <input
            v-model="duplicateListName"
            class="rounded border border-outline-gray-2 bg-surface-white px-3 py-1.5 text-sm text-ink-gray-9 dark:bg-surface-gray-3 dark:text-ink-gray-3"
            :placeholder="__('Negotiated Year 6')"
          />
        </label>
        <Button
          variant="solid"
          size="sm"
          :loading="duplicatingList"
          @click="duplicatePriceList"
          >{{ __('Duplicate with prices') }}</Button
        >
        <Button variant="subtle" size="sm" @click="showDuplicateList = false">
          {{ __('Cancel') }}
        </Button>
      </div>

      <div class="mb-5 flex flex-wrap items-end gap-2">
        <label
          class="flex min-w-64 max-w-md flex-1 flex-col gap-1 text-xs font-medium text-ink-gray-6"
        >
          {{ __('Price List') }}
          <select
            v-model="selectedPriceList"
            class="rounded border border-outline-gray-2 bg-surface-white px-3 py-2 text-sm text-ink-gray-9 dark:bg-surface-gray-3 dark:text-ink-gray-3"
          >
            <option value="">{{ __('Select a price list') }}</option>
            <option
              v-for="priceList in priceLists"
              :key="priceList.value"
              :value="priceList.value"
            >
              {{ priceList.label }}
            </option>
          </select>
        </label>
        <Button
          v-if="selectedPriceList"
          variant="subtle"
          size="sm"
          @click="openDuplicateForm"
          >{{ __('Duplicate list') }}</Button
        >
      </div>

      <div
        v-if="selectedPriceListMeta"
        class="mb-4 rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-4 dark:bg-surface-gray-2"
      >
        <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <p class="text-xs uppercase tracking-wide text-ink-gray-5">
              {{ __('Facilities using this list') }}
            </p>
            <p class="mt-1 text-lg font-semibold text-ink-gray-9">
              {{ selectedPriceListMeta.facility_count ?? 0 }}
            </p>
          </div>
          <div>
            <p class="text-xs uppercase tracking-wide text-ink-gray-5">
              {{ __('Networks using this list') }}
            </p>
            <p class="mt-1 text-lg font-semibold text-ink-gray-9">
              {{ selectedPriceListMeta.network_count ?? 0 }}
            </p>
          </div>
          <div>
            <p class="text-xs uppercase tracking-wide text-ink-gray-5">
              {{ __('Created') }}
            </p>
            <p class="mt-1 text-sm text-ink-gray-8">
              {{ formatTimestamp(selectedPriceListMeta.creation) }}
            </p>
            <p class="text-xs text-ink-gray-5">
              {{ selectedPriceListMeta.owner || '—' }}
            </p>
          </div>
          <div>
            <p class="text-xs uppercase tracking-wide text-ink-gray-5">
              {{ __('Last edited') }}
            </p>
            <p class="mt-1 text-sm text-ink-gray-8">
              {{ formatTimestamp(selectedPriceListMeta.modified) }}
            </p>
            <p class="text-xs text-ink-gray-5">
              {{ selectedPriceListMeta.modified_by || '—' }}
            </p>
          </div>
        </div>
        <div
          v-if="selectedPriceListMeta.facility_count"
          class="mt-4 border-t border-outline-gray-2 pt-3"
        >
          <button
            type="button"
            class="flex w-full items-center justify-between gap-3 rounded-md py-1 text-left hover:bg-surface-gray-2"
            :aria-expanded="showAttachedFacilities"
            aria-controls="attached-facilities-list"
            @click="toggleAttachedFacilities"
          >
            <span class="flex items-center gap-2">
              <span
                class="text-xs font-semibold uppercase tracking-wide text-ink-gray-5"
              >
                {{ __('Attached facilities') }}
              </span>
              <span
                class="rounded-full bg-surface-gray-3 px-2 py-0.5 text-xs font-medium text-ink-gray-6 dark:bg-surface-gray-4"
              >
                {{ selectedPriceListMeta.facility_count }}
              </span>
            </span>
            <span class="text-xs font-medium text-ink-gray-6">
              {{ showAttachedFacilities ? __('Hide list') : __('Show list') }}
            </span>
          </button>
          <p class="mt-1 text-xs text-ink-gray-5">
            {{ __('Select a facility to preview its quote') }}
          </p>
          <div
            v-if="showAttachedFacilities"
            id="attached-facilities-list"
            class="mt-3"
          >
            <div
              v-if="priceListFacilitiesLoading && !priceListFacilities.length"
              class="py-3 text-center text-xs text-ink-gray-5"
            >
              {{ __('Loading attached facilities…') }}
            </div>
            <div v-else-if="priceListFacilities.length" class="space-y-3">
              <div class="flex flex-wrap gap-2">
                <Button
                  v-for="facility in priceListFacilities"
                  :key="`${facility.name}-${facility.network}`"
                  variant="subtle"
                  size="sm"
                  @click="viewSampleQuote(facility)"
                >
                  {{ facility.facility_name }}
                  <span class="ml-1 text-xs text-ink-gray-5"
                    >({{ facility.network }})</span
                  >
                </Button>
              </div>
              <div
                v-if="priceListFacilitiesHasMore"
                class="flex items-center justify-between gap-3"
              >
                <span class="text-xs text-ink-gray-5">
                  {{
                    __('Showing {0} of {1}', [
                      priceListFacilities.length,
                      priceListFacilitiesTotal,
                    ])
                  }}
                </span>
                <Button
                  variant="subtle"
                  size="sm"
                  :loading="priceListFacilitiesLoading"
                  @click="loadMorePriceListFacilities"
                >
                  {{ __('Load more') }}
                </Button>
              </div>
            </div>
            <p v-else class="py-3 text-center text-xs text-ink-gray-5">
              {{ __('No attached facilities found.') }}
            </p>
          </div>
        </div>
      </div>

      <div
        v-if="selectedPriceList"
        class="mb-4 rounded-lg border border-outline-gray-2 p-4"
      >
        <div class="mb-3">
          <h2 class="text-sm font-semibold text-ink-gray-9">
            {{ __('Quick price setup') }}
          </h2>
          <p class="mt-1 text-xs text-ink-gray-5">
            {{
              __(
                'Set negotiated prices for several items at once. Item and Item Price records are handled automatically.',
              )
            }}
          </p>
        </div>
        <div
          v-if="sellableItems.length"
          class="mb-4 overflow-x-auto rounded border border-outline-gray-2"
        >
          <table class="w-full text-sm">
            <thead
              class="bg-surface-gray-1 text-xs text-ink-gray-5 dark:bg-surface-gray-2"
            >
              <tr>
                <th class="px-3 py-2 text-left font-medium">
                  {{ __('Item') }}
                </th>
                <th class="px-3 py-2 text-left font-medium">{{ __('UOM') }}</th>
                <th class="px-3 py-2 text-right font-medium">
                  {{ __('Monthly Price (KES, excl. VAT)') }}
                </th>
              </tr>
            </thead>
            <tbody class="divide-y divide-outline-elevation-2">
              <tr v-for="item in sellableItems" :key="item.value">
                <td class="px-3 py-2">
                  <div class="font-medium text-ink-gray-9">
                    {{ item.item_name }}
                  </div>
                  <div class="font-mono text-xs text-ink-gray-5">
                    {{ item.value }}
                  </div>
                </td>
                <td class="px-3 py-2 text-ink-gray-6">
                  {{ item.stock_uom || 'Nos' }}
                </td>
                <td class="px-3 py-2 text-right">
                  <input
                    v-model.number="bulkRates[item.value]"
                    min="0"
                    step="0.01"
                    type="number"
                    class="w-40 rounded border border-outline-gray-2 bg-surface-white px-2 py-1 text-right text-sm text-ink-gray-9 dark:bg-surface-gray-3 dark:text-ink-gray-3"
                    :placeholder="__('Enter price')"
                  />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="mb-4 text-xs text-ink-gray-5">
          {{ __('Add a catalogue item to configure a negotiated price.') }}
        </div>
        <div class="flex justify-end">
          <Button
            variant="solid"
            size="sm"
            :disabled="!bulkPriceRows.length"
            :loading="savingAllItems"
            @click="saveAllItemPrices"
          >
            {{ __('Save all prices') }}
          </Button>
        </div>

        <div class="my-4 border-t border-outline-gray-2" />
        <div
          class="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-gray-5"
        >
          {{ __('Add one item') }}
        </div>
        <div class="flex flex-wrap items-end gap-3">
          <label
            class="flex min-w-56 flex-1 flex-col gap-1 text-xs font-medium text-ink-gray-6"
          >
            {{ __('Item Code') }}
            <input
              v-model="newItemCode"
              list="sellable-items"
              class="rounded border border-outline-gray-2 bg-surface-white px-3 py-1.5 text-sm text-ink-gray-9 dark:bg-surface-gray-3 dark:text-ink-gray-3"
              :placeholder="__('Search or enter an item code')"
            />
            <datalist id="sellable-items">
              <option
                v-for="item in sellableItems"
                :key="item.value"
                :value="item.value"
              >
                {{ item.item_name }}
              </option>
            </datalist>
          </label>
          <label
            class="flex w-40 flex-col gap-1 text-xs font-medium text-ink-gray-6"
          >
            {{ __('Monthly Price (KES)') }}
            <input
              v-model.number="newRate"
              min="0"
              step="0.01"
              type="number"
              class="rounded border border-outline-gray-2 bg-surface-white px-3 py-1.5 text-sm text-ink-gray-9 dark:bg-surface-gray-3 dark:text-ink-gray-3"
            />
          </label>
          <Button
            variant="solid"
            size="sm"
            :loading="savingItem"
            @click="saveItemPrice"
            >{{ __('Save Item Price') }}</Button
          >
        </div>
      </div>

      <div
        v-if="pricesResource.loading"
        class="py-12 text-center text-sm text-ink-gray-5"
      >
        {{ __('Loading prices…') }}
      </div>
      <div
        v-else-if="selectedPriceList && !itemPrices.length"
        class="py-12 text-center text-sm text-ink-gray-5"
      >
        {{ __('No item prices are configured for this list.') }}
      </div>
      <div
        v-else-if="itemPrices.length"
        class="overflow-x-auto rounded-lg border border-outline-gray-2"
      >
        <table class="w-full text-sm">
          <thead
            class="bg-surface-gray-1 text-xs uppercase tracking-wide text-ink-gray-5"
          >
            <tr>
              <th class="px-4 py-2.5 text-left font-medium">
                {{ __('Item') }}
              </th>
              <th class="px-4 py-2.5 text-left font-medium">{{ __('UOM') }}</th>
              <th class="px-4 py-2.5 text-right font-medium">
                {{ __('Monthly Price (KES)') }}
              </th>
              <th class="px-4 py-2.5 text-right font-medium">
                {{ __('Actions') }}
              </th>
            </tr>
          </thead>
          <tbody class="divide-y divide-outline-elevation-2">
            <tr v-for="itemPrice in itemPrices" :key="itemPrice.name">
              <td class="px-4 py-3">
                <div class="font-medium text-ink-gray-9">
                  {{ itemPrice.item_name || itemPrice.item_code }}
                </div>
                <div class="font-mono text-xs text-ink-gray-5">
                  {{ itemPrice.item_code }}
                </div>
              </td>
              <td class="px-4 py-3 text-ink-gray-6">
                {{ itemPrice.uom || 'Nos' }}
              </td>
              <td class="px-4 py-3 text-right">
                <input
                  v-model.number="itemPrice.price_list_rate"
                  min="0"
                  step="0.01"
                  type="number"
                  class="w-36 rounded border border-outline-gray-2 bg-surface-white px-2 py-1 text-right text-sm text-ink-gray-9 dark:bg-surface-gray-3 dark:text-ink-gray-3"
                />
              </td>
              <td class="px-4 py-3 text-right">
                <Button
                  size="sm"
                  variant="subtle"
                  :loading="savingItem === itemPrice.name"
                  @click="saveItemPrice(itemPrice)"
                  >{{ __('Save') }}</Button
                >
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <Dialog
      v-model="showSampleQuote"
      :options="{ title: __('Sample quotation'), size: 'lg' }"
    >
      <template #body-content>
        <div
          v-if="sampleQuoteLoading"
          class="py-10 text-center text-sm text-ink-gray-5"
        >
          {{ __('Loading sample quotation…') }}
        </div>
        <div v-else-if="sampleQuote" class="space-y-4">
          <div>
            <p class="text-lg font-semibold text-ink-gray-9">
              {{ sampleQuote.facility }}
            </p>
            <p class="text-sm text-ink-gray-5">
              {{ sampleQuote.organization }} · {{ sampleQuote.keph_level }} ·
              {{ sampleQuote.network }}
            </p>
          </div>
          <div
            class="rounded-lg bg-surface-gray-1 p-3 text-sm dark:bg-surface-gray-2"
          >
            <div class="flex justify-between gap-4">
              <span class="text-ink-gray-5">{{ __('Price list') }}</span>
              <span class="font-medium text-ink-gray-9">{{
                sampleQuote.price_list
              }}</span>
            </div>
            <div class="mt-1 flex justify-between gap-4">
              <span class="text-ink-gray-5">{{ __('Item') }}</span>
              <span class="text-right text-ink-gray-8">{{
                sampleQuote.item_name
              }}</span>
            </div>
          </div>
          <div class="grid gap-3 sm:grid-cols-2">
            <div class="rounded-lg border border-outline-gray-2 p-3">
              <p class="text-xs uppercase tracking-wide text-ink-gray-5">
                {{ __('Monthly') }}
              </p>
              <p class="mt-1 text-base font-semibold text-ink-gray-9">
                {{ formatKes(sampleQuote.monthly_gross) }}
              </p>
              <p class="text-xs text-ink-gray-5">
                {{ formatKes(sampleQuote.monthly_net) }} {{ __('excl. VAT') }} ·
                {{ sampleQuote.vat_label }}
              </p>
            </div>
            <div class="rounded-lg border border-outline-gray-2 p-3">
              <p class="text-xs uppercase tracking-wide text-ink-gray-5">
                {{ __('Annual') }}
              </p>
              <p class="mt-1 text-base font-semibold text-ink-gray-9">
                {{ formatKes(sampleQuote.annual_gross) }}
              </p>
              <p class="text-xs text-ink-gray-5">
                {{ formatKes(sampleQuote.annual_net) }} {{ __('excl. VAT') }} ·
                {{ sampleQuote.vat_label }}
              </p>
            </div>
          </div>
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Button, createResource, Dialog, toast } from 'frappe-ui'

const selectedPriceList = ref('')
const showNewList = ref(false)
const showDuplicateList = ref(false)
const showNewItem = ref(false)
const newListName = ref('')
const duplicateListName = ref('')
const newCatalogueItemCode = ref('')
const newCatalogueItemName = ref('')
const newCatalogueItemUom = ref('Nos')
const newItemCode = ref('')
const newRate = ref(null)
const creatingList = ref(false)
const duplicatingList = ref(false)
const creatingItem = ref(false)
const savingItem = ref(false)
const savingAllItems = ref(false)
const bulkRates = ref({})
const showSampleQuote = ref(false)
const sampleQuote = ref(null)
const sampleQuoteLoading = ref(false)
const showAttachedFacilities = ref(false)
const priceListFacilities = ref([])
const priceListFacilitiesTotal = ref(0)
const priceListFacilitiesPage = ref(0)
const priceListFacilitiesLoading = ref(false)
const priceListFacilitiesPageSize = 50
let priceListFacilitiesRequestId = 0

const priceListsResource = createResource({
  url: 'crm.api.optin_admin.list_negotiated_price_lists',
  auto: true,
})
const priceLists = computed(() => priceListsResource.data ?? [])
const selectedPriceListMeta = computed(
  () =>
    priceLists.value.find(
      (priceList) => priceList.value === selectedPriceList.value,
    ) ?? null,
)
const sellableItemsResource = createResource({
  url: 'crm.api.optin_admin.list_sellable_items',
  auto: true,
})
const sellableItems = computed(() => sellableItemsResource.data ?? [])
const pricesResource = createResource({
  url: 'crm.api.optin_admin.list_item_prices',
  makeParams: () => ({ price_list: selectedPriceList.value }),
})
const itemPrices = computed(() => pricesResource.data ?? [])
const saveResource = createResource({
  url: 'crm.api.optin_admin.save_item_price',
})
const createListResource = createResource({
  url: 'crm.api.optin_admin.create_negotiated_price_list',
})
const createItemResource = createResource({
  url: 'crm.api.optin_admin.create_sellable_item',
})
const bulkSaveResource = createResource({
  url: 'crm.api.optin_admin.save_item_prices',
})
const priceListFacilitiesResource = createResource({
  url: 'crm.api.optin_admin.list_price_list_facilities',
})
const priceListFacilitiesHasMore = computed(
  () => priceListFacilities.value.length < priceListFacilitiesTotal.value,
)
const sampleQuoteResource = createResource({
  url: 'crm.api.optin_admin.get_facility_sample_quote',
})
const duplicateListResource = createResource({
  url: 'crm.api.optin_admin.duplicate_negotiated_price_list',
})

const bulkPriceRows = computed(() =>
  sellableItems.value
    .map((item) => ({
      item_code: item.value,
      rate: bulkRates.value[item.value],
    }))
    .filter(
      (row) => row.rate !== null && row.rate !== undefined && row.rate !== '',
    ),
)

watch(
  [itemPrices, selectedPriceList],
  ([prices, selected], previous) => {
    if (selected !== previous?.[1]) {
      bulkRates.value = {}
      return
    }
    const configured = Object.fromEntries(
      prices.map((item) => [item.item_code, item.price_list_rate]),
    )
    bulkRates.value = { ...configured, ...bulkRates.value }
  },
  { immediate: true },
)

watch(selectedPriceList, (value) => {
  resetPriceListFacilities()
  if (!value) return
  pricesResource.reload()
  if (showAttachedFacilities.value) loadPriceListFacilities()
})

function resetPriceListFacilities() {
  priceListFacilitiesRequestId += 1
  priceListFacilities.value = []
  priceListFacilitiesTotal.value = 0
  priceListFacilitiesPage.value = 0
  priceListFacilitiesLoading.value = false
}

async function loadPriceListFacilities(append = false) {
  const value = selectedPriceList.value
  if (!value || priceListFacilitiesLoading.value) return
  if (append && !priceListFacilitiesHasMore.value) return

  const requestId = ++priceListFacilitiesRequestId
  const page = append ? priceListFacilitiesPage.value + 1 : 1
  priceListFacilitiesLoading.value = true
  try {
    const response = await priceListFacilitiesResource.submit({
      price_list: value,
      page,
      page_length: priceListFacilitiesPageSize,
    })
    if (
      requestId !== priceListFacilitiesRequestId ||
      value !== selectedPriceList.value
    )
      return
    const rows = Array.isArray(response) ? response : response?.rows ?? []
    priceListFacilities.value = append
      ? [...priceListFacilities.value, ...rows]
      : rows
    priceListFacilitiesTotal.value = Array.isArray(response)
      ? rows.length
      : response?.total ?? rows.length
    priceListFacilitiesPage.value = Array.isArray(response)
      ? 1
      : response?.page ?? page
  } catch (error) {
    if (requestId !== priceListFacilitiesRequestId) return
    toast.error(
      error?.messages?.[0] ??
        error?.message ??
        __('Could not load attached facilities'),
    )
  } finally {
    if (requestId === priceListFacilitiesRequestId)
      priceListFacilitiesLoading.value = false
  }
}

function toggleAttachedFacilities() {
  showAttachedFacilities.value = !showAttachedFacilities.value
  if (showAttachedFacilities.value && !priceListFacilitiesPage.value)
    loadPriceListFacilities()
}

function loadMorePriceListFacilities() {
  loadPriceListFacilities(true)
}

function formatTimestamp(value) {
  if (!value) return '—'
  return new Date(value).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

function formatKes(value) {
  return `KES ${Number(value || 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

async function viewSampleQuote(facility) {
  sampleQuoteLoading.value = true
  sampleQuote.value = null
  showSampleQuote.value = true
  try {
    sampleQuote.value = await sampleQuoteResource.submit({
      facility: facility.name,
      network: facility.network,
      price_list: selectedPriceList.value,
    })
  } catch (error) {
    showSampleQuote.value = false
    toast.error(
      error?.messages?.[0] ??
        error?.message ??
        __('Could not load sample quote'),
    )
  } finally {
    sampleQuoteLoading.value = false
  }
}

function openNewListForm() {
  showDuplicateList.value = false
  showNewItem.value = false
  showNewList.value = true
}

function openNewItemForm() {
  showNewList.value = false
  showDuplicateList.value = false
  showNewItem.value = true
}

async function createPriceList() {
  if (!newListName.value.trim()) return
  creatingList.value = true
  try {
    const result = await createListResource.submit({
      name: newListName.value.trim(),
    })
    await priceListsResource.reload()
    selectedPriceList.value = result.name
    newListName.value = ''
    showNewList.value = false
    toast.success(__('Price list created'))
  } catch (error) {
    toast.error(
      error?.messages?.[0] ??
        error?.message ??
        __('Could not create price list'),
    )
  } finally {
    creatingList.value = false
  }
}

async function createCatalogueItem() {
  const itemCode = newCatalogueItemCode.value.trim()
  const itemName = newCatalogueItemName.value.trim()
  if (!itemCode || !itemName) return
  creatingItem.value = true
  try {
    const result = await createItemResource.submit({
      item_code: itemCode,
      item_name: itemName,
      stock_uom: newCatalogueItemUom.value.trim() || 'Nos',
    })
    await sellableItemsResource.reload()
    newItemCode.value = result.value
    newCatalogueItemCode.value = ''
    newCatalogueItemName.value = ''
    newCatalogueItemUom.value = 'Nos'
    showNewItem.value = false
    toast.success(__('Catalogue item added'))
  } catch (error) {
    toast.error(
      error?.messages?.[0] ??
        error?.message ??
        __('Could not add catalogue item'),
    )
  } finally {
    creatingItem.value = false
  }
}

function openDuplicateForm() {
  if (!selectedPriceList.value) return
  duplicateListName.value = `${selectedPriceList.value} Copy`
  showNewList.value = false
  showDuplicateList.value = true
}

async function duplicatePriceList() {
  const name = duplicateListName.value.trim()
  if (!selectedPriceList.value || !name) return
  duplicatingList.value = true
  try {
    const result = await duplicateListResource.submit({
      source: selectedPriceList.value,
      name,
    })
    await priceListsResource.reload()
    selectedPriceList.value = result.name
    duplicateListName.value = ''
    showDuplicateList.value = false
    toast.success(
      __('Price list duplicated with {0} items', [result.copied ?? 0]),
    )
  } catch (error) {
    toast.error(
      error?.messages?.[0] ??
        error?.message ??
        __('Could not duplicate price list'),
    )
  } finally {
    duplicatingList.value = false
  }
}

async function saveItemPrice(itemPrice = null) {
  const itemCode = itemPrice?.item_code ?? newItemCode.value.trim()
  const rate = itemPrice?.price_list_rate ?? newRate.value
  if (!itemCode || rate === null || rate === '') return
  savingItem.value = itemPrice?.name ?? 'new'
  try {
    await saveResource.submit({
      price_list: selectedPriceList.value,
      item_code: itemCode,
      rate,
    })
    newItemCode.value = ''
    newRate.value = null
    await pricesResource.reload()
    toast.success(__('Item price saved'))
  } catch (error) {
    toast.error(
      error?.messages?.[0] ?? error?.message ?? __('Could not save item price'),
    )
  } finally {
    savingItem.value = false
  }
}

async function saveAllItemPrices() {
  if (!selectedPriceList.value || !bulkPriceRows.value.length) return
  savingAllItems.value = true
  try {
    const result = await bulkSaveResource.submit({
      price_list: selectedPriceList.value,
      prices: JSON.stringify(bulkPriceRows.value),
    })
    await pricesResource.reload()
    toast.success(
      __('Saved {0} item prices', [result.saved ?? bulkPriceRows.value.length]),
    )
  } catch (error) {
    toast.error(
      error?.messages?.[0] ??
        error?.message ??
        __('Could not save item prices'),
    )
  } finally {
    savingAllItems.value = false
  }
}
</script>
