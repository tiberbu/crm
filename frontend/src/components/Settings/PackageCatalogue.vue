<template>
  <div class="flex h-full flex-col gap-6 px-6 py-8 text-ink-gray-8">
    <div class="flex flex-wrap items-start justify-between gap-4 px-2">
      <div>
        <h2 class="text-2xl-semibold leading-none">{{ __('Packages') }}</h2>
        <p class="mt-1 text-p-base text-ink-gray-6">
          {{
            __(
              'The Value Express packages facilities can buy on the landing page and in self-onboarding. Changes show on the next page load.',
            )
          }}
        </p>
      </div>
      <Button
        variant="solid"
        :label="__('New package')"
        :disabled="!catalogue.price_list"
        data-testid="package-new"
        @click="openEditor({})"
      >
        <template #prefix><LucidePlus class="size-4" /></template>
      </Button>
    </div>

    <div
      v-if="resource.loading && !catalogue.version"
      class="flex flex-1 items-center justify-center"
    >
      <LoadingIndicator class="size-6" />
    </div>
    <div v-else class="flex flex-1 flex-col gap-6 overflow-y-auto px-2 pb-6">
      <div
        v-if="!catalogue.price_list"
        class="rounded-lg bg-surface-amber-1 px-4 py-3 text-sm text-ink-amber-3"
      >
        {{
          __(
            'No token selling Price List is set. Ask an administrator to set one in Settings › Opt-In Process; package prices are kept there.',
          )
        }}
      </div>
      <div v-else class="flex flex-wrap items-center justify-between gap-3">
        <TabButtons
          v-model="filter"
          :buttons="filters"
          data-testid="package-filter"
        />
        <span class="text-sm text-ink-gray-5">
          {{
            __('Prices excl. VAT, from Price List {0}', [catalogue.price_list])
          }}
        </span>
      </div>

      <section
        v-for="group in groups"
        :key="group.plan"
        :data-testid="`package-section-${group.plan}`"
      >
        <div class="mb-3 flex items-baseline gap-2">
          <h3 class="text-base font-semibold text-ink-gray-8">
            {{ group.title }}
          </h3>
          <span class="text-sm text-ink-gray-5">{{ group.hint }}</span>
        </div>
        <p
          v-if="!group.packages.length"
          class="rounded-lg border border-dashed border-outline-gray-2 px-4 py-6 text-center text-sm text-ink-gray-5"
        >
          {{ __('No {0} packages here.', [group.title]) }}
        </p>
        <div
          v-else
          class="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(15rem,1fr))]"
        >
          <article
            v-for="pkg in group.packages"
            :key="pkg.row_name"
            class="flex flex-col rounded-xl border border-outline-gray-2 bg-surface-white p-4 shadow-sm dark:bg-surface-gray-1"
            :class="{ 'opacity-70': pkg.status !== 'Active' }"
            data-testid="package-card"
            :data-package="pkg.display_name"
          >
            <div class="flex items-start justify-between gap-2">
              <div class="min-w-0">
                <p
                  class="truncate font-semibold text-ink-gray-9"
                  :title="pkg.display_name"
                >
                  {{ pkg.display_name }}
                </p>
                <p
                  class="truncate text-xs text-ink-gray-5"
                  :title="pkg.item_code"
                >
                  {{ pkg.item_code }}
                </p>
              </div>
              <Dropdown :options="actions(pkg)" placement="right">
                <Button
                  variant="ghost"
                  :aria-label="__('Package actions')"
                  data-testid="package-actions"
                >
                  <LucideEllipsis class="size-4" />
                </Button>
              </Dropdown>
            </div>
            <div class="mt-2 flex flex-wrap gap-1.5">
              <Badge
                :label="__(pkg.status)"
                :theme="statusTheme[pkg.status]"
                variant="subtle"
                data-testid="package-status-badge"
              />
              <Badge
                v-if="pkg.popular"
                :label="__('Most popular')"
                theme="blue"
                variant="subtle"
              />
              <Badge
                v-if="pkg.sold_orders"
                :label="__('{0} orders', [pkg.sold_orders])"
                theme="gray"
                variant="outline"
              />
            </div>
            <p
              v-if="pkg.plan !== 'Custom'"
              class="mt-3 font-mono text-xl font-semibold"
              data-testid="package-price"
            >
              {{ money(pkg.price, pkg.currency) }}
              <span class="font-sans text-sm font-normal text-ink-gray-5">{{
                __(periodLabel(pkg.billing_period))
              }}</span>
            </p>
            <p v-else class="mt-3 text-sm text-ink-gray-6">
              {{ __('Amount entered by the facility') }}
            </p>
            <dl class="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
              <template v-if="pkg.plan === 'Flex'">
                <dt class="text-ink-gray-5">{{ __('Tokens') }}</dt>
                <dd class="text-right font-mono">
                  {{ pkg.token_quantity.toLocaleString() }}
                </dd>
                <dt class="text-ink-gray-5">{{ __('Per token') }}</dt>
                <dd class="text-right font-mono">{{ perToken(pkg) }}</dd>
              </template>
              <template v-if="pkg.plan === 'Fixed'">
                <dt class="text-ink-gray-5">{{ __('Levels') }}</dt>
                <dd class="text-right">
                  {{ pkg.facility_levels.join(', ') || '—' }}
                </dd>
              </template>
              <template v-if="pkg.discontinued_on">
                <dt class="text-ink-gray-5">{{ __('Discontinued') }}</dt>
                <dd class="text-right">{{ pkg.discontinued_on }}</dd>
              </template>
            </dl>
            <p class="mt-2 line-clamp-2 text-sm text-ink-gray-6">
              {{ pkg.description }}
            </p>
          </article>
        </div>
      </section>
      <ErrorMessage :message="actionError" />
    </div>

    <PackageEditDialog
      v-model="editorOpen"
      :package="editing"
      :currency="catalogue.currency"
      :periods="catalogue.periods"
      :level-suggestions="catalogue.level_suggestions"
      :save="savePackage"
    />
    <Dialog
      v-model="confirmOpen"
      :options="{
        title: __('Discontinue {0}?', [confirming?.display_name]),
        message: __(
          'Facilities can no longer buy it, and it cannot be switched back on. Existing orders and history keep it. To sell it again later, duplicate it as a new package.',
        ),
        actions: [
          {
            label: __('Discontinue'),
            variant: 'solid',
            theme: 'red',
            onClick: discontinue,
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
import PackageEditDialog from '@/components/Settings/PackageEditDialog.vue'
import { periodLabel } from '@/utils/valueExpress'

const API = 'crm.api.package_catalogue'
const statusTheme = {
  Active: 'green',
  Disabled: 'orange',
  Discontinued: 'gray',
}

const resource = createResource({
  url: `${API}.get_package_catalogue`,
  auto: true,
})
const catalogue = computed(
  () =>
    resource.data || {
      packages: [],
      periods: [],
      level_suggestions: [],
      currency: 'KES',
      price_list: '',
      version: '',
    },
)

const filter = ref('Active')
const filters = computed(() => {
  const count = (status) =>
    catalogue.value.packages.filter((p) => !status || p.status === status)
      .length
  return [
    { label: `${__('Active')} (${count('Active')})`, value: 'Active' },
    { label: `${__('Disabled')} (${count('Disabled')})`, value: 'Disabled' },
    {
      label: `${__('Discontinued')} (${count('Discontinued')})`,
      value: 'Discontinued',
    },
    { label: `${__('All')} (${count()})`, value: 'All' },
  ]
})

const groups = computed(() =>
  [
    { plan: 'Flex', title: __('Flex'), hint: __('Prepaid token packages') },
    {
      plan: 'Fixed',
      title: __('Fixed'),
      hint: __('A set fee by facility level, per billing period'),
    },
    {
      plan: 'Custom',
      title: __('Custom'),
      hint: __('The facility enters an amount'),
    },
  ].map((group) => ({
    ...group,
    packages: catalogue.value.packages.filter(
      (p) =>
        p.plan === group.plan &&
        (filter.value === 'All' || p.status === filter.value),
    ),
  })),
)

function money(value, currency) {
  return `${currency || catalogue.value.currency} ${Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`
}

function perToken(pkg) {
  return pkg.token_quantity && pkg.price
    ? `${pkg.currency || catalogue.value.currency} ${(pkg.price / pkg.token_quantity).toFixed(2)}`
    : '—'
}

const actionError = ref('')

async function run(method, params, done) {
  actionError.value = ''
  try {
    resource.data = await call(`${API}.${method}`, {
      ...params,
      version: catalogue.value.version,
    })
    if (done) toast.success(done)
  } catch (error) {
    // A stale view is the usual cause; show the latest catalogue with the reason.
    resource.reload()
    actionError.value =
      error?.messages?.join(' ') ||
      error?.message ||
      __('Could not update the package')
    toast.error(actionError.value.replace(/<[^>]+>/g, ' '))
  }
}

const editorOpen = ref(false)
const editing = ref({})

function openEditor(pkg) {
  editing.value = pkg
  editorOpen.value = true
}

function duplicate(pkg) {
  // A new package from this one: its own item, on sale once saved.
  openEditor({
    ...pkg,
    row_name: '',
    item_code: '',
    status: 'Active',
    sold_orders: 0,
    discontinued_on: '',
    display_name: __('{0} copy', [pkg.display_name]),
  })
}

async function savePackage(pkg) {
  // Errors reach the dialog, which stays open so nothing typed is lost.
  resource.data = await call(`${API}.save_package`, {
    package: pkg,
    version: catalogue.value.version,
  })
  filter.value = pkg.row_name ? filter.value : pkg.status || 'Active'
  toast.success(__('Package saved'))
}

const confirmOpen = ref(false)
const confirming = ref(null)

async function discontinue({ close }) {
  await run(
    'set_package_status',
    { row_name: confirming.value.row_name, status: 'Discontinued' },
    __('Package discontinued'),
  )
  close()
}

function actions(pkg) {
  const setStatus = (status, done) => () =>
    run('set_package_status', { row_name: pkg.row_name, status }, done)
  const move = (direction) => () =>
    run('move_package', {
      row_name: pkg.row_name,
      direction,
      visible: groups.value.flatMap((g) => g.packages.map((p) => p.row_name)),
    })
  if (pkg.status === 'Discontinued') {
    return [{ label: __('Duplicate as new'), onClick: () => duplicate(pkg) }]
  }
  return [
    { label: __('Edit'), onClick: () => openEditor(pkg) },
    { label: __('Duplicate'), onClick: () => duplicate(pkg) },
    { label: __('Move earlier'), onClick: move('up') },
    { label: __('Move later'), onClick: move('down') },
    pkg.status === 'Active'
      ? {
          label: __('Disable'),
          onClick: setStatus('Disabled', __('Package disabled')),
        }
      : {
          label: __('Enable'),
          onClick: setStatus('Active', __('Package enabled')),
        },
    {
      label: __('Discontinue'),
      onClick: () => {
        confirming.value = pkg
        confirmOpen.value = true
      },
    },
  ]
}
</script>
