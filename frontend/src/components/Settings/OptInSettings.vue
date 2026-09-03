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
    dirty.value = false
  },
})
const priceListsResource = createResource({
  url: 'crm.api.optin_admin.list_negotiated_price_lists',
  auto: true,
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
