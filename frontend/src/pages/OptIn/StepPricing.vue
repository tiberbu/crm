<template>
  <div class="mx-auto w-full max-w-2xl px-4 py-6">
    <h2 class="mb-1 text-xl font-bold text-gray-900 dark:text-white">
      Your Package Pricing
    </h2>
    <p class="mb-5 text-sm text-gray-500 dark:text-gray-400">
      Pricing is computed from your KEPH level and locked at your selected rate.
    </p>

    <!-- Loading state -->
    <div v-if="loading" class="py-12 text-center">
      <div
        class="inline-block h-8 w-8 animate-spin rounded-full border-4 border-gray-200 border-t-transparent"
        :style="{ borderTopColor: 'var(--brand-primary)' }"
      />
      <p class="mt-3 text-sm text-gray-500 dark:text-gray-400">
        Calculating your pricing...
      </p>
    </div>

    <!-- Error state -->
    <div
      v-else-if="errorMsg"
      class="rounded-xl bg-red-50 px-6 py-8 text-center dark:bg-red-900/10"
    >
      <p class="text-sm text-red-600 dark:text-red-400">{{ errorMsg }}</p>
      <button
        class="mt-3 text-xs underline text-red-600 hover:text-red-800 dark:text-red-400"
        @click="loadPricing"
      >
        Retry
      </button>
    </div>

    <!-- Pricing table -->
    <template v-else-if="pricing">
      <section
        v-if="availablePlans.length > 1"
        class="mb-5 rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-900"
      >
        <div class="flex items-start justify-between gap-3">
          <div>
            <p class="text-sm font-semibold text-gray-900 dark:text-white">
              Choose your subscription term
            </p>
            <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Each selected year has its own quotation. Your contract remains
              one agreement.
            </p>
          </div>
          <span
            class="rounded-full bg-gray-100 px-2 py-1 text-xs font-semibold text-gray-600 dark:bg-gray-800 dark:text-gray-300"
          >
            {{ selectedYears.length }} year{{
              selectedYears.length === 1 ? '' : 's'
            }}
          </span>
        </div>
        <div class="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <button
            v-for="plan in availablePlans"
            :key="plan.year_number"
            type="button"
            :class="[
              'rounded-xl border px-3 py-2 text-left text-sm transition',
              selectedYears.includes(plan.year_number)
                ? 'border-red-500 bg-red-50 text-red-700 dark:bg-red-950/30 dark:text-red-300'
                : 'border-gray-200 text-gray-600 hover:border-gray-400 dark:border-gray-700 dark:text-gray-300',
            ]"
            @click="toggleYear(plan.year_number)"
          >
            <span class="block font-semibold">{{
              plan.label || `Year ${plan.year_number}`
            }}</span>
            <span class="mt-0.5 block text-xs opacity-70">Contract schedule</span>
            <span class="mt-1 block text-xs font-semibold opacity-90">{{
              fmtKes(plan.grand_total_annual)
            }} / year incl. VAT</span>
          </button>
        </div>
        <p
          v-if="availablePlans.length >= 3 && selectedYears.length < 3"
          class="mt-2 text-xs text-amber-600"
        >
          Select at least three years to continue.
        </p>
      </section>

      <section
        v-if="optionalServices.length"
        class="mb-5 rounded-2xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-gray-800/50"
      >
        <div>
          <p class="text-sm font-semibold text-gray-900 dark:text-white">
            Optional services and hardware
          </p>
          <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
            Select anything you would like our team to quote separately. These
            are not part of the subscription total.
          </p>
        </div>
        <div class="mt-3 grid gap-2 sm:grid-cols-2">
          <label
            v-for="item in optionalServices"
            :key="item.item_code"
            class="flex cursor-pointer items-start gap-2 rounded-xl border border-gray-200 bg-white p-3 text-sm dark:border-gray-700 dark:bg-gray-900"
          >
            <input
              v-model="selectedOptionalCodes"
              type="checkbox"
              :value="item.item_code"
              class="mt-0.5"
            />
            <span
              ><span class="block font-medium text-gray-900 dark:text-white">{{
                item.item_name
              }}</span
              ><span class="block text-xs text-gray-500">{{
                item.description
              }}</span></span
            >
          </label>
        </div>
      </section>

      <!-- Hero total: selected-term commitment is the number that matters. -->
      <div class="mb-5 grid gap-3 sm:grid-cols-2">
        <div
          class="flex overflow-hidden rounded-2xl border border-gray-200 shadow-sm dark:border-gray-700"
        >
          <div
            class="w-1.5 shrink-0"
            style="background-color: var(--brand-primary)"
          />
          <div
            class="flex-1 p-5"
            style="
              background-color: color-mix(
                in srgb,
                var(--brand-primary) 6%,
                transparent
              );
            "
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <p
                  class="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400"
                >
                  Total contract commitment · incl. VAT
                </p>
                <p
                  class="mt-0.5 text-3xl font-extrabold tracking-tight text-gray-900 dark:text-white"
                >
                  {{ fmtKes(commitmentAnnual) }}
                </p>
              </div>
              <span
                class="mt-1 shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold"
                style="
                  background-color: color-mix(
                    in srgb,
                    var(--brand-primary) 14%,
                    transparent
                  );
                  color: var(--brand-primary);
                "
              >
                {{ selectedYears.length }}
                {{ selectedYears.length === 1 ? 'year' : 'years' }}
              </span>
            </div>
            <div class="mt-2 flex flex-wrap items-baseline gap-2 text-sm">
              <span class="text-gray-500 dark:text-gray-400">
                Selected term · {{ selectedYears.length }} year{{
                  selectedYears.length === 1 ? '' : 's'
                }}
              </span>
              <span class="font-semibold text-gray-800 dark:text-gray-200">
                {{ fmtKes(commitmentNetAnnual) }} net
              </span>
            </div>
          </div>
        </div>
        <div
          class="rounded-2xl border border-gray-200 bg-gray-50 p-5 dark:border-gray-700 dark:bg-gray-800/50"
        >
          <p
            class="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400"
          >
            Active year · Year {{ activePlan.year_number || 1 }}
          </p>
          <p class="mt-1 text-2xl font-bold text-gray-900 dark:text-white">
            {{ fmtKes(activePlan.grand_total_annual) }}
          </p>
          <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Annual incl. VAT · {{
              activePlan.label ||
              `Year ${activePlan.year_number || 1} contract schedule`
            }}
          </p>
          <p class="mt-3 text-xs text-gray-500 dark:text-gray-400">
            Each selected year has its own quotation. Optional services are
            shown separately and are not included in this total.
          </p>
        </div>
      </div>

      <div
        class="overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-700"
      >
        <table class="w-full text-sm">
          <thead class="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th
                class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400"
              >
                Facility
              </th>
              <th
                class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400"
              >
                KEPH Level
              </th>
              <th
                class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400"
              >
                Monthly (KES, excl. VAT)
              </th>
              <th
                class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400"
              >
                Annual (KES, excl. VAT)
              </th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100 dark:divide-gray-700">
            <tr
              v-for="fac in activePlan.facilities"
              :key="fac.mfl_code"
              class="bg-white dark:bg-gray-900"
            >
              <td class="px-4 py-3">
                <p class="font-medium text-gray-900 dark:text-white">
                  {{ fac.facility_name }}
                </p>
                <p class="text-xs text-gray-400 dark:text-gray-500">
                  {{ fac.mfl_code }}
                </p>
              </td>
              <td class="px-4 py-3">
                <span
                  :class="[
                    'rounded-full px-2 py-0.5 text-xs font-semibold',
                    kephBadgeClass(fac.keph_level),
                  ]"
                >
                  {{ fac.keph_level }}
                </span>
              </td>
              <td
                class="px-4 py-3 text-right font-medium text-gray-900 dark:text-white"
              >
                {{ fmtKes(fac.monthly_kes) }}
              </td>
              <td
                class="px-4 py-3 text-right font-medium text-gray-900 dark:text-white"
              >
                {{ fmtKes(fac.annual_kes) }}
              </td>
            </tr>
          </tbody>
          <!-- Subtotals -->
          <tfoot class="bg-gray-50 dark:bg-gray-800">
            <tr>
              <td
                colspan="2"
                class="px-4 py-2 text-right text-xs text-gray-500 dark:text-gray-400"
              >
                Subtotal
              </td>
              <td
                class="px-4 py-2 text-right text-sm text-gray-700 dark:text-gray-300"
              >
                {{ fmtKes(activePlan.subtotal_monthly) }}
              </td>
              <td
                class="px-4 py-2 text-right text-sm text-gray-700 dark:text-gray-300"
              >
                {{ fmtKes(activePlan.subtotal_annual) }}
              </td>
            </tr>
            <tr>
              <td
                colspan="2"
                class="px-4 py-2 text-right text-xs text-gray-500 dark:text-gray-400"
              >
                {{ pricing.vat_label || 'VAT' }}
              </td>
              <td
                class="px-4 py-2 text-right text-sm text-gray-700 dark:text-gray-300"
              >
                {{ fmtKes(activePlan.vat_monthly) }}
              </td>
              <td
                class="px-4 py-2 text-right text-sm text-gray-700 dark:text-gray-300"
              >
                {{ fmtKes(activePlan.vat_annual) }}
              </td>
            </tr>
            <tr class="border-t-2 border-gray-200 dark:border-gray-600">
              <td
                colspan="2"
                class="px-4 py-3 text-right text-sm font-bold text-gray-900 dark:text-white"
              >
                Grand Total (incl. VAT)
              </td>
              <td
                class="px-4 py-3 text-right text-base font-bold"
                :style="{ color: 'var(--brand-primary)' }"
              >
                {{ fmtKes(activePlan.grand_total_monthly) }}
              </td>
              <td
                class="px-4 py-3 text-right text-base font-bold"
                :style="{ color: 'var(--brand-primary)' }"
              >
                {{ fmtKes(activePlan.grand_total_annual) }}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>

      <p class="mt-3 text-xs text-gray-400 dark:text-gray-500">
        * Prices exclude applicable taxes shown above. All amounts in Kenya
        Shillings (KES).
      </p>
    </template>

    <!-- Footer nav -->
    <div class="mt-6 flex items-center justify-between">
      <button
        class="rounded-xl border border-gray-200 bg-white px-5 py-2.5 text-sm font-medium text-gray-600 transition hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
        @click="emit('back')"
      >
        Back
      </button>
      <button
        :disabled="loading || !!errorMsg || !canContinue"
        class="rounded-xl px-6 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
        style="background-color: var(--brand-primary)"
        @click="emit('continue')"
      >
        Continue
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { createResource } from 'frappe-ui'
import { useOptInStore } from './useOptInStore.js'

