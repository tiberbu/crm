<template>
  <div class="flex h-full flex-col gap-6 py-8 px-6 text-ink-gray-8">
    <div class="flex justify-between items-start px-2">
      <div class="flex flex-col gap-1">
        <h2 class="text-2xl-semibold leading-none text-ink-gray-8">
          {{ __('HFR Integration') }}
        </h2>
        <p class="text-p-base text-ink-gray-6">
          {{
            __(
              'Connect to the Kenya Health Facility Registry (HFR) via the HIE to pre-fill Organisation and Lead records from verified registry data.',
            )
          }}
        </p>
      </div>
      <div class="flex items-center gap-2">
        <Badge
          v-if="isDirty"
          :label="__('Not Saved')"
          variant="subtle"
          theme="orange"
        />
        <Button
          v-if="isDirty && loaded"
          variant="solid"
          :label="__('Save Changes')"
          :loading="saving"
          @click="save"
        />
      </div>
    </div>

    <div
      v-if="settings.loading"
      class="flex flex-1 items-center justify-center"
    >
      <LoadingIndicator class="size-8" />
    </div>

    <!-- Never show (or save) the default form when the saved settings did not load:
         saving it would overwrite the stored credentials with blanks. -->
    <div
      v-else-if="!loaded"
      class="flex flex-1 flex-col items-center justify-center gap-3 px-2"
    >
      <ErrorMessage
        :message="
          __('HFR settings could not be loaded. Nothing has been changed.')
        "
      />
      <Button :label="__('Retry')" @click="settings.reload()" />
    </div>

    <div v-else class="flex-1 overflow-y-auto flex flex-col">
      <!-- Enable toggle -->
      <div class="flex items-center justify-between py-3 px-2">
        <div class="flex flex-col">
          <div class="text-p-base-medium text-ink-gray-7">
            {{ __('Enable HFR Integration') }}
          </div>
          <div class="text-p-sm text-ink-gray-5">
            {{
              __(
                'Allow Sales Agents to search the Health Facility Registry when creating Organisations and Leads.',
              )
            }}
          </div>
        </div>
        <Switch
          v-model="form.hfr_enabled"
          size="sm"
          @update:modelValue="markDirty"
        />
      </div>

      <template v-if="form.hfr_enabled">
        <div class="h-px border-t mx-2 border-outline-elevation-2" />
        <div class="px-2 pt-4 pb-2">
          <div
            class="text-xs-medium text-ink-gray-5 uppercase tracking-wider mb-3"
          >
            {{ __('HIE Credentials') }}
          </div>
          <div class="flex flex-col gap-3">
            <div class="flex items-center gap-4">
              <label class="text-p-sm text-ink-gray-7 w-44 shrink-0">{{
                __('HIE Base URL')
              }}</label>
              <FormControl
                v-model="form.hfr_url"
                type="text"
                placeholder="https://hie.example.health"
                class="flex-1"
                @input="markDirty"
              />
            </div>
            <div class="flex items-center gap-4">
              <label class="text-p-sm text-ink-gray-7 w-44 shrink-0">{{
                __('HFR Fetch Path')
              }}</label>
              <FormControl
                v-model="form.hfr_fetch_path"
                type="text"
                placeholder="/v1/hfr/facilities"
                class="flex-1"
                @input="markDirty"
              />
            </div>
            <div class="flex items-center gap-4">
              <label class="text-p-sm text-ink-gray-7 w-44 shrink-0">{{
                __('HIE Username')
              }}</label>
              <FormControl
                v-model="form.hfr_username"
                type="text"
                class="flex-1"
                @input="markDirty"
              />
            </div>
            <div class="flex items-center gap-4">
              <label class="text-p-sm text-ink-gray-7 w-44 shrink-0">{{
                __('HIE Password')
              }}</label>
              <FormControl
                v-model="form.hfr_password"
                type="password"
                :placeholder="__('Leave blank to keep existing')"
                class="flex-1"
                @input="markDirty"
              />
            </div>
            <div class="flex items-center gap-4">
              <label class="text-p-sm text-ink-gray-7 w-44 shrink-0">
                {{ __('JWT Expiry') }}
                <span class="text-ink-gray-4 ml-1">{{ __('(seconds)') }}</span>
              </label>
              <FormControl
                v-model="form.hfr_jwt_expiry"
                type="number"
                placeholder="20000"
                class="flex-1"
                @input="markDirty"
              />
            </div>
          </div>
        </div>
      </template>

      <div class="h-px border-t mx-2 border-outline-elevation-2" />
      <div class="px-2 pt-4 pb-4">
        <div class="text-xs-medium text-ink-gray-5 uppercase tracking-wider mb-1">
          {{ __('HIE Gateway Status API') }}
        </div>
        <p class="mb-4 max-w-3xl text-p-sm text-ink-gray-5">
          {{ __('Used as the fallback when the external setup service credentials below are not configured. The current status response does not include service-unit inventory.') }}
        </p>
        <div class="flex flex-col gap-3">
          <div class="flex items-center gap-4">
            <label class="text-p-sm text-ink-gray-7 w-44 shrink-0">{{ __('Provisioning Request API Path') }}</label>
            <FormControl v-model="form.provisioning_submit_path" type="text" placeholder="/v1/hmis/provisioning/facilities" class="flex-1" @input="markDirty" />
          </div>
          <div class="flex items-center gap-4">
            <label class="text-p-sm text-ink-gray-7 w-44 shrink-0">{{ __('Provisioning Status API Path') }}</label>
            <FormControl v-model="form.provisioning_status_path" type="text" placeholder="/v1/hmis/provisioning/facilities/{fid}/status" class="flex-1" @input="markDirty" />
          </div>
          <p class="text-p-sm text-ink-gray-5">{{ form.provisioning_status_configured ? __('HIE gateway fallback credentials are configured. The provisioning route must also be published.') : __('Configure the HIE gateway URL and credentials above to enable fallback status lookups.') }}</p>
        </div>
      </div>

      <div class="h-px border-t mx-2 border-outline-elevation-2" />
      <div class="px-2 pt-4 pb-4">
        <div class="text-xs-medium text-ink-gray-5 uppercase tracking-wider mb-1">
          {{ __('External HMIS Setup Service') }}
        </div>
        <p class="mb-4 max-w-3xl text-p-sm text-ink-gray-5">
          {{ __('If all three values are configured, status reads go directly to the setup service and take precedence over HIE. Use a dedicated Frappe service-user API key and secret. Deployment starts automatically unless manual review is switched on below.') }}
        </p>
        <div class="flex flex-col gap-3">
          <div class="flex items-center gap-4">
            <label class="text-p-sm text-ink-gray-7 w-44 shrink-0">{{ __('Setup Service Base URL') }}</label>
            <FormControl v-model="form.external_provisioning_url" type="text" placeholder="https://deploy.example.co.ke" class="flex-1" @input="markDirty" />
          </div>
          <div class="flex items-center gap-4">
            <label class="text-p-sm text-ink-gray-7 w-44 shrink-0">{{ __('Service API Key') }}</label>
            <FormControl v-model="form.external_provisioning_key" type="text" class="flex-1" @input="markDirty" />
          </div>
          <div class="flex items-center gap-4">
            <label class="text-p-sm text-ink-gray-7 w-44 shrink-0">{{ __('Service API Secret') }}</label>
            <FormControl v-model="form.external_provisioning_secret" type="password" :placeholder="__('Leave blank to keep existing')" class="flex-1" @input="markDirty" />
          </div>
          <div class="flex items-center gap-4">
            <label class="text-p-sm text-ink-gray-7 w-44 shrink-0">{{ __('Typical setup time (minutes)') }}</label>
            <FormControl v-model="form.provisioning_typical_minutes" type="number" min="0" class="flex-1" @input="markDirty" />
          </div>
          <p class="text-p-sm text-ink-gray-5">
            {{ __('Facility users see this as the usual wait while their HMIS site is set up, unless the setup service reports its own estimate. Set 0 to hide it.') }}
          </p>
          <div class="flex items-start justify-between gap-4">
            <div>
              <div class="text-p-sm font-medium text-ink-gray-8">{{ __('Review HMIS deployments before they start') }}</div>
              <div class="text-p-sm text-ink-gray-5">
                {{ __('When on, new setup records wait for the implementation team to start deployment in the setup service. When off, deployment starts automatically.') }}
              </div>
            </div>
            <Switch
              v-model="form.external_provisioning_manual_review"
              size="sm"
              data-testid="hfr-manual-review"
              @update:modelValue="markDirty"
            />
          </div>
          <p class="text-p-sm text-ink-gray-5">
            {{ form.external_provisioning_configured ? __('Direct setup service credentials are configured and take precedence over HIE for status lookups.') : (form.external_provisioning_secret_configured ? __('A saved API secret exists. Save a base URL and API key to activate the direct setup service.') : __('Direct setup service credentials are not complete; status lookups use the HIE gateway fallback.')) }}
          </p>
        </div>
      </div>

      <div v-if="saveError" class="mx-2 mt-2">
        <ErrorMessage :message="saveError" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import {
  Badge,
  Button,
  createResource,
  ErrorMessage,
  FormControl,
  LoadingIndicator,
  Switch,
  toast,
} from 'frappe-ui'

