<template>
  <Dialog
    v-model="show"
    :options="{ title: title, size: '3xl' }"
    data-testid="coupon-redemptions-dialog"
  >
    <template #body-content>
      <div
        v-if="resource.loading"
        class="flex items-center justify-center py-10"
      >
        <LoadingIndicator class="size-6" />
      </div>
      <div v-else class="flex flex-col gap-4">
        <p
          v-if="!rows.length"
          class="rounded-lg border border-dashed border-outline-gray-2 px-4 py-8 text-center text-sm text-ink-gray-5"
        >
          {{ __('No redemptions yet.') }}
        </p>
        <div
          v-else
          class="overflow-x-auto rounded-lg border border-outline-gray-2"
        >
          <table class="w-full text-sm">
            <thead>
              <tr
                class="border-b border-outline-gray-2 bg-surface-gray-1 text-left text-xs text-ink-gray-5"
              >
                <th class="px-3 py-2">{{ __('Facility') }}</th>
                <th class="px-3 py-2">{{ __('Customer') }}</th>
                <th class="px-3 py-2">{{ __('Order') }}</th>
                <th class="px-3 py-2">{{ __('Tokens') }}</th>
                <th class="px-3 py-2">{{ __('Status') }}</th>
                <th class="px-3 py-2">{{ __('When') }}</th>
                <th class="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in rows"
                :key="row.name"
                class="border-b border-outline-gray-1 last:border-0"
              >
                <td class="px-3 py-2 font-mono">{{ row.facility_mfl }}</td>
                <td class="px-3 py-2">{{ row.customer }}</td>
                <td class="px-3 py-2 font-mono">{{ row.sales_order }}</td>
                <td class="px-3 py-2 text-right font-mono">
                  {{ row.tokens_awarded }}
                </td>
                <td class="px-3 py-2">
                  <Badge
                    :label="__(row.status)"
                    :theme="statusTheme[row.status] || 'gray'"
                    variant="subtle"
                  />
                </td>
                <td class="px-3 py-2 text-ink-gray-5">{{ row.redeemed_on }}</td>
                <td class="px-3 py-2 text-right">
                  <Button
                    v-if="row.status === 'Reserved'"
                    size="sm"
                    variant="subtle"
                    :label="__('Release')"
                    data-testid="coupon-release"
                    @click="release(row)"
                  />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <ErrorMessage :message="actionError" />
      </div>
    </template>
    <template #actions>
      <Button :label="__('Close')" @click="show = false" />
    </template>
  </Dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import {
  Badge,
  Button,
  Dialog,
  ErrorMessage,
  LoadingIndicator,
  call,
  createResource,
  toast,
} from 'frappe-ui'

const show = defineModel({ type: Boolean, default: false })
const props = defineProps({
  coupon: { type: Object, default: null },
})

const statusTheme = {
  Reserved: 'blue',
  Granted: 'green',
  Released: 'gray',
  Lapsed: 'orange',
}

const resource = createResource({
  url: 'crm.api.coupons.list_redemptions',
  auto: false,
  makeParams: () => ({ coupon: props.coupon?.name }),
})
const rows = computed(() => resource.data?.redemptions || [])
const title = computed(() =>
  props.coupon
    ? __('Redemptions — {0}', [props.coupon.coupon_title])
    : __('Redemptions'),
)

watch(show, (open) => {
  if (open) resource.reload()
})

const actionError = ref('')
async function release(row) {
  actionError.value = ''
  try {
    await call('crm.api.coupons.release_redemption', {
      name: row.name,
      reason: '',
    })
    resource.reload()
    toast.success(__('Redemption released'))
  } catch (error) {
    actionError.value =
      error?.messages?.join(' ') || error?.message || __('Could not release')
    toast.error(actionError.value.replace(/<[^>]+>/g, ' '))
  }
}
</script>