const props = defineProps({
  networkSlug: { type: String, required: true },
  dealInvitation: { type: String, default: '' },
})

const emit = defineEmits(['continue', 'back'])

const store = useOptInStore()
const loading = ref(false)
const errorMsg = ref('')
const pricing = ref(store.pricing || null)
const availablePlans = computed(
  () => store.networkConfig?.price_plans || pricing.value?.plans || [],
)
const selectedYears = ref(
  (store.pricing?.selected_years?.length
    ? [...store.pricing.selected_years]
    : availablePlans.value.length >= 3
      ? availablePlans.value.slice(0, 3).map((plan) => plan.year_number)
      : availablePlans.value.map((plan) => plan.year_number)) || [1],
)
const selectedOptionalCodes = ref(
  (store.optionalItems || []).map((item) => item.item_code),
)
const optionalServices = computed(
  () =>
    store.networkConfig?.optional_services ||
    pricing.value?.optional_services ||
    [],
)
const activePlan = computed(() => {
  const year = selectedYears.value[0]
  return (
    (pricing.value?.plans || []).find((plan) => plan.year_number === year) ||
    pricing.value || { facilities: [] }
  )
})
const commitmentAnnual = computed(() =>
  Number(pricing.value?.commitment_annual ?? activePlan.value.grand_total_annual ?? 0),
)
const commitmentNetAnnual = computed(() =>
  Number(
    pricing.value?.commitment_net_annual ??
      activePlan.value.subtotal_annual ??
      0,
  ),
)
const canContinue = computed(
  () =>
    activePlan.value.facilities?.length > 0 &&
    (availablePlans.value.length < 3 || selectedYears.value.length >= 3),
)

