<script setup>
import { onMounted, ref } from 'vue'
import { call } from 'frappe-ui'

const loading = ref(true)
const errorMessage = ref('')
const context = ref({ user: '', ois: [] })
const purchaseOis = ref('')
const purchaseFacility = ref('')
const purchaseBusy = ref(false)
const purchaseMessage = ref('')
const purchaseKey = ref('')

function stepClass(step) {
  if (step.status === 'complete') return 'bg-emerald-600 text-white'
  if (step.status === 'current') return 'bg-amber-500 text-white'
  return 'bg-surface-gray-2 text-ink-gray-5'
}

function stepLabel(step) {
  if (step.status === 'complete') return 'Complete'
  if (step.status === 'current') return 'In progress'
  return 'Up next'
}

function contractSummary(progress) {
  const contract = progress?.contract
  if (!contract?.required) return 'Contract is being prepared'
  return `${contract.signed} of ${contract.required} signatures complete`
}

function money(value, currency) {
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: currency || 'KES',
    maximumFractionDigits: 0,
  }).format(value || 0)
}

async function startPayment(orderName) {
  try {
    const response = await call(
      'crm.api.customer_experience.start_token_payment',
      { sales_order: orderName },
    )
    const payload =
      response?.message?.data ||
      response?.data ||
      response?.message ||
      response ||
      {}
    if (payload.checkout_url) window.location.href = payload.checkout_url
  } catch (error) {
    errorMessage.value =
      error?.messages?.[0] || 'We could not start payment for this order.'
  }
}

function purchaseFacilities() {
  return (
    context.value.ois?.find((item) => item.name === purchaseOis.value)?.progress
      ?.facilities || []
  )
}

async function buyPackage(item) {
  purchaseMessage.value = ''
  if (!purchaseOis.value || !purchaseFacility.value) {
    purchaseMessage.value =
      'Select the facility that should receive this package.'
    return
  }
  purchaseBusy.value = true
  try {
    if (!purchaseKey.value) purchaseKey.value = crypto.randomUUID()
    const response = await call(
      'crm.api.customer_experience.create_token_order',
      {
        ois_number: purchaseOis.value,
        facility_mfl: purchaseFacility.value,
        package_item_code: item.item_code,
        purchase_key: purchaseKey.value,
      },
    )
    const payload =
      response?.message?.data ||
      response?.data ||
      response?.message ||
      response ||
      {}
    purchaseMessage.value = `Order ${payload.sales_order || 'created'} is ready. Start payment from the facility card below.`
    purchaseKey.value = ''
    const refreshed = await call('crm.api.website_redirect.get_portal_context')
    context.value =
      refreshed?.message?.data ||
      refreshed?.data ||
      refreshed?.message ||
      refreshed ||
      context.value
  } catch (error) {
    purchaseMessage.value =
      error?.messages?.[0] || 'We could not create the token order.'
  } finally {
    purchaseBusy.value = false
  }
}

