<template>
  <div class="flex h-full flex-col gap-6 px-6 py-8 text-ink-gray-8">
    <div class="flex items-start justify-between gap-4 px-2">
      <div>
        <h2 class="text-2xl-semibold leading-none">
          {{ __('Opt-In Process') }}
        </h2>
        <p class="mt-1 text-p-base text-ink-gray-6">
          {{
            __(
              'Set the defaults used when facilities submit their Opt-In commitments.',
            )
          }}
        </p>
      </div>
      <div class="flex items-center gap-2">
        <Badge
          v-if="dirty"
          :label="__('Not Saved')"
          theme="orange"
          variant="subtle"
        />
        <Button
          v-if="dirty"
          variant="solid"
          :label="__('Save Changes')"
          :loading="saving"
          @click="save"
        />
      </div>
    </div>

    <div v-if="settingsResource.loading" class="grid flex-1 place-items-center">
      <LoadingIndicator class="size-8" />
    </div>
    <div v-else class="flex flex-1 flex-col overflow-y-auto px-2">
      <section class="py-3">
        <h3 class="text-sm font-semibold text-ink-gray-8">
          {{ __('Commercial defaults') }}
        </h3>
        <p class="mt-1 text-sm text-ink-gray-5">
          {{
            __(
              'These values apply when a Network does not supply its own negotiated price list.',
            )
          }}
        </p>
        <div class="mt-4 max-w-xl">
          <FormControl
            v-model="form.default_price_list"
            :label="__('Default selling price list')"
            :options="priceListOptions"
            type="select"
            @update:modelValue="markDirty"
          />
          <FormControl
            v-model="form.optional_services_price_list"
            class="mt-4"
            :label="__('Optional services price list')"
            :options="optionalServicesPriceListOptions"
            type="select"
            :description="
              __(
                'Items from this selling list appear as selectable optional services. They are informational and are not added to subscription quotations.',
              )
            "
            @update:modelValue="markDirty"
          />
          <FormControl
            v-model="form.sales_tax_template"
            class="mt-4"
            :label="__('VAT taxes and charges template')"
            :options="taxTemplateOptions"
            type="select"
            :description="
              __(
                'Rates stay exclusive of VAT. This ERPNext template supplies the VAT shown on quotations, emails, and contracts.',
              )
            "
            @update:modelValue="markDirty"
          />
        </div>
      </section>

      <div class="border-t border-outline-elevation-2" />
      <section class="py-5">
        <div class="flex items-start justify-between gap-4">
          <div>
            <h3 class="text-sm font-semibold text-ink-gray-8">
              {{ __('Facility token catalogue') }}
            </h3>
            <p class="mt-1 max-w-3xl text-sm text-ink-gray-5">
              {{
                __('Use one ERPNext selling Price List with several service items. The names and coverage text below are what facility owners see. Rates remain in ERPNext Item Price records and exclude VAT.')
              }}
            </p>
          </div>
        </div>
        <div class="mt-4 max-w-3xl">
          <FormControl
            v-model="form.token_price_list"
            :label="__('Token selling Price List')"
            :options="tokenPriceListOptions"
            type="select"
            @update:modelValue="markDirty"
          />
          <FormControl
            v-model="form.facility_onboarding_default_partner_id"
            class="mt-4"
            :label="__('Default Network Partner ID')"
            :description="__('Optional six-digit Network ID used when a facility leaves Partner ID blank during self-onboarding.')"
            @update:modelValue="markDirty"
          />
          <div class="mt-4 grid gap-4 md:grid-cols-2">
            <FormControl
              v-model="form.token_sales_order_validity_days"
              :label="__('Sales Order validity (days)')"
              type="number"
              :description="__('Generic validity window for an open token Sales Order.')"
              @update:modelValue="markDirty"
            />
            <FormControl
              v-model="form.token_invoice_due_days"
              :label="__('Invoice payment terms (days)')"
              type="number"
              :description="__('Invoices are due within this period; checkout may happen immediately.')"
              @update:modelValue="markDirty"
            />
          </div>
        </div>
        <div class="mt-5 max-w-5xl overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-white shadow-sm dark:bg-surface-gray-1">
          <div class="hidden grid-cols-[1.2fr_1fr_5rem_7rem_2.5rem] gap-3 border-b border-outline-gray-2 bg-surface-gray-1/80 px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-ink-gray-5 md:grid dark:bg-surface-gray-2">
            <span>{{ __('Service item') }}</span><span>{{ __('Facility-facing name') }}</span><span>{{ __('Tokens') }}</span><span>{{ __('Enabled') }}</span><span />
          </div>
          <div v-if="!form.token_packages.length" class="px-4 py-8 text-center text-sm text-ink-gray-5">
            <p class="font-medium text-ink-gray-7">{{ __('No token packages configured') }}</p>
            <p class="mt-1 text-xs text-ink-gray-5">{{ __('Add service items to publish facility-friendly token choices.') }}</p>
          </div>
          <div v-for="(pkg, index) in form.token_packages" :key="pkg._key || index" class="grid grid-cols-1 gap-3 border-b border-outline-gray-2 px-4 py-4 last:border-b-0 md:grid-cols-[1.2fr_1fr_5rem_7rem_2.5rem] md:items-start md:gap-3 md:px-3 md:py-3">
            <div>
              <span class="mb-1 block text-xs font-medium text-ink-gray-5 md:hidden">{{ __('Service item') }}</span>
              <select v-model="pkg.item_code" class="w-full rounded-lg border border-outline-gray-2 bg-surface-white px-3 py-2 text-sm text-ink-gray-8 shadow-sm outline-none focus:border-outline-gray-3 focus:ring-2 focus:ring-outline-gray-2 dark:bg-surface-gray-2" @change="markDirty">
                <option value="">{{ __('Select item') }}</option>
                <option v-for="item in tokenItemOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
              </select>
            </div>
            <div>
              <span class="mb-1 block text-xs font-medium text-ink-gray-5 md:hidden">{{ __('Facility-facing name') }}</span>
              <input v-model="pkg.display_name" type="text" :placeholder="__('e.g. Core care operations')" class="w-full rounded-lg border border-outline-gray-2 bg-surface-white px-3 py-2 text-sm text-ink-gray-8 shadow-sm outline-none placeholder:text-ink-gray-4 focus:border-outline-gray-3 focus:ring-2 focus:ring-outline-gray-2 dark:bg-surface-gray-2" @input="markDirty" />
            </div>
            <div>
              <span class="mb-1 block text-xs font-medium text-ink-gray-5 md:hidden">{{ __('Tokens') }}</span>
              <input v-model="pkg.token_quantity" type="number" min="1" class="w-full rounded-lg border border-outline-gray-2 bg-surface-white px-3 py-2 text-sm text-ink-gray-8 shadow-sm outline-none focus:border-outline-gray-3 focus:ring-2 focus:ring-outline-gray-2 dark:bg-surface-gray-2" @input="markDirty" />
            </div>
            <div class="flex items-center gap-2 pt-2">
              <input v-model="pkg.enabled" type="checkbox" class="rounded border-outline-gray-3" @change="markDirty" />
              <span class="text-sm text-ink-gray-7">{{ __('Published') }}</span>
            </div>
            <div class="flex justify-end md:justify-center">
              <button type="button" class="grid size-8 place-items-center rounded-lg text-lg text-ink-gray-5 transition hover:bg-surface-gray-2 hover:text-ink-red-5 focus:outline-none focus:ring-2 focus:ring-outline-gray-2 dark:hover:bg-surface-gray-3" :aria-label="__('Remove package')" @click="removeTokenPackage(index)">×</button>
            </div>
            <div class="md:col-span-5 grid gap-3 md:grid-cols-3">
              <textarea v-model="pkg.description" :placeholder="__('Facility-facing description')" class="min-h-20 w-full rounded-lg border border-outline-gray-2 bg-surface-white px-3 py-2 text-sm text-ink-gray-8 shadow-sm outline-none placeholder:text-ink-gray-4 focus:border-outline-gray-3 focus:ring-2 focus:ring-outline-gray-2 dark:bg-surface-gray-2" @input="markDirty" />
              <textarea v-model="pkg.coverage_summary" :placeholder="__('Coverage summary, for example 100 laboratory transactions per month')" class="min-h-20 w-full rounded-lg border border-outline-gray-2 bg-surface-white px-3 py-2 text-sm text-ink-gray-8 shadow-sm outline-none placeholder:text-ink-gray-4 focus:border-outline-gray-3 focus:ring-2 focus:ring-outline-gray-2 dark:bg-surface-gray-2" @input="markDirty" />
              <FormControl v-model="pkg.billing_period" :label="__('Billing period')" :options="billingPeriodOptions" type="select" @update:modelValue="markDirty" />
            </div>
          </div>
          <div class="flex items-center justify-between border-t border-outline-gray-2 bg-surface-gray-1/80 px-4 py-3 dark:bg-surface-gray-2">
            <span class="text-xs text-ink-gray-5">{{ __('Use Item Price for rates. Do not enter VAT-inclusive prices here.') }}</span>
            <Button variant="subtle" size="sm" :label="__('Add package')" @click="addTokenPackage" />
          </div>
        </div>
      </section>

      <div class="border-t border-outline-elevation-2" />
      <section class="py-5">
        <div class="flex items-center justify-between gap-3">
          <div>
            <h3 class="text-sm font-semibold text-ink-gray-8">
              {{ __('Agreement defaults') }}
            </h3>
            <p class="mt-1 text-sm text-ink-gray-5">
              {{
                __(
                  'Facilities must accept this document before submitting an Opt-In request.',
                )
              }}
            </p>
          </div>
          <Button
            variant="subtle"
            size="sm"
            :label="__('Manage terms')"
            @click="router.push({ name: 'OptInTerms' })"
          />
        </div>
        <div class="mt-4 max-w-xl">
          <FormControl
            v-model="form.active_tc_document"
            :label="__('Default Terms & Conditions')"
            :options="termsOptions"
            type="select"
            @update:modelValue="markDirty"
          />
        </div>
      </section>

      <div class="border-t border-outline-elevation-2" />
      <section class="py-5">
        <h3 class="text-sm font-semibold text-ink-gray-8">
          {{ __('Ownership and signing') }}
        </h3>
        <p class="mt-1 text-sm text-ink-gray-5">
          {{
            __(
              'Assign the internal people responsible for new submissions and executed contracts.',
            )
          }}
        </p>
        <div class="mt-4 grid max-w-xl gap-4">
          <FormControl
            v-model="form.default_lead_owner"
            :label="__('Default Lead Owner')"
            :options="userOptions"
            type="select"
            @update:modelValue="markDirty"
          />
        </div>
      </section>
      <div class="border-t border-outline-elevation-2" />
      <section class="py-5">
        <h3 class="text-sm font-semibold text-ink-gray-8">
          {{ __('Tiberbu signing and approval contacts') }}
        </h3>
        <p class="mt-1 max-w-3xl text-sm text-ink-gray-5">
          {{
            __(
              'Maintain one row per Tiberbu signatory or approver. These contacts can be external to CRM and are copied onto new contracts.',
            )
          }}
        </p>
        <div
          class="mt-4 w-full max-w-5xl overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-white shadow-sm dark:bg-surface-gray-1"
        >
          <div
            class="hidden grid-cols-[8rem_1fr_1.3fr_1fr_2.5rem] gap-3 border-b border-outline-gray-2 bg-surface-gray-1/80 px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-ink-gray-5 md:grid dark:bg-surface-gray-2"
          >
            <span>{{ __('Role') }}</span
            ><span>{{ __('Name') }}</span
            ><span>{{ __('Email') }}</span
            ><span>{{ __('Phone') }}</span
            ><span />
          </div>
          <div
            v-if="!form.tiberbu_contacts.length"
            class="px-4 py-8 text-center text-sm text-ink-gray-5"
          >
            <div
              class="mx-auto mb-2 grid size-9 place-items-center rounded-full bg-surface-gray-2 text-lg text-ink-gray-5 dark:bg-surface-gray-3"
              aria-hidden="true"
            >
              +
            </div>
            <p class="font-medium text-ink-gray-7">
              {{ __('No signing contacts yet') }}
            </p>
            <p class="mt-1 text-xs text-ink-gray-5">
              {{ __('Add a signatory or approver to use on new contracts.') }}
            </p>
          </div>
          <div
            v-for="(contact, index) in form.tiberbu_contacts"
            :key="contact._key || index"
            class="grid grid-cols-1 gap-3 border-b border-outline-gray-2 px-4 py-4 last:border-b-0 md:grid-cols-[8rem_1fr_1.3fr_1fr_2.5rem] md:items-center md:gap-3 md:px-3 md:py-2.5"
          >
            <div
              class="grid grid-cols-[5rem_minmax(0,1fr)] items-center gap-3 md:contents"
            >
              <span class="text-xs font-medium text-ink-gray-5 md:hidden">
                {{ __('Role') }}
              </span>
              <select
                v-model="contact.role"
                :aria-label="__('Contact role')"
                class="w-full rounded-lg border border-outline-gray-2 bg-surface-white px-3 py-2 text-sm text-ink-gray-8 shadow-sm outline-none transition focus:border-outline-gray-3 focus:ring-2 focus:ring-outline-gray-2 dark:bg-surface-gray-2"
                @change="markDirty"
              >
                <option value="Signatory">{{ __('Signatory') }}</option>
                <option value="Approver">{{ __('Approver') }}</option>
              </select>
            </div>
            <div
              class="grid grid-cols-[5rem_minmax(0,1fr)] items-center gap-3 md:contents"
            >
              <span class="text-xs font-medium text-ink-gray-5 md:hidden">
                {{ __('Name') }}
              </span>
              <input
                v-model="contact.full_name"
                type="text"
                :aria-label="__('Contact full name')"
                :placeholder="__('Full name')"
                class="w-full rounded-lg border border-outline-gray-2 bg-surface-white px-3 py-2 text-sm text-ink-gray-8 shadow-sm outline-none transition placeholder:text-ink-gray-4 focus:border-outline-gray-3 focus:ring-2 focus:ring-outline-gray-2 dark:bg-surface-gray-2"
                @input="markDirty"
              />
            </div>
            <div
              class="grid grid-cols-[5rem_minmax(0,1fr)] items-center gap-3 md:contents"
            >
              <span class="text-xs font-medium text-ink-gray-5 md:hidden">
                {{ __('Email') }}
              </span>
              <input
                v-model="contact.email"
                type="email"
                :aria-label="__('Contact email')"
                :placeholder="__('name@tiberbu.com')"
                class="w-full rounded-lg border border-outline-gray-2 bg-surface-white px-3 py-2 text-sm text-ink-gray-8 shadow-sm outline-none transition placeholder:text-ink-gray-4 focus:border-outline-gray-3 focus:ring-2 focus:ring-outline-gray-2 dark:bg-surface-gray-2"
                @input="markDirty"
              />
            </div>
            <div
              class="grid grid-cols-[5rem_minmax(0,1fr)] items-center gap-3 md:contents"
            >
              <span class="text-xs font-medium text-ink-gray-5 md:hidden">
                {{ __('Phone') }}
              </span>
              <input
                v-model="contact.phone"
                type="tel"
                :aria-label="__('Contact phone')"
                :placeholder="__('+254 7xx xxx xxx')"
                class="w-full rounded-lg border border-outline-gray-2 bg-surface-white px-3 py-2 text-sm text-ink-gray-8 shadow-sm outline-none transition placeholder:text-ink-gray-4 focus:border-outline-gray-3 focus:ring-2 focus:ring-outline-gray-2 dark:bg-surface-gray-2"
                @input="markDirty"
              />
            </div>
            <div class="flex justify-end md:justify-center">
              <button
                type="button"
                class="grid size-8 place-items-center rounded-lg text-lg text-ink-gray-5 transition hover:bg-surface-gray-2 hover:text-ink-red-5 focus:outline-none focus:ring-2 focus:ring-outline-gray-2 dark:hover:bg-surface-gray-3"
                :aria-label="__('Remove contact')"
                :title="__('Remove contact')"
                @click="removeContact(index)"
              >
                ×
              </button>
            </div>
          </div>
          <div
            class="flex flex-col gap-3 border-t border-outline-gray-2 bg-surface-gray-1/80 px-4 py-3 sm:flex-row sm:items-center sm:justify-between dark:bg-surface-gray-2"
          >
            <div class="flex items-center gap-2">
              <Badge
                :label="
                  __('{0} contact{1}', [
                    form.tiberbu_contacts.length,
                    form.tiberbu_contacts.length === 1 ? '' : 's',
                  ])
                "
                theme="gray"
                variant="subtle"
              />
              <span class="text-xs text-ink-gray-5">
                {{ __('Used for new contracts') }}
              </span>
            </div>
            <Button
              variant="subtle"
              size="sm"
              :label="__('Add contact')"
              @click="addContact"
            />
          </div>
        </div>
        <div class="mt-4 max-w-sm">
          <FormControl
            v-model="form.tiberbu_signing_requirement"
            :label="__('Tiberbu signing rule')"
            :options="signingRequirementOptions"
            type="select"
            :description="
              __(
                'Choose whether every Tiberbu signatory must sign or any one of them is sufficient.',
              )
            "
            @update:modelValue="markDirty"
          />
        </div>
        <details
          class="mt-4 max-w-3xl rounded-lg border border-outline-gray-2 px-3 py-2"
        >
          <summary class="cursor-pointer text-sm font-medium text-ink-gray-7">
            {{ __('Legacy fallback fields') }}
          </summary>
          <div class="mt-3 grid gap-4">
            <FormControl
              v-model="form.tiberbu_signatory"
              :label="__('Legacy signatory User')"
              :options="userOptions"
              type="select"
              :description="
                __('Used only when the table has no signatory rows.')
              "
              @update:modelValue="markDirty"
            />
            <div class="grid gap-4 md:grid-cols-3">
              <FormControl
                v-model="form.tiberbu_signatory_name"
                :label="__('Legacy signatory name')"
                type="text"
                @update:modelValue="markDirty"
              />
              <FormControl
                v-model="form.tiberbu_signatory_email"
                :label="__('Legacy signatory email')"
                type="email"
                @update:modelValue="markDirty"
              />
              <FormControl
                v-model="form.tiberbu_signatory_phone"
                :label="__('Legacy signatory phone')"
                type="tel"
                @update:modelValue="markDirty"
              />
            </div>
            <div class="grid gap-4 md:grid-cols-3">
              <FormControl
                v-model="form.tiberbu_approver_name"
                :label="__('Legacy approver name')"
                type="text"
                @update:modelValue="markDirty"
              />
              <FormControl
                v-model="form.tiberbu_approver_email"
                :label="__('Legacy approver email')"
                type="email"
                @update:modelValue="markDirty"
              />
              <FormControl
                v-model="form.tiberbu_approver_phone"
                :label="__('Legacy approver phone')"
                type="tel"
                @update:modelValue="markDirty"
              />
            </div>
          </div>
        </details>
      </section>
      <ErrorMessage v-if="saveError" :message="saveError" />
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import {
  Badge,
  Button,
  ErrorMessage,
  FormControl,
  LoadingIndicator,
  createResource,
  toast,
} from 'frappe-ui'
import router from '@/router'

