<template>
  <section
    class="mt-4 rounded-xl border border-outline-gray-2 bg-surface-white p-4 dark:bg-surface-gray-1"
    data-testid="deal-optin-billing"
  >
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <p class="text-sm font-semibold text-ink-gray-9">
          {{ __('Quarterly billing schedule') }}
        </p>
        <p class="mt-0.5 text-xs text-ink-gray-6">
          {{
            __(
              'Orders, invoices and payments for every contract period. Invoices are issued automatically on their date; the customer or a manager can issue them early.',
            )
          }}
        </p>
      </div>
      <Button
        variant="subtle"
        icon-left="refresh-cw"
        :label="__('Refresh')"
        :loading="ledger.loading"
        @click="ledger.reload()"
      />
    </div>

    <p v-if="ledger.error" class="mt-3 text-sm text-ink-red-4">
      {{ errorText(ledger.error) }}
    </p>
    <p v-else-if="!data && ledger.loading" class="mt-3 text-sm text-ink-gray-6">
      {{ __('Loading…') }}
    </p>
    <p v-else-if="!data" class="mt-3 text-sm text-ink-gray-6">
      {{ __('No Opt-In submission is linked to this Deal.') }}
    </p>

    <template v-else>
      <div class="mt-4 grid grid-cols-2 gap-2 lg:grid-cols-5">
        <div
          v-for="tile in tiles"
          :key="tile.key"
          class="rounded-lg bg-surface-gray-1 px-3 py-2 dark:bg-surface-gray-2"
        >
          <p class="text-xs text-ink-gray-6">{{ tile.label }}</p>
          <p class="mt-0.5 text-base font-semibold text-ink-gray-9">
            {{ tile.value }}
          </p>
        </div>
      </div>

      <div
        class="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-outline-gray-2 px-3 py-2"
      >
        <p class="text-sm text-ink-gray-7">
          <template v-if="data.advance.allowed">
            {{
              __('Next to issue: {0}', [
                (data.advance.next || [])
                  .slice(0, count)
                  .map((row) => row.label)
                  .join(', '),
              ])
            }}
          </template>
          <template v-else>{{ data.advance.reason }}</template>
        </p>
        <div
          v-if="data.can_issue && data.advance.allowed"
          class="flex items-center gap-2"
        >
          <select
            v-model.number="count"
            class="rounded border-outline-gray-2 bg-surface-white py-1 text-sm text-ink-gray-8 dark:bg-surface-gray-2"
            :aria-label="__('Periods to issue')"
          >
            <option v-for="n in data.advance.max_periods" :key="n" :value="n">
              {{ n }}
            </option>
          </select>
          <Button
            variant="solid"
            :label="__('Issue now')"
            :loading="issue.loading"
            data-testid="deal-optin-issue"
            @click="issueNow"
          />
        </div>
      </div>

      <div class="mt-3 overflow-x-auto">
        <table class="w-full min-w-[720px] text-left text-sm">
          <thead>
            <tr class="border-b border-outline-gray-2 text-xs text-ink-gray-6">
              <th class="py-2 pr-3 font-medium">{{ __('Period') }}</th>
              <th class="py-2 pr-3 font-medium">{{ __('Invoice date') }}</th>
              <th class="py-2 pr-3 font-medium">{{ __('Due') }}</th>
              <th class="py-2 pr-3 font-medium">{{ __('Status') }}</th>
              <th class="py-2 pr-3 font-medium">{{ __('Documents') }}</th>
              <th class="py-2 text-right font-medium">{{ __('Amount') }}</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="year in data.years" :key="year.year">
              <tr
                v-for="period in year.periods"
                :key="period.billing_key"
                class="border-b border-outline-gray-1 align-top"
              >
                <td class="py-2 pr-3 font-medium text-ink-gray-9">
                  {{ period.label }}
                  <p v-if="period.issued_early" class="text-xs text-ink-gray-6">
                    {{
                      __('Issued early by {0}', [
                        period.issued_by_user || period.issued_by,
                      ])
                    }}
                  </p>
                </td>
                <td class="py-2 pr-3 text-ink-gray-7">
                  {{ period.invoice_date || period.scheduled_date }}
                </td>
                <td class="py-2 pr-3 text-ink-gray-7">{{ period.due_date }}</td>
                <td class="py-2 pr-3">
                  <Badge
                    :label="period.state_label"
                    :theme="themeFor(period.state)"
                    variant="subtle"
                  />
                  <p
                    v-if="period.error"
                    class="mt-1 max-w-xs text-xs text-ink-red-4"
                  >
                    {{ period.error }}
                  </p>
                </td>
                <td class="py-2 pr-3 text-xs">
                  <a
                    v-if="period.sales_order"
                    :href="`/app/sales-order/${period.sales_order}`"
                    target="_blank"
                    class="block text-ink-gray-8 underline"
                    >{{ period.sales_order }}</a
                  >
                  <a
                    v-if="period.sales_invoice"
                    :href="`/app/sales-invoice/${period.sales_invoice}`"
                    target="_blank"
                    class="block text-ink-gray-8 underline"
                    >{{ period.sales_invoice }}</a
                  >
                  <a
                    v-for="payment in period.payments"
                    :key="payment.name"
                    :href="`/app/payment-entry/${payment.name}`"
                    target="_blank"
                    class="block text-ink-gray-8 underline"
                    >{{ payment.name }} · {{ payment.status }}</a
                  >
                </td>
                <td class="py-2 text-right font-medium text-ink-gray-9">
                  {{ fmt(period.amount) }}
                  <p
                    v-if="period.sales_invoice && period.outstanding > 0"
                    class="text-xs font-normal text-ink-gray-6"
                  >
                    {{ __('{0} outstanding', [fmt(period.outstanding)]) }}
                  </p>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Badge, Button, createResource, toast } from 'frappe-ui'

