<template>
  <Dialog
    v-model="show"
    :options="{ title: title, size: '2xl' }"
    data-testid="coupon-dialog"
  >
    <template #body-content>
      <form class="flex flex-col gap-4" @submit.prevent="submit">
        <div class="grid gap-4 sm:grid-cols-2">
          <FormControl
            v-model="form.coupon_title"
            type="text"
            :label="__('Coupon title')"
            :placeholder="__('e. g. 2026 onboarding bonus')"
            data-testid="coupon-title"
          />
          <FormControl
            v-model="form.network"
            type="select"
            :label="__('Network')"
            :options="networkOptions"
            :description="
              __(
                'Blank makes this a CRM coupon, not tied to a partner network.',
              )
            "
            data-testid="coupon-network"
          />
        </div>

        <div class="coupon-plans flex flex-col gap-2" data-testid="coupon-applies-to">
          <p class="text-sm text-ink-gray-7">{{ __('Applies to') }}</p>
          <div class="flex flex-wrap gap-4">
            <label
              v-for="option in planOptions"
              :key="option.value"
              class="flex items-center gap-2 text-base text-ink-gray-8"
            >
              <input
                v-model="form.applies_to"
                type="radio"
                name="coupon-applies-to"
                :value="option.value"
                :disabled="locked"
                :data-testid="`coupon-applies-to-${option.value.toLowerCase()}`"
              />
              {{ option.label }}
            </label>
          </div>
          <p class="text-sm text-ink-gray-6">{{ planHelp }}</p>
        </div>

        <div
          v-if="form.applies_to !== 'Flex'"
          class="grid gap-4 sm:grid-cols-3"
        >
          <FormControl
            v-model="form.fixed_discount_percent"
            type="number"
            :label="__('Fixed plan discount (%)')"
            :description="__('Taken off the Fixed package price')"
            min="0"
            max="100"
            step="0.01"
            :disabled="locked"
            data-testid="coupon-fixed-discount"
          />
        </div>

        <p
          v-if="form.applies_to !== 'Fixed'"
          class="-mb-2 text-sm text-ink-gray-7"
        >
          {{
            form.applies_to === 'Both'
              ? __('Flex plan: complimentary tokens')
              : __('Complimentary tokens')
          }}
        </p>
        <div
          v-if="form.applies_to !== 'Fixed'"
          class="grid gap-4 sm:grid-cols-3"
        >
          <FormControl
            v-model="form.value_type"
            type="select"
            :label="__('Value type')"
            :options="valueOptions"
            data-testid="coupon-value-type"
          />
          <FormControl
            v-model="form.value"
            type="number"
            :label="valueLabel"
            min="0"
            step="0.01"
            data-testid="coupon-value"
          />
          <FormControl
            v-model="form.max_tokens"
            type="number"
            :label="__('Max tokens (cap)')"
            :description="__('0 means no cap')"
            min="0"
            data-testid="coupon-max-tokens"
          />
        </div>

        <div class="grid gap-4 sm:grid-cols-3">
          <FormControl
            v-model="form.valid_from"
            type="date"
            :label="__('Valid from')"
            data-testid="coupon-valid-from"
          />
          <FormControl
            v-model="form.valid_to"
            type="date"
            :label="__('Valid to')"
            :description="__('Blank never expires')"
            data-testid="coupon-valid-to"
          />
          <FormControl
            v-model="form.max_redemptions"
            type="number"
            :label="__('Max redemptions')"
            :description="__('0 means unlimited')"
            min="0"
            data-testid="coupon-max-redemptions"
          />
        </div>

        <div
          v-if="!form.network"
          class="rounded-lg border border-outline-gray-2 p-4"
        >
          <p class="mb-3 text-sm font-semibold text-ink-gray-8">
            {{ __('Targeting (CRM coupons only)') }}
          </p>
          <FormControl
            v-model="form.targeting"
            type="select"
            :label="__('How facilities get this coupon')"
            :options="targetingOptions"
            data-testid="coupon-targeting"
          />
          <FormControl
            v-if="form.targeting === 'Facility Level'"
            v-model="form.facility_levels"
            type="textarea"
            :rows="3"
            class="mt-3"
            :label="__('Facility levels (one per line)')"
            :placeholder="__('Level 2')"
            data-testid="coupon-facility-levels"
          />
          <FormControl
            v-if="form.targeting === 'Coupon Code'"
            v-model="form.coupon_code"
            type="text"
            class="mt-3"
            :label="__('Coupon code')"
            :description="
              __('Letters, numbers or dashes, 4 to 32. Never six digits.')
            "
            data-testid="coupon-code"
          />
          <p
            v-if="form.targeting === 'Assigned Facilities'"
            class="mt-3 text-sm text-ink-gray-5"
          >
            {{
              __(
                'Assign facilities from the coupon menu (Assign). A client who redeems this coupon at onboarding is assigned automatically.',
              )
            }}
          </p>
        </div>

        <div class="grid gap-4 sm:grid-cols-2">
          <FormControl
            v-model="form.client_label"
            type="text"
            :label="__('Client label (optional)')"
            :placeholder="__('What the complimentary line says')"
            data-testid="coupon-client-label"
          />
          <FormControl
            v-model="form.description"
            type="textarea"
            :rows="2"
            :label="__('Description (internal)')"
            data-testid="coupon-description"
          />
        </div>
        <ErrorMessage :message="error" />
      </form>
    </template>
    <template #actions>
      <div class="flex justify-end gap-2">
        <Button :label="__('Cancel')" @click="show = false" />
        <Button
          variant="solid"
          :label="form.name ? __('Save coupon') : __('Add coupon')"
          :loading="saving"
          data-testid="coupon-save"
          @click="submit"
        />
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { Button, Dialog, ErrorMessage, FormControl } from 'frappe-ui'

