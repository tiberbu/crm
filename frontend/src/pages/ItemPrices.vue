<template>
  <div class="flex h-full flex-col overflow-hidden">
    <div class="flex flex-wrap items-center justify-between gap-3 border-b border-outline-gray-2 px-5 py-3">
      <div>
        <h1 class="text-xl font-semibold text-ink-gray-9">{{ __('Negotiated Item Prices') }}</h1>
        <p class="mt-1 text-sm text-ink-gray-5">{{ __('Manage the price lists used by opt-in networks.') }}</p>
      </div>
      <Button variant="solid" size="sm" @click="showNewList = true">{{ __('New Price List') }}</Button>
    </div>

    <div class="flex flex-1 flex-col overflow-auto p-5">
      <div v-if="showNewList" class="mb-5 flex flex-wrap items-end gap-3 rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-4 dark:bg-surface-gray-2">
        <label class="flex min-w-64 flex-1 flex-col gap-1 text-xs font-medium text-ink-gray-6">
          {{ __('Price List Name') }}
          <input v-model="newListName" class="rounded border border-outline-gray-2 bg-surface-white px-3 py-1.5 text-sm text-ink-gray-9 dark:bg-surface-gray-3 dark:text-ink-gray-3" placeholder="Negotiated Year 6" />
        </label>
        <Button variant="solid" size="sm" :loading="creatingList" @click="createPriceList">{{ __('Create') }}</Button>
        <Button variant="subtle" size="sm" @click="showNewList = false">{{ __('Cancel') }}</Button>
      </div>

      <label class="mb-5 flex max-w-md flex-col gap-1 text-xs font-medium text-ink-gray-6">
        {{ __('Negotiated Price List') }}
        <select v-model="selectedPriceList" class="rounded border border-outline-gray-2 bg-surface-white px-3 py-2 text-sm text-ink-gray-9 dark:bg-surface-gray-3 dark:text-ink-gray-3">
          <option value="">{{ __('Select a price list') }}</option>
          <option v-for="priceList in priceLists" :key="priceList.value" :value="priceList.value">{{ priceList.label }}</option>
        </select>
      </label>

      <div v-if="selectedPriceList" class="mb-4 flex flex-wrap items-end gap-3 rounded-lg border border-outline-gray-2 p-4">
        <label class="flex min-w-56 flex-1 flex-col gap-1 text-xs font-medium text-ink-gray-6">
          {{ __('Item Code') }}
          <input v-model="newItemCode" list="sellable-items" class="rounded border border-outline-gray-2 bg-surface-white px-3 py-1.5 text-sm text-ink-gray-9 dark:bg-surface-gray-3 dark:text-ink-gray-3" :placeholder="__('Search or enter an item code')" />
          <datalist id="sellable-items">
            <option v-for="item in sellableItems" :key="item.value" :value="item.value">{{ item.item_name }}</option>
          </datalist>
        </label>
        <label class="flex w-40 flex-col gap-1 text-xs font-medium text-ink-gray-6">
          {{ __('Monthly Price (KES)') }}
          <input v-model.number="newRate" min="0" step="0.01" type="number" class="rounded border border-outline-gray-2 bg-surface-white px-3 py-1.5 text-sm text-ink-gray-9 dark:bg-surface-gray-3 dark:text-ink-gray-3" />
        </label>
        <Button variant="solid" size="sm" :loading="savingItem" @click="saveItemPrice">{{ __('Save Item Price') }}</Button>
      </div>

      <div v-if="pricesResource.loading" class="py-12 text-center text-sm text-ink-gray-5">{{ __('Loading prices…') }}</div>
      <div v-else-if="selectedPriceList && !itemPrices.length" class="py-12 text-center text-sm text-ink-gray-5">{{ __('No item prices are configured for this list.') }}</div>
      <div v-else-if="itemPrices.length" class="overflow-x-auto rounded-lg border border-outline-gray-2">
        <table class="w-full text-sm">
          <thead class="bg-surface-gray-1 text-xs uppercase tracking-wide text-ink-gray-5">
            <tr><th class="px-4 py-2.5 text-left font-medium">{{ __('Item') }}</th><th class="px-4 py-2.5 text-left font-medium">{{ __('UOM') }}</th><th class="px-4 py-2.5 text-right font-medium">{{ __('Monthly Price (KES)') }}</th><th class="px-4 py-2.5 text-right font-medium">{{ __('Actions') }}</th></tr>
          </thead>
          <tbody class="divide-y divide-outline-elevation-2">
            <tr v-for="itemPrice in itemPrices" :key="itemPrice.name">
              <td class="px-4 py-3"><div class="font-medium text-ink-gray-9">{{ itemPrice.item_name || itemPrice.item_code }}</div><div class="font-mono text-xs text-ink-gray-5">{{ itemPrice.item_code }}</div></td>
              <td class="px-4 py-3 text-ink-gray-6">{{ itemPrice.uom || 'Nos' }}</td>
              <td class="px-4 py-3 text-right"><input v-model.number="itemPrice.price_list_rate" min="0" step="0.01" type="number" class="w-36 rounded border border-outline-gray-2 bg-surface-white px-2 py-1 text-right text-sm text-ink-gray-9 dark:bg-surface-gray-3 dark:text-ink-gray-3" /></td>
              <td class="px-4 py-3 text-right"><Button size="sm" variant="subtle" :loading="savingItem === itemPrice.name" @click="saveItemPrice(itemPrice)">{{ __('Save') }}</Button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Button, createResource, toast } from 'frappe-ui'