const isDirty = ref(false)
const loaded = ref(false)
const saving = ref(false)
const saveError = ref('')

const form = reactive({
  hfr_enabled: 0,
  hfr_url: '',
  hfr_fetch_path: '/v1/hfr/facilities',
  hfr_username: '',
  hfr_password: '',
  hfr_jwt_expiry: 20000,
  provisioning_submit_path: '/v1/hmis/provisioning/facilities',
  provisioning_status_path: '/v1/hmis/provisioning/facilities/{fid}/status',
  provisioning_status_configured: false,
  external_provisioning_url: '',
  external_provisioning_key: '',
  external_provisioning_secret: '',
  external_provisioning_secret_configured: false,
  external_provisioning_configured: false,
  provisioning_typical_minutes: 60,
  external_provisioning_manual_review: 0,
})

const settings = createResource({
  url: 'crm.api.hfr.get_hfr_settings',
  auto: true,
  onSuccess(data) {
    Object.assign(form, data)
    form.hfr_password = ''
    form.external_provisioning_secret = ''
    isDirty.value = false
    loaded.value = true
  },
})

const saveResource = createResource({
  url: 'crm.api.hfr.update_hfr_settings',
  method: 'POST',
  onSuccess() {
    isDirty.value = false
    saving.value = false
    saveError.value = ''
    settings.reload()
    toast.success(__('HFR settings saved'))
  },
  onError(err) {
    saveError.value = (err && err.message) || __('Failed to save settings')
    saving.value = false
  },
})

function markDirty() {
  isDirty.value = true
  saveError.value = ''
}

function save() {
  if (!loaded.value) return
  saving.value = true
  saveError.value = ''
  const payload = { ...form }
  if (!payload.hfr_password) delete payload.hfr_password
  if (!payload.external_provisioning_secret) delete payload.external_provisioning_secret
  saveResource.submit({ settings: payload })
}
</script>