const props = defineProps({
  deal: { type: String, required: true },
})

const count = ref(1)

const ledger = createResource({
  url: 'crm.api.optin_ledger.get_optin_ledger_for_deal',
  params: { deal: props.deal },
  auto: true,
  cache: ['deal-optin-ledger', props.deal],
})
const data = computed(() => ledger.data || null)

const issue = createResource({
  url: 'crm.api.optin_ledger.issue_optin_periods_for_deal',
  onSuccess(result) {
    if (result?.ledger) ledger.setData(result.ledger)
    const issued = result?.issued || []
    toast.success(
      __('{0} invoice(s) issued: {1}', [
        issued.length,
        issued.map((row) => row.sales_invoice).join(', '),
      ]),
    )
    if (result?.error) toast.error(result.error)
    count.value = 1
  },
  onError(error) {
    toast.error(errorText(error))
  },
})

function issueNow() {
  issue.submit({ deal: props.deal, count: count.value })
}

const THEMES = {
  due: 'orange',
  overdue: 'red',
  paid: 'green',
  paid_ahead: 'green',
  needs_attention: 'red',
}
function themeFor(state) {
  return THEMES[state] || 'gray'
}

function fmt(amount) {
  return new Intl.NumberFormat('en-KE', {
    style: 'currency',
    currency: data.value?.currency || 'KES',
    currencyDisplay: 'code',
    maximumFractionDigits: 0,
  }).format(Number(amount) || 0)
}

function errorText(error) {
  return error?.messages?.[0] || error?.message || __('Something went wrong.')
}

const tiles = computed(() => {
  const s = data.value?.summary || {}
  const next = s.next_payment
  return [
    { key: 'contract', label: __('Contract value'), value: fmt(s.contract_total) },
    { key: 'invoiced', label: __('Invoiced'), value: fmt(s.invoiced_total) },
    { key: 'paid', label: __('Paid'), value: fmt(s.paid_total) },
    { key: 'outstanding', label: __('Outstanding'), value: fmt(s.outstanding_total) },
    {
      key: 'next',
      label: __('Next payment'),
      value: next ? `${next.label} · ${next.date}` : __('All paid'),
    },
  ]
})
</script>