const selectedPriceList = ref('')
const showNewList = ref(false)
const newListName = ref('')
const newItemCode = ref('')
const newRate = ref(null)
const creatingList = ref(false)
const savingItem = ref(false)

const priceListsResource = createResource({ url: 'crm.api.optin_admin.list_negotiated_price_lists', auto: true })
const priceLists = computed(() => priceListsResource.data ?? [])
const sellableItemsResource = createResource({ url: 'crm.api.optin_admin.list_sellable_items', auto: true })
const sellableItems = computed(() => sellableItemsResource.data ?? [])
const pricesResource = createResource({
  url: 'crm.api.optin_admin.list_item_prices',
  makeParams: () => ({ price_list: selectedPriceList.value }),
})
const itemPrices = computed(() => pricesResource.data ?? [])
const saveResource = createResource({ url: 'crm.api.optin_admin.save_item_price' })
const createListResource = createResource({ url: 'crm.api.optin_admin.create_negotiated_price_list' })

watch(selectedPriceList, (value) => {
  if (value) pricesResource.reload()
})

async function createPriceList() {
  if (!newListName.value.trim()) return
  creatingList.value = true
  try {
    const result = await createListResource.submit({ name: newListName.value.trim() })
    await priceListsResource.reload()
    selectedPriceList.value = result.name
    newListName.value = ''
    showNewList.value = false
    toast.success(__('Price list created'))
  } catch (error) {
    toast.error(error?.messages?.[0] ?? error?.message ?? __('Could not create price list'))
  } finally {
    creatingList.value = false
  }
}

async function saveItemPrice(itemPrice = null) {
  const itemCode = itemPrice?.item_code ?? newItemCode.value.trim()
  const rate = itemPrice?.price_list_rate ?? newRate.value
  if (!itemCode || rate === null || rate === '') return
  savingItem.value = itemPrice?.name ?? 'new'
  try {
    await saveResource.submit({ price_list: selectedPriceList.value, item_code: itemCode, rate })
    newItemCode.value = ''
    newRate.value = null
    await pricesResource.reload()
    toast.success(__('Item price saved'))
  } catch (error) {
    toast.error(error?.messages?.[0] ?? error?.message ?? __('Could not save item price'))
  } finally {
    savingItem.value = false
  }
}
</script>