const show = defineModel({ type: Boolean, default: false })
const props = defineProps({
  coupon: { type: Object, default: () => ({}) },
  save: { type: Function, required: true },
  networks: { type: Array, default: () => [] },
})

const blank = () => ({
  name: '',
  coupon_title: '',
  network: '',
  applies_to: 'Flex',
  value_type: 'flat_tokens',
  value: 0,
  max_tokens: 0,
  fixed_discount_percent: 0,
  valid_from: '',
  valid_to: '',
  max_redemptions: 0,
  targeting: '',
  facility_levels: '',
  coupon_code: '',
  client_label: '',
  description: '',
})
const form = reactive(blank())
const error = ref('')
const saving = ref(false)

watch(show, (open) => {
  if (!open) return
  const c = props.coupon || {}
  Object.assign(form, blank(), c, {
    network: c.network || '',
    applies_to: c.applies_to || 'Flex',
    value_type: c.value_type || 'flat_tokens',
    fixed_discount_percent: c.fixed_discount_percent || 0,
    max_tokens: c.max_tokens || 0,
    max_redemptions: c.max_redemptions || 0,
  })
  error.value = ''
})

const title = computed(() =>
  form.name ? __('Edit {0}', [form.coupon_title]) : __('New coupon'),
)

const networkOptions = computed(() => [
  { label: __('CRM coupon (no network)'), value: '' },
  ...props.networks.map((n) => ({ label: n, value: n })),
])
const planOptions = [
  { label: __('Flex (tokens)'), value: 'Flex' },
  { label: __('Fixed (discount)'), value: 'Fixed' },
  { label: __('Both'), value: 'Both' },
]
// A used coupon keeps its plan and value (the server refuses changes too).
const locked = computed(() => Number(props.coupon?.redeemed_count || 0) > 0)
const planHelp = computed(
  () =>
    ({
      Flex: __(
        'Gives complimentary tokens on a Flex token package order only.',
      ),
      Fixed: __(
        'Takes a percentage off the Fixed package price. Gives no tokens.',
      ),
      Both: __(
        'Flex orders get the tokens below; Fixed orders get the discount. A facility uses one coupon once.',
      ),
    })[form.applies_to],
)
const valueOptions = [
  { label: __('Flat tokens'), value: 'flat_tokens' },
  { label: __('% of purchased tokens'), value: 'percentage_of_purchase' },
]
const targetingOptions = [
  { label: __('—'), value: '' },
  { label: __('Assigned facilities'), value: 'Assigned Facilities' },
  { label: __('Facility level'), value: 'Facility Level' },
  { label: __('Coupon code'), value: 'Coupon Code' },
]
const valueLabel = computed(() =>
  form.value_type === 'percentage_of_purchase'
    ? __('Percentage of purchase')
    : __('Tokens'),
)

async function submit() {
  error.value = ''
  saving.value = true
  try {
    await props.save({ ...form })
    show.value = false
  } catch (e) {
    error.value =
      e?.messages?.join(' ') || e?.message || __('Could not save the coupon')
  } finally {
    saving.value = false
  }
}
</script>

<style>
/* Brand guide: native radios take the brand red, never the forms-plugin blue. */
.coupon-plans input[type='radio'] {
  color: var(--ink-blue-6); /* the desk theme maps this token to the brand red */
  accent-color: var(--ink-blue-6);
}
.coupon-plans input[type='radio']:focus {
  --tw-ring-color: var(--brand-tint-07);
}
</style>
