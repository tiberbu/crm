<template>
  <Dialog
    v-model="show"
    :options="{ title: title, size: '2xl' }"
    data-testid="package-dialog"
  >
    <template #body-content>
      <form class="flex flex-col gap-4" @submit.prevent="submit">
        <div class="grid gap-4 sm:grid-cols-2">
          <FormControl
            v-model="form.plan"
            type="select"
            :label="__('Plan')"
            :options="planOptions"
            :disabled="locked"
            data-testid="package-plan"
          />
          <FormControl
            v-model="form.display_name"
            type="text"
            :label="__('Name facilities see')"
            :placeholder="__('e.g. Growth')"
            data-testid="package-name"
          />
        </div>
        <p
          v-if="locked"
          class="rounded-lg bg-surface-amber-1 px-3 py-2 text-sm text-ink-amber-3"
          data-testid="package-locked"
        >
          {{
            __(
              'On {0} orders, so its item, plan and tokens are fixed. Duplicate it to sell a different package.',
              [form.sold_orders],
            )
          }}
        </p>
        <div class="grid gap-4 sm:grid-cols-3">
          <FormControl
            v-if="form.plan === 'Flex'"
            v-model="form.token_quantity"
            type="number"
            :label="__('Tokens')"
            :disabled="locked"
            min="1"
            data-testid="package-tokens"
          />
          <FormControl
            v-if="form.plan !== 'Custom'"
            v-model="form.price"
            type="number"
            :label="__('Price ({0}, excl. VAT)', [currency])"
            min="0"
            step="0.01"
            data-testid="package-price"
          />
          <FormControl
            v-model="form.billing_period"
            type="select"
            :label="__('Billing period')"
            :options="periods.map((p) => ({ label: __(p), value: p }))"
            data-testid="package-period"
          />
        </div>
        <p
          v-if="form.plan === 'Flex' && rate"
          class="-mt-2 text-sm text-ink-gray-5"
        >
          {{ __('{0} per token', [rate]) }}
        </p>
        <p v-if="form.plan === 'Custom'" class="text-sm text-ink-gray-5">
          {{
            __(
              'Facilities enter their own amount. It is priced at the rate of the highest Flex package the amount reaches, so Custom needs at least one active Flex package.',
            )
          }}
        </p>
        <div v-if="form.plan === 'Fixed'">
          <FormControl
            v-model="form.levels_text"
            type="textarea"
            :rows="3"
            :label="__('Facility levels (one per line)')"
            :placeholder="__('Level 2')"
            data-testid="package-levels"
          />
          <div
            v-if="levelSuggestions.length"
            class="mt-2 flex flex-wrap gap-1.5"
          >
            <Button
              v-for="level in levelSuggestions"
              :key="level"
              size="sm"
              variant="subtle"
              :label="`+ ${level}`"
              @click="addLevel(level)"
            />
          </div>
        </div>
        <FormControl
          v-model="form.description"
          type="textarea"
          :rows="2"
          :label="__('Description on the card')"
          data-testid="package-description"
        />
        <FormControl
          v-model="form.coverage_summary"
          type="textarea"
          :rows="2"
          :label="__('Coverage summary (optional)')"
          :placeholder="__('Defaults to the description')"
        />
        <div v-if="form.plan === 'Flex'" class="grid gap-4 sm:grid-cols-2">
          <FormControl
            v-model="form.journeys"
            type="text"
            :label="__('Approx. patient journeys (optional)')"
            :placeholder="__('Worked out from tokens when empty')"
          />
          <div class="flex items-end pb-1.5">
            <FormControl
              v-model="form.popular"
              type="checkbox"
              :label="__('Mark as Most popular')"
              data-testid="package-popular"
            />
          </div>
        </div>
        <div v-if="!form.row_name" class="grid gap-4 sm:grid-cols-2">
          <FormControl
            v-model="form.item_code"
            type="select"
            :label="__('Service item')"
            :options="itemOptions"
          />
          <FormControl
            v-model="form.status"
            type="select"
            :label="__('Publish')"
            :options="[
              { label: __('Active: on sale now'), value: 'Active' },
              { label: __('Disabled: save as a draft'), value: 'Disabled' },
            ]"
            data-testid="package-status"
          />
        </div>
        <p v-else class="text-xs text-ink-gray-5">
          {{ __('Service item: {0}', [form.item_code]) }}
        </p>
        <ErrorMessage :message="error" />
      </form>
    </template>
    <template #actions>
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="show = false" />
        <Button
          variant="solid"
          :label="form.row_name ? __('Save package') : __('Add package')"
          :loading="saving"
          data-testid="package-save"
          @click="submit"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import {
  Button,
  Dialog,
  ErrorMessage,
  FormControl,
  createResource,
} from 'frappe-ui'

