<template>
  <div class="fc-finance-detail pb-6">
    <!-- Loading -->
    <div v-if="loading" class="space-y-4">
      <div class="h-24 bg-surface-gray-2 rounded-xl animate-pulse" />
      <div class="h-64 bg-surface-gray-2 rounded-xl animate-pulse" />
    </div>

    <div
      v-else-if="crud.error.value"
      class="mx-auto max-w-xl rounded-xl border border-red-200 bg-red-50 px-4 py-5 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300"
    >
      <div class="flex items-start gap-2">
        <FcIcon name="alert-circle" :size="18" class="mt-0.5 shrink-0" />
        <div>
          <p class="font-medium">Could not load {{ name }}.</p>
          <p class="mt-1 whitespace-pre-line">{{ crud.error.value }}</p>
          <div class="mt-3 flex gap-3">
            <Button size="sm" variant="outline" theme="gray" @click="load">
              Retry
            </Button>
            <Button size="sm" variant="ghost" theme="gray" @click="$emit('close')">
              Back
            </Button>
          </div>
        </div>
      </div>
    </div>

    <template v-else-if="doc">
      <!-- Error banner -->
      <div
        v-if="crud.error.value"
        class="mb-4 rounded-lg border border-red-300 bg-red-50 text-red-700 dark:bg-red-500/10 dark:border-red-500/30 dark:text-red-400 text-sm px-4 py-3 flex items-start gap-2 whitespace-pre-line"
      >
        <FcIcon name="alert-circle" :size="18" class="mt-0.5 flex-shrink-0" />
        <span>{{ crud.error.value }}</span>
      </div>

      <!-- Document header -->
      <div
        class="rounded-xl border border-outline-gray-1 bg-surface-white shadow-sm overflow-hidden"
      >
        <div class="p-5 sm:p-6 flex flex-col lg:flex-row lg:items-center gap-5">
          <div class="flex items-start gap-3 min-w-0 flex-1">
            <span
              class="flex items-center justify-center w-11 h-11 rounded-xl bg-surface-gray-3 text-ink-gray-7 flex-shrink-0"
            >
              <FcIcon name="receipt" :size="22" />
            </span>
            <div class="min-w-0">
              <div class="flex items-center gap-2.5 flex-wrap">
                <h2 class="text-xl font-bold text-ink-gray-9 truncate">
                  {{ name }}
                </h2>
                <StatusBadge v-if="statusValue" :status="statusValue" />
              </div>
              <p
                v-if="subtitle"
                class="text-sm text-ink-gray-5 mt-0.5 truncate"
              >
                {{ subtitle }}
              </p>
            </div>
          </div>

          <!-- Key amount -->
          <div v-if="keyAmount !== null" class="lg:text-right">
            <p class="text-xs font-medium text-ink-gray-5">
              {{ keyAmountLabel }}
            </p>
            <p class="text-2xl font-bold text-ink-gray-9 tabular-nums">
              {{ formatCurrency(keyAmount, doc.currency) }}
            </p>
          </div>

          <!-- Actions (RBAC-gated, visible-but-disabled) -->
          <div class="flex items-center gap-2 flex-wrap">
            <template v-if="workflowInfo?.transitions?.length">
              <Button
                v-for="transition in workflowInfo.transitions"
                :key="transition.action"
                variant="solid"
                theme="blue"
                :loading="busy"
                :disabled="!canWrite"
                @click="onApplyWorkflow(transition.action)"
              >
                <template #prefix><FcIcon name="check-circle" :size="14" /></template>
                {{ transition.action }}
              </Button>
            </template>
            <Button
              v-if="!isDetailReadOnly"
              variant="outline"
              theme="gray"
              :disabled="!canWrite || isCancelled"
              :title="!canWrite ? 'No permission to edit' : ''"
              @click="canWrite && !isCancelled && $emit('edit')"
            >
              <template #prefix><FcIcon name="edit" :size="14" /></template>
              Edit
            </Button>
            <Button
              v-if="(!workflowInfo || !workflowInfo.has_workflow) && isSubmittable && docstatus === 0 && (!readOnly || allowLifecycleActions)"
              theme="green"
              variant="subtle"
              :loading="busy"
              :disabled="!canSubmit"
              :title="!canSubmit ? 'No permission to submit' : ''"
              @click="onSubmit"
            >
              <template #prefix><FcIcon name="send" :size="14" /></template>
              Submit
            </Button>
            <Button
              v-if="(!workflowInfo || !workflowInfo.has_workflow) && isSubmittable && docstatus === 1 && (!readOnly || allowLifecycleActions)"
              theme="gray"
              variant="outline"
              :loading="busy"
              :disabled="!canCancel"
              :title="!canCancel ? 'No permission to cancel' : ''"
              @click="onCancel"
            >
              <template #prefix><FcIcon name="x" :size="14" /></template>
              Cancel
            </Button>
            <Button
              v-if="doctype === 'Sales Order' && docstatus === 1 && !invoiceState.hasInvoice"
              theme="blue"
              variant="solid"
              :loading="busy || invoiceStateLoading"
              :disabled="!canWrite || invoiceStateLoading || !!invoiceStateError"
              :title="
                invoiceStateError
                  ? 'Verify the existing invoice state before generating'
                  : !canWrite
                    ? 'Requires Accounts User or Accounts Manager'
                    : ''
              "
              @click="canWrite && onGenerateInvoice()"
            >
              <template #prefix><FcIcon name="file-plus" :size="14" /></template>
              Generate invoice
            </Button>
            <Button
              v-if="doctype === 'Quotation' && docstatus === 1"
              theme="blue"
              variant="solid"
              :loading="busy || mapping"
              :disabled="!canWrite || mapping"
              :title="!canWrite ? 'Requires Accounts User or Accounts Manager' : ''"
              @click="canWrite && onMakeSalesOrder()"
            >
              <template #prefix><FcIcon name="copy-plus" :size="14" /></template>
              Make order
            </Button>
            <Button
              v-if="doctype === 'Sales Invoice' && docstatus === 1 && Number(doc.outstanding_amount || 0) > 0"
              theme="blue"
              variant="solid"
              :loading="busy || mapping"
              :disabled="!canWrite || mapping"
              :title="!canWrite ? 'Requires Accounts User or Accounts Manager' : ''"
              @click="canWrite && onMakePayment()"
            >
              <template #prefix><FcIcon name="banknote" :size="14" /></template>
              Create payment
            </Button>
            <Button variant="outline" theme="gray" @click="printDoc">
              <template #prefix><FcIcon name="printer" :size="14" /></template>
              Print
            </Button>
            <Button variant="outline" theme="gray" @click="showSendDialog = true">
              <template #prefix><FcIcon name="mail" :size="14" /></template>
              Email copy
            </Button>
            <Button
              v-if="!isDetailReadOnly"
              theme="red"
              variant="subtle"
              :loading="busy"
              :disabled="!canDelete"
              :title="!canDelete ? 'No permission to delete' : ''"
              @click="onDelete"
            >
              <template #prefix><FcIcon name="trash" :size="14" /></template>
              Delete
            </Button>
          </div>
        </div>

        <!-- FC-13: Explicit summary strip -->
        <div
          class="border-t border-outline-gray-1 bg-surface-gray-1 px-5 sm:px-6 py-3 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4"
        >
          <div
            v-for="fact in summaryFacts"
            :key="fact.fieldname"
            class="min-w-0"
          >
            <dt
              class="text-[11px] font-medium text-ink-gray-5 uppercase tracking-wide"
            >
              {{ fact.label }}
            </dt>
            <dd
              class="text-sm font-medium mt-0.5 truncate"
              :class="[
                fact.numeric ? 'tabular-nums' : '',
                fact.color || 'text-ink-gray-8',
              ]"
            >
              {{ fact.display }}
            </dd>
            <dd
              v-if="fact.subLabel"
              class="text-xs mt-0.5"
              :class="fact.subColor || 'text-ink-gray-4'"
            >
              {{ fact.subLabel }}
            </dd>
          </div>
        </div>
      </div>

      <!-- Detail sections -->
      <div class="mt-5 space-y-5">
        <SectionCard
          v-if="doctype === 'Quotation'"
          title="Facility and Network context"
          icon="building-2"
          tone="neutral"
        >
          <div v-if="quotationContextLoading" class="space-y-2">
            <div class="h-8 rounded bg-surface-gray-2 animate-pulse" />
            <div class="h-8 rounded bg-surface-gray-2 animate-pulse" />
          </div>
          <div v-else-if="quotationContextError" class="text-sm text-ink-red-6" role="alert">
            {{ quotationContextError }}
            <button class="ml-2 underline font-medium" @click="loadQuotationContext">Retry</button>
          </div>
          <div v-else-if="quotationContext" class="space-y-4">
            <div class="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-lg bg-surface-gray-1 px-3 py-2 text-sm">
              <span><span class="text-ink-gray-5">Quote total</span> <strong class="ml-1 text-ink-gray-8">{{ formatCurrency(quotationContext.quotation?.grand_total, quotationContext.quotation?.currency) }}</strong></span>
              <span><span class="text-ink-gray-5">Quote state</span> <strong class="ml-1 text-ink-gray-8">{{ quotationContext.quotation?.finance_state || 'Unavailable' }}</strong></span>
              <span><span class="text-ink-gray-5">Handoff</span> <strong class="ml-1 text-ink-gray-8">{{ quotationContext.handoff_state || 'Unavailable' }}</strong></span>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 text-sm">
              <div>
                <p class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">Company</p>
                <p class="mt-1 font-medium text-ink-gray-8">{{ quotationContext.company || 'Unavailable' }}</p>
              </div>
              <div>
                <p class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">Customer</p>
                <a
                  v-if="quotationContext.customer?.available && contextHref('Customer', quotationContext.customer?.name)"
                  :href="contextHref('Customer', quotationContext.customer?.name)"
                  class="mt-1 inline-block font-medium text-ink-gray-8 underline underline-offset-2"
                >{{ quotationContext.customer?.label || quotationContext.customer?.name }}</a>
                <p v-else class="mt-1 text-ink-gray-6">{{ quotationContext.customer?.label || 'Unavailable' }}</p>
              </div>
              <div>
                <p class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">Opt-In Network · contracting and billing</p>
                <a
                  v-if="quotationContext.network?.available && contextHref('CRM Opt-In Network', quotationContext.network?.name)"
                  :href="contextHref('CRM Opt-In Network', quotationContext.network?.name)"
                  class="mt-1 inline-block font-medium text-ink-gray-8 underline underline-offset-2"
                >{{ quotationContext.network?.label }}</a>
                <p v-else class="mt-1 text-ink-gray-6">{{ quotationContext.network?.label || 'Not linked' }} · record unavailable</p>
                <p v-if="quotationContext.network?.partner_id" class="text-xs text-ink-gray-5">Partner ID {{ quotationContext.network.partner_id }}</p>
              </div>
            </div>

            <div class="border-t border-outline-gray-1 pt-3">
              <p class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">Originating Facilities</p>
              <div v-if="quotationContext.facilities?.length" class="mt-2 flex flex-wrap gap-2">
                <template v-for="facility in quotationContext.facilities" :key="facility.mfl_code || facility.label">
                  <a
                    v-if="facility.available"
                    :href="contextHref('CRM Pre-Qualified Facility', facility.name)"
                    class="rounded-md border border-outline-gray-1 px-2.5 py-1.5 text-sm text-ink-gray-7 underline underline-offset-2"
                  >{{ facility.label }}<span v-if="facility.mfl_code" class="ml-1 text-xs text-ink-gray-5">· {{ facility.mfl_code }}</span></a>
                  <span v-else class="rounded-md border border-outline-gray-1 px-2.5 py-1.5 text-sm text-ink-gray-7">
                    {{ facility.label }}<span v-if="facility.mfl_code" class="ml-1 text-xs text-ink-gray-5">· {{ facility.mfl_code }}</span><span class="ml-1 text-xs text-ink-gray-5">· record unavailable</span>
                  </span>
                </template>
              </div>
              <p v-else class="mt-1 text-sm text-ink-gray-5">Facility details are unavailable in the saved Opt-In record.</p>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 border-t border-outline-gray-1 pt-3 text-sm">
              <div>
                <p class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">Opt-In submission</p>
                <a
                  v-if="quotationContext.submission?.available"
                  :href="contextHref('CRM Opt-In Submission', quotationContext.submission.name)"
                  class="mt-1 inline-block font-medium text-ink-gray-8 underline underline-offset-2"
                >{{ quotationContext.submission.name }}</a>
                <p v-else class="mt-1 text-ink-gray-6">{{ quotationContext.submission?.name || 'Not linked' }} · record unavailable</p>
                <StatusBadge v-if="quotationContext.submission?.status" :status="quotationContext.submission.status" class="mt-1" />
              </div>
              <div>
                <p class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">Facility contract</p>
                <a
                  v-if="quotationContext.contract?.available"
                  :href="contextHref('CRM Contract', quotationContext.contract.name)"
                  class="mt-1 inline-block font-medium text-ink-gray-8 underline underline-offset-2"
                >{{ quotationContext.contract.name }}</a>
                <p v-else class="mt-1 text-ink-gray-6">{{ quotationContext.contract?.name || 'Not created' }} · record unavailable</p>
                <p class="text-xs text-ink-gray-5">{{ quotationContext.contract?.status || 'Status unavailable' }}<span v-if="quotationContext.contract?.signed_at"> · Facility signed {{ quotationContext.contract.signed_at }}</span></p>
              </div>
            </div>

            <div class="border-t border-outline-gray-1 pt-3">
              <p class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">Billing schedule and handoff</p>
              <div class="mt-2 grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
                <div><p class="text-xs text-ink-gray-5">Order date</p><p class="mt-0.5 text-ink-gray-8">{{ quotationContext.schedule?.order_date || '—' }}</p></div>
                <div><p class="text-xs text-ink-gray-5">Invoice timing</p><p class="mt-0.5 text-ink-gray-8">{{ quotationContext.schedule?.issue_timing || 'Network schedule unavailable' }}</p></div>
                <div><p class="text-xs text-ink-gray-5">Invoice date</p><p class="mt-0.5 text-ink-gray-8">{{ quotationContext.schedule?.invoice_date || 'Not scheduled' }}</p></div>
                <div><p class="text-xs text-ink-gray-5">Due date</p><p class="mt-0.5 text-ink-gray-8">{{ quotationContext.schedule?.due_date || '—' }}</p></div>
              </div>
              <p v-if="quotationContext.schedule?.error || quotationContext.schedule?.handoff_note" class="mt-2 text-sm text-ink-gray-6">{{ quotationContext.schedule.error || quotationContext.schedule.handoff_note }}</p>
            </div>

            <div class="border-t border-outline-gray-1 pt-3">
              <p class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">Linked finance records</p>
              <div class="mt-2 flex flex-wrap gap-x-4 gap-y-2 text-sm">
                <template v-for="record in quotationContext.sales_orders || []" :key="`order-${record.name}`">
                  <a :href="contextHref('Sales Order', record.name, quotationContext.company)" class="font-medium text-ink-gray-8 underline underline-offset-2">Sales Order {{ record.name }} · {{ record.status || 'Draft' }} · {{ formatCurrency(record.grand_total, record.currency) }}</a>
                </template>
                <template v-for="record in quotationContext.sales_invoices || []" :key="`invoice-${record.name}`">
                  <a :href="contextHref('Sales Invoice', record.name, quotationContext.company)" class="font-medium text-ink-gray-8 underline underline-offset-2">Sales Invoice {{ record.name }} · {{ record.status || 'Draft' }} · {{ formatCurrency(record.grand_total, record.currency) }} · outstanding {{ formatCurrency(record.outstanding_amount, record.currency) }}</a>
                </template>
                <template v-for="record in quotationContext.payments || []" :key="`payment-${record.name}`">
                  <a :href="contextHref('Payment Entry', record.name, quotationContext.company)" class="font-medium text-ink-gray-8 underline underline-offset-2">Payment Entry {{ record.name }} · {{ record.finance_state || record.workflow_state || 'Draft' }} · {{ record.posting_date || 'No date' }} · {{ formatCurrency(record.paid_amount, record.payment_type === 'Receive' ? record.paid_to_account_currency : record.paid_from_account_currency) }}</a>
                </template>
                <span v-if="!quotationContext.sales_orders?.length && !quotationContext.sales_invoices?.length && !quotationContext.payments?.length" class="text-ink-gray-5">No Sales Order, invoice, or payment has been created yet.</span>
              </div>
            </div>
          </div>
          <p v-else class="text-sm text-ink-gray-5">Quotation context is unavailable.</p>
        </SectionCard>

        <SectionCard
          v-if="doctype === 'Sales Order'"
          title="Billing"
          icon="receipt"
          tone="neutral"
        >
          <div class="flex flex-wrap items-center gap-3 text-sm">
            <span v-if="invoiceStateLoading" class="text-ink-gray-5">
              Checking for an existing invoice…
            </span>
            <div v-else-if="invoiceStateError" class="text-ink-red-6" role="alert">
              <span>{{ invoiceStateError }}</span>
              <button class="ml-2 underline font-medium" @click="loadInvoiceState">
                Retry
              </button>
            </div>
            <template v-else-if="invoiceState.hasInvoice">
              <span class="text-ink-gray-6">Invoice already generated:</span>
              <a
                v-for="invoiceName in invoiceState.invoiceNames"
                :key="invoiceName"
                :href="contextHref('Sales Invoice', invoiceName, doc?.company)"
                class="font-medium text-ink-gray-8 underline underline-offset-2"
              >
                {{ invoiceName }}
              </a>
            </template>
            <span v-else class="text-ink-gray-6">
              No invoice generated from this order yet.
            </span>
          </div>
        </SectionCard>

        <SectionCard
          v-if="doctype === 'Sales Invoice'"
          title="Payment history"
          icon="banknote"
          tone="positive"
        >
          <div v-if="paymentHistoryLoading" class="space-y-2">
            <div v-for="n in 3" :key="n" class="h-9 rounded bg-surface-gray-2 animate-pulse" />
          </div>
          <div v-else-if="paymentHistoryError" class="text-sm text-ink-red-6" role="alert">
            {{ paymentHistoryError }}
            <button class="ml-2 underline font-medium" @click="loadPaymentHistory">Retry</button>
          </div>
          <div v-else-if="!paymentHistory.length" class="text-sm text-ink-gray-5">
            No submitted payments have been allocated to this invoice.
          </div>
          <div v-else class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b border-outline-gray-1 text-left text-xs uppercase tracking-wide text-ink-gray-5">
                  <th class="py-2 pr-3">Payment</th>
                  <th class="py-2 pr-3">Date</th>
                  <th class="py-2 pr-3">Mode</th>
                  <th class="py-2 text-right">Allocated</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="payment in paymentHistory" :key="payment.name" class="border-b border-outline-gray-1 last:border-0">
                  <td class="py-2 pr-3">
                    <a :href="contextHref('Payment Entry', payment.name, doc?.company)" class="font-medium text-ink-gray-8 underline underline-offset-2">{{ payment.name }}</a>
                    <div v-if="payment.reference_no" class="text-xs text-ink-gray-4">{{ payment.reference_no }}</div>
                  </td>
                  <td class="py-2 pr-3 text-ink-gray-6">{{ payment.posting_date || '—' }}</td>
                  <td class="py-2 pr-3 text-ink-gray-6">{{ payment.mode_of_payment || '—' }}</td>
                  <td class="py-2 text-right tabular-nums text-ink-gray-8">{{ formatCurrency(payment.allocated_amount, doc.currency) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="mt-3 flex flex-wrap justify-between gap-2 border-t border-outline-gray-1 pt-3 text-sm">
            <span class="text-ink-gray-5">Outstanding balance</span>
            <strong class="tabular-nums text-ink-gray-9">{{ formatCurrency(doc.outstanding_amount, doc.currency) }}</strong>
          </div>
        </SectionCard>

        <template v-for="sec in layout.sections" :key="sec.key">
          <!-- Line items / taxes -->
          <SectionCard
            v-if="sec.kind === 'lineItems' || sec.kind === 'taxes'"
            :title="sec.title"
            :icon="sec.icon"
            :tone="sec.kind === 'lineItems' ? 'positive' : 'pending'"
            :badge="(doc[sec.tableField] || []).length || ''"
          >
            <LineItemsGrid
              :columns="sec.columns"
              :rows="doc[sec.tableField] || []"
              :currency="doc.currency"
              :read-only="true"
              :qty-field="sec.kind === 'lineItems' ? sec.qtyField : ''"
              :rate-field="sec.kind === 'lineItems' ? sec.rateField : ''"
              :amount-field="sec.kind === 'lineItems' ? sec.amountField : ''"
            />
          </SectionCard>

          <!-- Summary -->
          <SectionCard
            v-else-if="sec.kind === 'summary'"
            :title="sec.title"
            :icon="sec.icon"
            tone="positive"
          >
            <SummaryBar
              :subtotal="subtotal"
              :tax="taxTotal"
              :grand-total="grandTotal"
              :currency="doc.currency"
              :tax-rows="doc[layout.totals?.taxRowsField] || null"
              :notes="doc[layout.remarksField] || ''"
              :notes-label="layout.remarksLabel"
              :show-notes="!!layout.remarksField"
              :read-only="true"
            />
          </SectionCard>
        </template>

        <!-- Configured scalar details -->
        <SectionCard
          v-if="detailFields.length"
          title="Details"
          icon="file-text"
          tone="neutral"
        >
          <dl
            class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-4"
          >
            <div
              v-for="f in detailFields"
              :key="f.fieldname"
              class="flex flex-col min-w-0"
            >
              <dt class="text-xs font-medium text-ink-gray-5">{{ f.label }}</dt>
              <dd
                class="text-sm text-ink-gray-8 mt-0.5 truncate"
                :class="isNum(f) ? 'tabular-nums' : ''"
              >
                <template v-if="f.type === 'check'">{{
                  doc[f.fieldname] ? 'Yes' : 'No'
                }}</template>
                <template v-else-if="f.type === 'currency'">{{
                  formatCurrency(doc[f.fieldname], doc.currency)
                }}</template>
                <a
                  v-else-if="isFinanceNetworkField(f) && financeNetworkHref(f)"
                  :href="financeNetworkHref(f)"
                  class="underline underline-offset-2 hover:text-ink-gray-9"
                >{{ displayVal(doc[f.fieldname]) }}</a>
                <a
                  v-else-if="doctype === 'Payment Entry' && f.type === 'link' && doc[f.fieldname] && paymentFieldHref(f)"
                  :href="paymentFieldHref(f)"
                  class="underline underline-offset-2 hover:text-ink-gray-9"
                >{{ displayVal(doc[f.fieldname]) }}</a>
                <template v-else>{{ displayVal(doc[f.fieldname]) }}</template>
              </dd>
            </div>
          </dl>
        </SectionCard>

        <!-- FC-14: Related documents panel -->
        <SectionCard
          v-if="relatedItems.length"
          title="Related"
          icon="link"
          tone="neutral"
        >
          <div class="flex flex-wrap gap-2">
            <a
              v-for="item in relatedItems"
              :key="item.href"
              :href="item.href"
              class="inline-flex items-center gap-1.5 text-xs font-medium text-ink-gray-7 border border-outline-gray-2 rounded-lg px-3 py-1.5 hover:bg-surface-gray-1 hover:text-ink-gray-9 transition-colors"
            >
              <FcIcon :name="item.icon" :size="13" />
              {{ item.label }}
            </a>
          </div>
        </SectionCard>

        <!-- FC-14: Payment Entry references (invoice allocations) -->
        <SectionCard
          v-if="doctype === 'Payment Entry'"
          title="Referenced Documents"
          icon="receipt"
          tone="positive"
          :badge="paymentRefs.length"
        >
          <div v-if="paymentRefs.length" class="divide-y divide-outline-gray-1">
            <div
              v-for="paymentRef in paymentRefs"
              :key="`${paymentRef.reference_doctype || 'unknown'}:${paymentRef.reference_name || 'missing'}`"
              class="flex flex-wrap items-center justify-between gap-3 py-2"
            >
              <div class="min-w-0">
                <a
                  v-if="paymentRefHref(paymentRef)"
                  :href="paymentRefHref(paymentRef)"
                  class="text-sm font-medium text-ink-gray-8 underline underline-offset-2 hover:text-ink-gray-9"
                >
                  {{ paymentRef.reference_name }}
                </a>
                <span v-else class="text-sm font-medium text-ink-gray-6">
                  {{ paymentRef.reference_name || 'Reference unavailable' }}
                </span>
                <p class="text-xs text-ink-gray-5">
                  {{ paymentRef.reference_doctype || 'Unknown document type' }}
                  <span v-if="!paymentRefHref(paymentRef)"> · Native record link unavailable</span>
                </p>
              </div>
              <span class="text-sm tabular-nums text-ink-gray-6">{{
                formatCurrency(paymentRef.allocated_amount, doc.currency)
              }}</span>
            </div>
          </div>
          <p v-else class="text-sm text-ink-gray-5">
            This Payment Entry has no allocated document references.
          </p>
        </SectionCard>
      </div>
    </template>
    <SendDocumentDialog
      v-if="doc"
      v-model:open="showSendDialog"
      :doctype="doctype"
      :name="name"
      :doc="doc"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { Button, toast, dialog, createResource } from 'frappe-ui'
import StatusBadge from './StatusBadge.vue'
import SectionCard from './SectionCard.vue'
import SummaryBar from './SummaryBar.vue'
import LineItemsGrid from './LineItemsGrid.vue'
import FcIcon from './FcIcon.vue'
import SendDocumentDialog from './SendDocumentDialog.vue'
import { useCrud, readableError } from '../../composables/useCrud.js'
import { useCurrency } from '../../composables/useCurrency.js'
import { useBoot } from '../../composables/useBoot.js'
import { useCompanyContext } from '../../composables/useCompanyContext.js'
import { cockpitRecordHref } from '../../composables/useFinanceNavigation.js'
import { resolveLayout, isNumericType } from '../../constants/formLayouts.js'
import { printUrl } from '../../constants/printFormats.js'
import { useMappedDoc } from '../../composables/useMappedDoc.js'

const props = defineProps({
  doctype: { type: String, required: true },
  name: { type: String, required: true },
  readOnly: { type: Boolean, default: false },
  allowLifecycleActions: { type: Boolean, default: false },
})

const emit = defineEmits(['edit', 'mapped', 'deleted', 'close'])

const crud = useCrud(props.doctype)
const { formatCurrency } = useCurrency()
const { getRoles, isAdministrator } = useBoot()
const { company } = useCompanyContext()

const layout = resolveLayout(props.doctype)
const doc = ref(null)
const loading = ref(true)
const busy = ref(false)
const invoiceState = ref({ hasInvoice: false, invoiceNames: [] })
const invoiceStateLoading = ref(false)
const invoiceStateError = ref('')
const invoiceStateResource = createResource({
  url: 'crm.finance.api.get_sales_order_invoice_state',
})
const quotationContextResource = createResource({
  url: 'crm.finance.api.get_quotation_finance_context',
})
const paymentHistoryResource = createResource({
  url: 'crm.finance.api.get_sales_invoice_payments',
})
const generateInvoiceResource = createResource({
  url: 'crm.finance.api.make_sales_invoice_from_order',
})
const workflowTransitionsResource = createResource({
  url: 'crm.finance.api.get_document_workflow_transitions',
})
const applyWorkflowResource = createResource({
  url: 'crm.finance.api.apply_document_workflow_action',
})
const workflowInfo = ref(null)
const paymentHistory = ref([])
const paymentHistoryLoading = ref(false)
const paymentHistoryError = ref('')
const quotationContext = ref(null)
const quotationContextLoading = ref(false)
const quotationContextError = ref('')
const showSendDialog = ref(false)
const mapping = ref(false)
const { mapDoc } = useMappedDoc()

/* ---- Header facets ---- */
const statusValue = computed(() => doc.value?.[layout.statusField] || '')
const isSubmittable = computed(() => layout.isSubmittable)
const docstatus = computed(() => Number(doc.value?.docstatus || 0))
const isCancelled = computed(() => docstatus.value === 2)
const isDetailReadOnly = computed(
  () => props.readOnly || props.doctype === 'Payment Entry',
)

const subtitle = computed(() => {
  const d = doc.value
  if (!d) return ''
  return d.customer || d.supplier || d.party || d.title || ''
})

const totalsCfg = computed(() => layout.totals)
const keyAmountLabel = computed(() =>
  isSubmittable.value ? 'Grand Total' : 'Amount',
)
const keyAmount = computed(() => {
  const d = doc.value
  if (!d) return null
  if (d.grand_total != null) return d.grand_total
  if (d.outstanding_amount != null) return d.outstanding_amount
  if (d.total != null) return d.total
  return null
})

const subtotal = computed(() => {
  const cfg = totalsCfg.value
  const d = doc.value
  if (!cfg || !d) return 0
  if (d[cfg.subtotalField] != null) return Number(d[cfg.subtotalField])
  const rows = d[cfg.lineItemsField] || []
  return rows.reduce(
    (s, r) => s + Number(r[cfg.qtyField] ?? 0) * Number(r[cfg.rateField] ?? 0),
    0,
  )
})
const taxTotal = computed(() => {
  const cfg = totalsCfg.value
  const d = doc.value
  if (!cfg || !d) return 0
  if (d[cfg.taxTotalField] != null) return Number(d[cfg.taxTotalField])
  const rows = d[cfg.taxRowsField] || []
  return rows.reduce((s, r) => s + Number(r[cfg.taxAmountField] ?? 0), 0)
})
const grandTotal = computed(() => {
  const cfg = totalsCfg.value
  const d = doc.value
  if (cfg && d && d[cfg.grandTotalField] != null)
    return Number(d[cfg.grandTotalField])
  return subtotal.value + taxTotal.value
})

/* ---- FC-13: Explicit summary strip ---- */
const TODAY = new Date().toISOString().slice(0, 10)

const summaryFacts = computed(() => {
  const d = doc.value
  if (!d) return []

  // Use explicit summaryFields list from layout if provided; otherwise fall back
  // to first-5 scalar fields (excluding check/textarea) as before.
  const fieldNames = layout.summaryFields
  if (fieldNames) {
    return fieldNames
      .map((fn) => buildFact(fn, d))
      .filter((fact) => {
        if (!fact) return false
        if (
          props.doctype === 'Payment Entry' &&
          ['party_type', 'party'].includes(fact.fieldname) &&
          !d[fact.fieldname]
        ) {
          return false
        }
        return true
      })
  }

  const fields = []
  for (const sec of layout.sections) {
    if (sec.kind === 'fields') fields.push(...(sec.fields || []))
  }
  return fields
    .filter((f) => f.type !== 'check' && f.type !== 'textarea')
    .slice(0, 5)
    .map((f) => buildFact(f.fieldname, d))
    .filter(Boolean)
})

function buildFact(fieldname, d) {
  // Gather field meta from layout.
  const allFields = []
  for (const sec of layout.sections) {
    if (sec.kind === 'fields') allFields.push(...(sec.fields || []))
  }
  const fieldMeta = allFields.find((f) => f.fieldname === fieldname)
  const label = paymentFieldLabel(fieldname, d) || fieldMeta?.label || fieldname
  const type = fieldMeta?.type || 'data'
  const val = d[fieldname]

  let display = displayVal(val)
  let color = null
  let subLabel = null
  let subColor = null

  if (type === 'currency') {
    display = formatCurrency(val, d.currency)
  }

  // FC-13: paid-in-full indicator on outstanding_amount.
  if (fieldname === 'outstanding_amount' && Number(val ?? -1) === 0) {
    display = 'Paid in Full'
    color = 'text-ink-green-6'
  }

  // FC-13: "X days overdue" sub-label on due_date.
  if (fieldname === 'due_date' && val && val < TODAY && docstatus.value === 1) {
    const days = Math.floor((new Date(TODAY) - new Date(val)) / 86400000)
    subLabel = days + (days === 1 ? ' day overdue' : ' days overdue')
    subColor = 'text-red-500 dark:text-red-400'
  }

  return {
    fieldname,
    label,
    numeric: isNumericType(type),
    display,
    color,
    subLabel,
    subColor,
  }
}

// Configured scalar fields not already shown in the summary strip.
const detailFields = computed(() => {
  if (!doc.value) return []
  const shownNames = new Set(summaryFacts.value.map((f) => f.fieldname))
  if (layout.remarksField) shownNames.add(layout.remarksField)
  const seen = new Set()
  const out = []
  for (const sec of layout.sections) {
    if (sec.kind !== 'fields') continue
    for (const f of sec.fields || []) {
      if (shownNames.has(f.fieldname) || seen.has(f.fieldname)) continue
      seen.add(f.fieldname)
      const v = doc.value[f.fieldname]
      if (!paymentFieldIsVisible(f.fieldname, doc.value)) continue
      if (v === null || v === undefined || v === '') continue
      out.push(
        props.doctype === 'Payment Entry'
          ? { ...f, label: paymentFieldLabel(f.fieldname, doc.value) || f.label }
          : f,
      )
    }
  }
  return out
})

/* ---- FC-14: Related documents ---- */
const relatedItems = computed(() => {
  const d = doc.value
  if (!d) return []
  const items = []

  if (props.doctype === 'Sales Invoice') {
    if (d.crm_deal) {
      const dealHref = cockpitRecordHref('CRM Deal', d.crm_deal, d.company)
      if (dealHref) {
        items.push({
          label: 'View Deal →',
          icon: 'briefcase',
          href: dealHref,
        })
      }
    }
    if (d.crm_quotation) {
      const quoteHref = cockpitRecordHref('Quotation', d.crm_quotation, d.company)
      if (quoteHref) {
        items.push({
          label: 'View Quote →',
          icon: 'file-text',
          href: quoteHref,
        })
      }
    }
  }

  return items
})

// Payment Entry references from the native child table.
const paymentRefs = computed(() => {
  if (props.doctype !== 'Payment Entry') return []
  return doc.value?.references || []
})

function paymentFieldLabel(fieldname, payment) {
  if (props.doctype !== 'Payment Entry') return ''
  if (fieldname === 'party') return payment?.party_type || 'Party'
  if (fieldname === 'paid_from') {
    return payment?.payment_type === 'Internal Transfer'
      ? 'Source Account'
      : 'Paid From Account'
  }
  if (fieldname === 'paid_to') {
    return payment?.payment_type === 'Internal Transfer'
      ? 'Destination Account'
      : 'Paid To Account'
  }
  return ''
}

function paymentFieldIsVisible(fieldname, payment) {
  if (props.doctype !== 'Payment Entry') return true
  if (fieldname === 'party' || fieldname === 'party_type') {
    return payment?.payment_type !== 'Internal Transfer' && !!payment?.party
  }
  if (fieldname === 'paid_from') {
    return payment?.payment_type !== 'Receive' || !!payment?.paid_from
  }
  if (fieldname === 'paid_to') {
    return payment?.payment_type !== 'Pay' || !!payment?.paid_to
  }
  return true
}

function paymentFieldHref(field) {
  const payment = doc.value
  let doctype = field.options
  if (field.fieldname === 'party') doctype = payment?.party_type
  return nativePaymentDocHref(doctype, payment?.[field.fieldname], payment?.company)
}

function isFinanceNetworkField(field) {
  return (
    field?.fieldname === 'optin_network' &&
    ['CRM Partner Rebate Voucher', 'CRM Sales Commission'].includes(props.doctype)
  )
}

function financeNetworkHref(field) {
  const network = doc.value?.[field?.fieldname]
  const linkCompany = doc.value?.company || company.value
  return nativePaymentDocHref('CRM Opt-In Network', network, linkCompany)
}

function paymentRefHref(reference) {
  return nativePaymentDocHref(
    reference?.reference_doctype,
    reference?.reference_name,
    doc.value?.company,
  )
}

function nativePaymentDocHref(doctype, name, recordCompany) {
  return cockpitRecordHref(doctype, name, recordCompany)
}

function isNum(f) {
  return isNumericType(f.type)
}
function displayVal(v) {
  return v === null || v === undefined || v === '' ? '—' : v
}

/* ---- RBAC ---- */
const roles = computed(() => getRoles())
const isElevated = computed(
  () =>
    isAdministrator() ||
    roles.value.includes('Accounts Manager'),
)
const canWrite = computed(
  () => isElevated.value || roles.value.includes('Accounts User'),
)
const canSubmit = computed(() => canWrite.value)
const canCancel = computed(() => isElevated.value)
const canDelete = computed(() => isElevated.value)

/* ---- Data ---- */
async function load() {
  loading.value = true
  try {
    doc.value = await crud.loadDoc(props.name)
    await loadInvoiceState()
    await loadPaymentHistory()
    await loadQuotationContext()
    await loadWorkflowTransitions()
  } finally {
    loading.value = false
  }
}

async function loadWorkflowTransitions() {
  try {
    workflowInfo.value = await workflowTransitionsResource.submit({
      doctype: props.doctype,
      name: props.name,
    })
  } catch {
    workflowInfo.value = null
  }
}

async function onApplyWorkflow(action) {
  busy.value = true
  try {
    await applyWorkflowResource.submit({
      doctype: props.doctype,
      name: props.name,
      action,
    })
    toast.success(`Workflow action "${action}" applied successfully`)
    await load()
  } catch (err) {
    toast.error(readableError(err) || `Failed to apply workflow action "${action}"`)
  } finally {
    busy.value = false
  }
}

async function loadQuotationContext() {
  if (props.doctype !== 'Quotation') return
  quotationContextLoading.value = true
  quotationContextError.value = ''
  try {
    quotationContext.value = await quotationContextResource.submit({
      quotation_name: props.name,
      company: doc.value?.company,
    })
  } catch (err) {
    quotationContext.value = null
    quotationContextError.value = readableError(err) || 'Could not load the quotation handoff context.'
  } finally {
    quotationContextLoading.value = false
  }
}

function contextHref(doctype, name, company = quotationContext.value?.company) {
  return nativePaymentDocHref(doctype, name, company)
}

async function loadPaymentHistory() {
  if (props.doctype !== 'Sales Invoice') return
  paymentHistoryLoading.value = true
  paymentHistoryError.value = ''
  try {
    paymentHistory.value =
      (await paymentHistoryResource.submit({
        invoice_name: props.name,
        company: doc.value?.company,
      })) || []
  } catch (err) {
    paymentHistory.value = []
    paymentHistoryError.value = readableError(err) || 'Could not load payment history.'
  } finally {
    paymentHistoryLoading.value = false
  }
}
onMounted(load)
watch(() => [props.doctype, props.name], load)

async function loadInvoiceState() {
  if (props.doctype !== 'Sales Order') return
  invoiceStateLoading.value = true
  invoiceStateError.value = ''
  try {
    const result = await invoiceStateResource.submit({
      order_name: props.name,
      company: doc.value?.company,
    })
    invoiceState.value = {
      hasInvoice: !!result?.has_invoice,
      invoiceNames: result?.invoice_names || [],
    }
  } catch (err) {
    invoiceStateError.value =
      readableError(err) ||
      'Could not verify whether this order already has an invoice.'
  } finally {
    invoiceStateLoading.value = false
  }
}

async function onGenerateInvoice() {
  busy.value = true
  try {
    const result = await generateInvoiceResource.submit({
      order_name: props.name,
      company: doc.value?.company,
    })
    toast.success(`Created draft invoice ${result?.name || ''}`.trim())
    await load()
  } catch (err) {
    toast.error(
      readableError(err) ||
        'Invoice could not be generated. Check the order state and billing setup.',
    )
    await loadInvoiceState()
  } finally {
    busy.value = false
  }
}

async function onMakeSalesOrder() {
  mapping.value = true
  try {
    const mapped = await mapDoc(
      'erpnext.selling.doctype.quotation.quotation.make_sales_order',
      props.name,
    )
    toast.success('Sales Order draft is ready to review')
    emit('mapped', mapped)
  } catch (err) {
    toast.error(readableError(err) || 'The Sales Order could not be prepared.')
  } finally {
    mapping.value = false
  }
}

async function onMakePayment() {
  mapping.value = true
  try {
    const mapped = await mapDoc('crm.finance.api.make_payment_entry_from_invoice', props.name)
    toast.success('Payment draft is ready to review')
    emit('mapped', mapped)
  } catch (err) {
    toast.error(readableError(err) || 'The payment could not be prepared.')
  } finally {
    mapping.value = false
  }
}

async function onSubmit() {
  busy.value = true
  try {
    await crud.submitDoc({ ...doc.value })
    toast.success('Submitted ' + props.name)
    await load()
  } catch {
    toast.error(crud.error.value || 'Submit failed')
  } finally {
    busy.value = false
  }
}

async function onCancel() {
  busy.value = true
  try {
    await crud.cancelDoc(props.name)
    toast.success('Cancelled ' + props.name)
    await load()
  } catch {
    toast.error(crud.error.value || 'Cancel failed')
  } finally {
    busy.value = false
  }
}

function onDelete() {
  dialog.danger({
    title: 'Delete ' + props.name + '?',
    message: 'This action cannot be undone.',
    onConfirm: async () => {
      busy.value = true
      try {
        await crud.deleteDoc(props.name)
        toast.success('Deleted ' + props.name)
        emit('deleted', props.name)
      } catch {
        toast.error(crud.error.value || 'Delete failed')
      } finally {
        busy.value = false
      }
    },
  })
}

function printDoc() {
  window.open(printUrl(props.doctype, props.name), '_blank')
}
</script>
