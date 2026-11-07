<template>
  <div class="flex h-full flex-col gap-6 px-6 py-8 text-ink-gray-8">
    <div class="flex flex-wrap items-start justify-between gap-4 px-2">
      <div>
        <h2 class="text-2xl-semibold leading-none">{{ __('Coupons') }}</h2>
        <p class="mt-1 text-p-base text-ink-gray-6">
          {{
            __(
              'Per-network and CRM coupons. A coupon sets how many tokens a facility earns — a flat amount or a share of what it buys — with a validity window, redemption limits and revocation.',
            )
          }}
        </p>
      </div>
      <Button
        variant="solid"
        :label="__('New coupon')"
        data-testid="coupon-new"
        @click="openEditor({})"
      >
        <template #prefix><LucidePlus class="size-4" /></template>
      </Button>
    </div>

    <div
      v-if="resource.loading && !coupons.length"
      class="flex flex-1 items-center justify-center"
    >
      <LoadingIndicator class="size-6" />
    </div>
    <div v-else class="flex flex-1 flex-col gap-6 overflow-y-auto px-2 pb-6">
      <TabButtons
        v-model="filter"
        :buttons="filters"
        data-testid="coupon-filter"
      />

      <p
        v-if="!coupons.length"
        class="rounded-lg border border-dashed border-outline-gray-2 px-4 py-8 text-center text-sm text-ink-gray-5"
      >
        {{ __('No coupons here yet.') }}
      </p>

      <div
        v-else
        class="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(16rem,1fr))]"
      >
        <article
          v-for="coupon in coupons"
          :key="coupon.name"
          class="flex flex-col rounded-xl border border-outline-gray-2 bg-surface-white p-4 shadow-sm dark:bg-surface-gray-1"
          :class="{ 'opacity-70': coupon.derived_status !== 'Active' }"
          data-testid="coupon-card"
          :data-coupon="coupon.name"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <p
                class="truncate font-semibold text-ink-gray-9"
                :title="coupon.coupon_title"
              >
                {{ coupon.coupon_title }}
              </p>
              <p class="truncate text-xs text-ink-gray-5">
                {{
                  coupon.network
                    ? networkLabel(coupon.network)
                    : __('CRM coupon')
                }}
              </p>
            </div>
            <Dropdown :options="actions(coupon)" placement="right">
              <Button
                variant="ghost"
                :aria-label="__('Coupon actions')"
                data-testid="coupon-actions"
              >
                <LucideEllipsis class="size-4" />
              </Button>
            </Dropdown>
          </div>
          <div class="mt-2 flex flex-wrap gap-1.5">
            <Badge
              :label="__(coupon.derived_status)"
              :theme="COUPON_STATUS_THEME[coupon.derived_status] || 'gray'"
              variant="subtle"
              data-testid="coupon-status-badge"
            />
            <Badge
              v-if="coupon.coupon_code"
              :label="coupon.coupon_code"
              theme="gray"
              variant="outline"
            />
          </div>
          <p
            class="mt-3 font-mono text-lg font-semibold"
            data-testid="coupon-value"
          >
            {{ couponValueLabel(coupon) }}
          </p>
          <dl class="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
            <dt class="text-ink-gray-5">{{ __('Redeemed') }}</dt>
            <dd class="text-right font-mono">
              {{ coupon.redeemed_count
              }}{{
                coupon.max_redemptions ? ` / ${coupon.max_redemptions}` : ''
              }}
            </dd>
            <dt class="text-ink-gray-5">{{ __('Window') }}</dt>
            <dd class="text-right">
              {{ windowLabel(coupon) }}
            </dd>
          </dl>
        </article>
      </div>
      <ErrorMessage :message="actionError" />
    </div>

    <CouponEditDialog
      v-model="editorOpen"
      :coupon="editing"
      :save="saveCoupon"
      :networks="networks"
    />
    <CouponRedemptions v-model="redemptionsOpen" :coupon="redemptionsCoupon" />
    <Dialog
      v-model="revokeOpen"
      :options="{
        title: __('Revoke {0}?', [revokeTarget?.coupon_title]),
        message: __(
          'New orders and payments will no longer use this coupon. Tokens already granted are never taken back.',
        ),
        actions: [
          {
            label: __('Revoke'),
            variant: 'solid',
            theme: 'red',
            onClick: doRevoke,
          },
        ],
      }"
    />
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import {
  Badge,
  Button,
  Dialog,
  Dropdown,
  ErrorMessage,
  LoadingIndicator,
  TabButtons,
  call,
  createResource,
  toast,
} from 'frappe-ui'
import LucidePlus from '~icons/lucide/plus'
import LucideEllipsis from '~icons/lucide/ellipsis'
import CouponEditDialog from '@/components/Settings/CouponEditDialog.vue'
import CouponRedemptions from '@/components/Settings/CouponRedemptions.vue'
import { COUPON_STATUS_THEME, couponValueLabel } from '@/utils/coupons'