const show = defineModel({ type: Boolean, default: false })
const props = defineProps({
  // The package to edit; without row_name a new one (a duplicate when pre-filled).
  package: { type: Object, default: () => ({}) },
  currency: { type: String, default: 'KES' },
  periods: { type: Array, default: () => ['Monthly'] },
  levelSuggestions: { type: Array, default: () => [] },
  save: { type: Function, required: true },
})

const planOptions = [
  { label: __('Flex: prepaid token package'), value: 'Flex' },
  { label: __('Fixed: fee by facility level'), value: 'Fixed' },
  { label: __('Custom: facility enters an amount'), value: 'Custom' },
]

const blank = () => ({
  row_name: '',
  item_code: '',
  plan: 'Flex',
  display_name: '',
  token_quantity: 1000,
  price: 0,
  billing_period: 'Monthly',
  levels_text: '',
  description: '',
  coverage_summary: '',
  journeys: '',
  popular: false,
  status: 'Active',
  sold_orders: 0,
})
const form = reactive(blank())
const error = ref('')
const saving = ref(false)

watch(show, (open) => {
  if (!open) return
  const pkg = props.package || {}
  Object.assign(form, blank(), pkg, {
    levels_text: (pkg.facility_levels || []).join('\n'),
    popular: Boolean(pkg.popular),
  })
  error.value = ''
})

const title = computed(() =>
  form.row_name
    ? __('Edit {0}', [props.package.display_name])
    : props.package.display_name
      ? __('Duplicate package')
      : __('New package'),
)
const locked = computed(() => Boolean(form.row_name && form.sold_orders))
const rate = computed(() => {
  const tokens = Number(form.token_quantity) || 0
  const price = Number(form.price) || 0
  return tokens && price
    ? `${props.currency} ${(price / tokens).toFixed(2)}`
    : ''
})

const items = createResource({
  url: 'frappe.client.get_list',
  auto: true,
  makeParams: () => ({
    doctype: 'Item',
    fields: ['name', 'item_name'],
    filters: { disabled: 0, is_sales_item: 1 },
    order_by: 'item_name asc',
    limit_page_length: 0,
  }),
})
const itemOptions = computed(() => [
  { label: __('Create a new item from the name'), value: '' },
  ...(items.data ?? []).map((item) => ({
    label: item.item_name ? `${item.item_name} (${item.name})` : item.name,
    value: item.name,
  })),
])

function addLevel(level) {
  const lines = form.levels_text.split('\n').filter((line) => line.trim())
  if (!lines.includes(level)) lines.push(level)
  form.levels_text = lines.join('\n')
}

async function submit() {
  error.value = ''
  saving.value = true
  try {
    await props.save({
      ...form,
      facility_levels: form.levels_text.split('\n').filter((l) => l.trim()),
      popular: form.popular ? 1 : 0,
    })
    show.value = false
  } catch (e) {
    error.value =
      e?.messages?.join(' ') || e?.message || __('Could not save the package')
  } finally {
    saving.value = false
  }
}
</script>