const dirty = ref(false)
const saving = ref(false)
const saveError = ref('')
const form = reactive({
  default_price_list: '',
  optional_services_price_list: '',
  sales_tax_template: '',
  active_tc_document: '',
  default_lead_owner: '',
  tiberbu_signatory: '',
  tiberbu_signatory_name: '',
  tiberbu_signatory_email: '',
  tiberbu_signatory_phone: '',
  tiberbu_approver_name: '',
  tiberbu_approver_email: '',
  tiberbu_approver_phone: '',
  tiberbu_signing_requirement: 'All must sign',
  tiberbu_contacts: [],
  token_price_list: '',
  facility_onboarding_default_partner_id: '',
  token_sales_order_validity_days: 30,
  token_invoice_due_days: 30,
  token_packages: [],
})

const settingsResource = createResource({
  url: 'crm.api.optin_admin.get_optin_settings',
  auto: true,
  onSuccess(data) {
    Object.assign(form, data)
    form.tiberbu_contacts = (data.tiberbu_contacts ?? []).map(
      (contact, index) => ({
        ...contact,
        _key: `${contact.role}-${contact.email}-${index}`,
      }),
    )
    form.token_packages = (data.token_packages ?? []).map((pkg, index) => ({
      ...pkg,
      _key: `${pkg.item_code}-${index}`,
    }))
    dirty.value = false
  },
})
const priceListsResource = createResource({
  url: 'crm.api.optin_admin.list_negotiated_price_lists',
  auto: true,
})
const tokenPriceListsResource = createResource({
  url: 'crm.api.optin_admin.list_selling_price_lists',
  auto: true,
})
const tokenItemsResource = createResource({
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
const termsResource = createResource({
  url: 'crm.api.optin_admin.list_optin_terms',
  auto: true,
})
const optionalServicesPriceListsResource = createResource({
  url: 'crm.api.optin_admin.list_optional_services_price_lists',
  auto: true,
})
const taxTemplatesResource = createResource({
  url: 'crm.api.optin_admin.list_optin_tax_templates',
  auto: true,
})
const usersResource = createResource({
  url: 'frappe.client.get_list',
  auto: true,
  makeParams: () => ({
    doctype: 'User',
    fields: ['name', 'full_name'],
    filters: { enabled: 1 },
    order_by: 'full_name asc',
    limit_page_length: 0,
  }),
})
const saveResource = createResource({
  url: 'crm.api.optin_admin.update_optin_settings',
  method: 'POST',
})

const priceListOptions = computed(() => [
  { label: __('Select a price list'), value: '' },
  ...(priceListsResource.data ?? []),
])
const tokenPriceListOptions = computed(() => [
  { label: __('Select a token selling Price List'), value: '' },
  ...(tokenPriceListsResource.data ?? []),
])
const tokenItemOptions = computed(() =>
  (tokenItemsResource.data ?? []).map((item) => ({
    label: item.item_name ? `${item.item_name} (${item.name})` : item.name,
    value: item.name,
  })),
)
const billingPeriodOptions = [
  { label: __('Monthly'), value: 'Monthly' },
  { label: __('Quarterly'), value: 'Quarterly' },
  { label: __('Annual'), value: 'Annual' },
]
const optionalServicesPriceListOptions = computed(() => [
  { label: __('Use Standard Selling / configured default'), value: '' },
  ...(optionalServicesPriceListsResource.data ?? []),
])
const termsOptions = computed(() => [
  { label: __('Select Terms & Conditions'), value: '' },
  ...(termsResource.data?.rows ?? []).map((document) => ({
    label: document.title,
    value: document.name,
  })),
])
const taxTemplateOptions = computed(() => [
  { label: __('Select VAT taxes and charges template'), value: '' },
  ...(taxTemplatesResource.data ?? []),
])
const userOptions = computed(() => [
  { label: __('Not set'), value: '' },
  ...(usersResource.data ?? []).map((user) => ({
    label: user.full_name || user.name,
    value: user.name,
  })),
])
const signingRequirementOptions = [
  { label: __('All must sign'), value: 'All must sign' },
  { label: __('At least one must sign'), value: 'At least one must sign' },
]

function addContact() {
  form.tiberbu_contacts.push({
    _key: `new-${Date.now()}-${form.tiberbu_contacts.length}`,
    role: 'Signatory',
    full_name: '',
    email: '',
    phone: '',
  })
  markDirty()
}

function removeContact(index) {
  form.tiberbu_contacts.splice(index, 1)
  markDirty()
}

function addTokenPackage() {
  form.token_packages.push({
    _key: `new-token-${Date.now()}-${form.token_packages.length}`,
    item_code: '',
    display_name: '',
    description: '',
    token_quantity: 1,
    billing_period: 'Monthly',
    coverage_summary: '',
    coverage_metrics: '',
    enabled: 1,
  })
  markDirty()
}

function removeTokenPackage(index) {
  form.token_packages.splice(index, 1)
  markDirty()
}

function markDirty() {
  dirty.value = true
  saveError.value = ''
}

async function save() {
  saving.value = true
  saveError.value = ''
  try {
    await saveResource.submit({ settings: { ...form } })
    dirty.value = false
    toast.success(__('Opt-In settings saved'))
  } catch (error) {
    saveError.value =
      error?.messages?.[0] ??
      error?.message ??
      __('Could not save Opt-In settings')
  } finally {
    saving.value = false
  }
}
</script>