onMounted(async () => {
  try {
    const response = await call('crm.api.website_redirect.get_portal_context')
    const payload = response?.message || response || {}
    context.value = payload.data || payload
    purchaseOis.value = context.value.ois?.[0]?.name || ''
    purchaseFacility.value = purchaseFacilities()?.[0]?.mfl_code || ''
  } catch (error) {
    errorMessage.value =
      error?.messages?.[0] || 'We could not load your facility portal.'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <main class="min-h-screen bg-[#f6f7f8] text-ink-gray-9">
    <header class="border-b border-outline-gray-2 bg-surface-white">
      <div
        class="mx-auto flex max-w-5xl items-center justify-between px-5 py-4 sm:px-8"
      >
        <div>
          <p class="text-sm font-semibold tracking-tight">tiberbu Express</p>
          <p class="text-xs text-ink-gray-5">Customer Experience</p>
        </div>
        <a
          class="text-sm text-ink-gray-6 underline underline-offset-4 hover:text-ink-gray-9"
          href="/api/method/logout"
          >Sign out</a
        >
      </div>
    </header>

    <div class="mx-auto max-w-5xl px-5 py-10 sm:px-8 sm:py-14">
      <section class="max-w-2xl">
        <p
          class="text-xs font-semibold uppercase tracking-[0.16em] text-ink-gray-5"
        >
          Welcome back
        </p>
        <h1 class="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
          Your facility journey
        </h1>
        <p class="mt-3 text-base leading-7 text-ink-gray-6">
          Review onboarding progress, contract status, and the next action for
          each facility linked to your account.
        </p>
      </section>

      <p v-if="loading" class="mt-8 text-sm text-ink-gray-5" aria-live="polite">
        Loading your secure portal…
      </p>
      <p
        v-else-if="errorMessage"
        class="mt-8 rounded-lg border border-outline-red-2 bg-surface-red-1 px-4 py-3 text-sm text-ink-red-7"
        role="alert"
      >
        {{ errorMessage }}
      </p>
      <section
        v-else-if="!context.ois?.length"
        class="mt-8 max-w-2xl border border-outline-gray-2 bg-surface-white p-6 shadow-sm"
      >
        <p
          class="text-xs font-semibold uppercase tracking-[0.14em] text-ink-gray-5"
        >
          Account setup
        </p>
        <h2 class="mt-2 text-xl font-semibold">
          Your account is not linked yet
        </h2>
        <p class="mt-3 text-sm leading-6 text-ink-gray-6">
          You are signed in securely. Once your facility onboarding record is
          linked, your progress and next actions will appear here.
        </p>
      </section>
      <section v-else class="mt-8 grid gap-4 sm:grid-cols-2">
        <article
          v-for="submission in context.ois"
          :key="submission.name"
          class="border border-outline-gray-2 bg-surface-white p-5 shadow-sm"
        >
          <p
            class="text-xs font-semibold uppercase tracking-[0.14em] text-ink-gray-5"
          >
            Opt-In Request
          </p>
          <h2 class="mt-2 font-mono text-lg font-semibold">
            {{ submission.name }}
          </h2>
          <dl class="mt-5 space-y-3 text-sm">
            <div class="flex justify-between gap-4">
              <dt class="text-ink-gray-5">Status</dt>
              <dd class="font-medium">{{ submission.status || 'Pending' }}</dd>
            </div>
            <div class="flex justify-between gap-4">
              <dt class="text-ink-gray-5">Network</dt>
              <dd class="font-medium">
                {{ submission.network_slug || 'Being confirmed' }}
              </dd>
            </div>
          </dl>
          <div class="mt-6 border-t border-outline-gray-2 pt-5">
            <div class="flex items-center justify-between gap-4">
              <p
                class="text-xs font-semibold uppercase tracking-[0.12em] text-ink-gray-5"
              >
                Progress
              </p>
              <p class="text-xs font-medium text-ink-gray-6">
                {{ submission.progress?.next_action?.label }}
              </p>
            </div>
            <ol class="mt-4 grid gap-3 sm:grid-cols-5">
              <li
                v-for="step in submission.progress?.steps || []"
                :key="step.key"
                class="flex items-center gap-2 text-xs"
              >
                <span
                  class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold"
                  :class="stepClass(step)"
                >
                  {{ step.status === 'complete' ? '✓' : '•' }}
                </span>
                <span>
                  <span class="block font-medium text-ink-gray-8">{{
                    step.label
                  }}</span>
                  <span class="block text-ink-gray-5">{{
                    stepLabel(step)
                  }}</span>
                </span>
              </li>
            </ol>
          </div>

          <div class="mt-5 rounded-lg bg-surface-gray-1 p-4">
            <div class="flex items-center justify-between gap-3">
              <p class="text-sm font-medium">Implementation status</p>
              <span
                class="rounded-full px-2 py-1 text-xs font-medium"
                :class="
                  submission.progress?.steps?.at(-1)?.status === 'complete'
                    ? 'bg-emerald-100 text-emerald-800'
                    : 'bg-amber-100 text-amber-800'
                "
              >
                {{
                  submission.progress?.steps?.at(-1)?.status === 'complete'
                    ? 'GoLive ready'
                    : 'In progress'
                }}
              </span>
            </div>
            <p class="mt-2 text-sm leading-6 text-ink-gray-6">
              {{ contractSummary(submission.progress) }}. Your Network Contact’s
              GoLive status is shown below.
            </p>
            <div class="mt-3 space-y-2">
              <div
                v-for="facility in submission.progress?.facilities || []"
                :key="facility.mfl_code"
                class="flex items-center justify-between gap-3 rounded-md border border-outline-gray-2 bg-surface-white px-3 py-2 text-xs"
              >
                <span>
                  <span class="block font-medium text-ink-gray-8">{{
                    facility.facility_name
                  }}</span>
                  <span class="text-ink-gray-5"
                    >{{ facility.membership_status }} ·
                    {{ facility.mfl_code }}</span
                  >
                </span>
                <span
                  class="shrink-0 rounded-full px-2 py-1 font-medium"
                  :class="
                    facility.network_contact?.go_live
                      ? 'bg-emerald-100 text-emerald-800'
                      : 'bg-surface-gray-2 text-ink-gray-6'
                  "
                >
                  {{
                    facility.network_contact?.go_live
                      ? 'GoLive'
                      : 'Not yet GoLive'
                  }}
                </span>
              </div>
            </div>
            <div
              v-if="submission.open_invoices?.length"
              class="mt-4 border-t border-outline-gray-2 pt-4"
            >
              <p
                class="text-xs font-semibold uppercase tracking-[0.12em] text-ink-gray-5"
              >
                Open invoices
              </p>
              <div
                v-for="invoice in submission.open_invoices"
                :key="invoice.name"
                class="mt-2 flex items-center justify-between gap-3 rounded-md border border-outline-gray-2 bg-surface-white px-3 py-2 text-xs"
              >
                <span
                  ><span class="block font-medium">{{
                    invoice.invoice_number
                  }}</span
                  ><span class="text-ink-gray-5"
                    >Due {{ invoice.due_date || 'on request' }}</span
                  ></span
                >
                <a
                  :href="`/payment-checkout?ois=${encodeURIComponent(submission.name)}`"
                  class="rounded-md bg-[#bc1823] px-3 py-2 font-semibold text-white"
                  >Pay {{ money(invoice.amount, invoice.currency) }}</a
                >
              </div>
            </div>
            <div
              v-if="submission.open_orders?.length"
              class="mt-4 border-t border-outline-gray-2 pt-4"
            >
              <p
                class="text-xs font-semibold uppercase tracking-[0.12em] text-ink-gray-5"
              >
                Open orders
              </p>
              <div
                v-for="order in submission.open_orders"
                :key="order.name"
                class="mt-2 flex items-center justify-between gap-3 rounded-md border border-outline-gray-2 bg-surface-white px-3 py-2 text-xs"
              >
                <span
                  ><span class="block font-medium">{{ order.name }}</span
                  ><span class="text-ink-gray-5"
                    >{{ order.crm_token_facility_mfl }} ·
                    {{ order.status || 'Open' }}</span
                  ></span
                >
                <button
                  type="button"
                  class="rounded-md bg-[#bc1823] px-3 py-2 font-semibold text-white"
                  @click="startPayment(order.name)"
                >
                  Start payment
                </button>
              </div>
            </div>
          </div>
        </article>
      </section>
      <section
        v-if="!loading && !errorMessage && context.token_packages?.length"
        class="mt-8 rounded-2xl border border-outline-gray-2 bg-surface-white p-5 shadow-sm sm:p-6"
      >
        <div class="flex items-end justify-between gap-4">
          <div>
            <p
              class="text-xs font-semibold uppercase tracking-[0.14em] text-ink-gray-5"
            >
              Token catalogue
            </p>
            <h2 class="mt-2 text-xl font-semibold">
              Choose capacity when you need it
            </h2>
          </div>
          <p class="text-xs text-ink-gray-5">All prices exclude VAT</p>
        </div>
        <div class="mt-5 grid gap-3 sm:grid-cols-2">
          <select
            v-model="purchaseOis"
            class="rounded-lg border border-outline-gray-2 px-3 py-2 text-sm"
            @change="
              purchaseFacility = purchaseFacilities()?.[0]?.mfl_code || ''
            "
          >
            <option
              v-for="item in context.ois"
              :key="item.name"
              :value="item.name"
            >
              {{ item.name }}
            </option></select
          ><select
            v-model="purchaseFacility"
            class="rounded-lg border border-outline-gray-2 px-3 py-2 text-sm"
          >
            <option
              v-for="facility in purchaseFacilities()"
              :key="facility.mfl_code"
              :value="facility.mfl_code"
            >
              {{ facility.facility_name }} · {{ facility.mfl_code }}
            </option>
          </select>
        </div>
        <p
          v-if="purchaseMessage"
          class="mt-3 rounded-lg bg-surface-gray-1 px-3 py-2 text-xs text-ink-gray-6"
        >
          {{ purchaseMessage }}
        </p>
        <div class="mt-5 grid gap-3 md:grid-cols-3">
          <article
            v-for="item in context.token_packages"
            :key="item.item_code"
            class="rounded-xl border border-outline-gray-2 p-4"
          >
            <p class="text-sm font-semibold">
              {{ item.display_name || item.item_code }}
            </p>
            <p class="mt-2 text-base font-semibold">
              {{ money(item.price, item.currency) }}
            </p>
            <p class="mt-2 text-xs leading-5 text-ink-gray-5">
              {{ item.coverage_summary || item.description }}
            </p>
            <button
              class="mt-4 rounded-md bg-[#bc1823] px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
              type="button"
              :disabled="purchaseBusy"
              @click="buyPackage(item)"
            >
              {{ purchaseBusy ? 'Creating order…' : 'Buy this package' }}
            </button>
          </article>
        </div>
      </section>
    </div>
  </main>
</template>
