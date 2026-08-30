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
          <FormControl
            v-model="form.tiberbu_signatory"
            :label="__('Tiberbu Signatory')"
            :options="userOptions"
            type="select"
            @update:modelValue="markDirty"
          />
        </div>
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
  sales_tax_template: '',
  active_tc_document: '',
  default_lead_owner: '',
  tiberbu_signatory: '',
})

const settingsResource = createResource({
  url: 'crm.api.optin_admin.get_optin_settings',
  auto: true,
  onSuccess(data) {
    Object.assign(form, data)
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