const API = 'crm.api.coupons'

const resource = createResource({
  url: `${API}.list_coupons`,
  auto: true,
})
const list = computed(() => resource.data?.coupons || [])

const filter = ref('All')
const filters = computed(() => {
  const by = (status) =>
    list.value.filter((c) => !status || c.derived_status === status).length
  return [
    { label: `${__('All')} (${by('')})`, value: 'All' },
    { label: `${__('Active')} (${by('Active')})`, value: 'Active' },
    { label: `${__('Revoked')} (${by('Revoked')})`, value: 'Revoked' },
  ]
})
const coupons = computed(() =>
  list.value.filter(
    (c) => filter.value === 'All' || c.derived_status === filter.value,
  ),
)

const networks = computed(() => [
  ...new Set(list.value.map((c) => c.network).filter(Boolean)),
])
function networkLabel(name) {
  const c = list.value.find((x) => x.network === name)
  return c?.client_label || name
}
function windowLabel(coupon) {
  const from = coupon.valid_from ? `from ${coupon.valid_from}` : 'any time'
  const to = coupon.valid_to ? `to ${coupon.valid_to}` : 'no expiry'
  return `${from} · ${to}`
}

const actionError = ref('')
async function run(method, params, done) {
  actionError.value = ''
  try {
    await call(`${API}.${method}`, params)
    resource.reload()
    if (done) toast.success(done)
  } catch (error) {
    actionError.value =
      error?.messages?.join(' ') ||
      error?.message ||
      __('Could not update the coupon')
    toast.error(actionError.value.replace(/<[^>]+>/g, ' '))
  }
}

const editorOpen = ref(false)
const editing = ref({})
function openEditor(coupon) {
  editing.value = coupon
  editorOpen.value = true
}
async function saveCoupon(payload) {
  await run(
    'save_coupon',
    { name: payload.name || '', payload },
    __('Coupon saved'),
  )
  editorOpen.value = false
}

const redemptionsOpen = ref(false)
const redemptionsCoupon = ref(null)
function showRedemptions(coupon) {
  redemptionsCoupon.value = coupon
  redemptionsOpen.value = true
}

const revokeOpen = ref(false)
const revokeTarget = ref(null)
async function doRevoke({ close }) {
  await run(
    'revoke_coupon',
    { name: revokeTarget.value.name, reason: '' },
    __('Coupon revoked'),
  )
  close()
}

function actions(coupon) {
  return [
    { label: __('Edit'), onClick: () => openEditor(coupon) },
    {
      label: __('Redemptions'),
      onClick: () => showRedemptions(coupon),
    },
    ...(coupon.derived_status === 'Revoked'
      ? []
      : [
          {
            label: __('Revoke'),
            onClick: () => {
              revokeTarget.value = coupon
              revokeOpen.value = true
            },
          },
        ]),
  ]
}
</script>