const pricingResource = createResource({ url: 'crm.api.optin.get_pricing' })

watch(
  selectedOptionalCodes,
  (codes) => {
    store.setOptionalItems(
      optionalServices.value.filter((item) => codes.includes(item.item_code)),
    )
  },
  { deep: true },
)

async function loadPricing() {
  loading.value = true
  errorMsg.value = ''
  try {
    const mflCodes = (store.selectedFacilities || []).map((f) => f.mfl_code)
    const data = await pricingResource.fetch({
      signing_token: store.signingToken,
      email: store.contact.email,
      network_slug: props.networkSlug,
      expiry: store.signingExpiry,
      selected_mfl_codes: JSON.stringify(mflCodes),
      deal_invitation: props.dealInvitation,
      selected_years: JSON.stringify(selectedYears.value),
    })
    if (!(data?.facilities || []).length) {
      pricing.value = null
      store.setPricing(null)
      errorMsg.value =
        'No valid pricing is available for the selected facilities. Please go back and review your selection.'
      return
    }
    pricing.value = data
    store.setPricing(data)
    store.setOptionalItems(
      optionalServices.value.filter((item) =>
        selectedOptionalCodes.value.includes(item.item_code),
      ),
    )
  } catch (err) {
    errorMsg.value =
      err && err.message
        ? err.message
        : 'Failed to load pricing. Please go back and try again.'
  } finally {
    loading.value = false
  }
}

function toggleYear(year) {
  if (selectedYears.value.includes(year)) {
    if (selectedYears.value.length === 1) return
    selectedYears.value = selectedYears.value.filter((value) => value !== year)
  } else {
    selectedYears.value = [...selectedYears.value, year].sort((a, b) => a - b)
  }
  loadPricing()
}

onMounted(() => {
  if (!store.pricing) {
    loadPricing()
  }
})

function kephBadgeClass(keph) {
  const level = (keph || '')
    .replace(/^Level\s+/i, '')
    .trim()
    .toUpperCase()
  if (['5', '6'].includes(level))
    return 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
  if (['3A', '4', '4B'].includes(level))
    return 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400'
  return 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
}

function fmtKes(v) {
  const n = parseFloat(v || 0)
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: 'KES',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(n)
}
</script>
