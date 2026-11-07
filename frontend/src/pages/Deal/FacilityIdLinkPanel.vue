<template>
  <div class="rounded-lg border border-outline-gray-1 bg-surface-gray-1 p-3 sm:p-4">
    <p class="text-base text-ink-gray-7">
      {{ __('This facility has no Facility ID yet. Link it here so it can be metered.') }}
    </p>

    <div class="mt-3 flex flex-wrap items-end gap-2">
      <FormControl
        v-model="fid"
        class="w-56"
        :label="__('Facility ID')"
        placeholder="FID-00-12345-1"
        autocomplete="off"
        data-testid="facility-id-input"
      />
      <Button
        :label="__('Link')"
        :loading="busy === 'link'"
        :disabled="!fid.trim()"
        @click="link('manual')"
      />
    </div>

    <div class="mt-4 border-t border-outline-gray-1 pt-3">
      <div class="text-sm font-medium text-ink-gray-8">{{ __('Find by owner ID') }}</div>
      <div class="mt-2 flex flex-wrap items-end gap-2">
        <FormControl
          v-model="ownerId"
          class="w-56"
          :label="__('Owner ID number')"
          autocomplete="off"
          data-testid="owner-id-input"
        />
        <Button
          :label="__('Find facilities')"
          :loading="busy === 'find'"
          :disabled="!ownerId.trim()"
          @click="findFacilities"
        />
      </div>

      <p v-if="findError" class="mt-2 text-sm text-ink-red-4">{{ findError }}</p>

      <div v-for="candidate in candidates" :key="candidate.hfr_facility_id" class="mt-2 flex items-center justify-between gap-2">
        <span class="text-base text-ink-gray-8">
          {{ candidate.hfr_facility_id }}
          <span class="text-ink-gray-6">
            · {{ candidate.facility_name }}
            <template v-if="candidate.facility_level"> · {{ __(candidate.facility_level) }}</template>
            <template v-if="candidate.facility_type"> · {{ __(candidate.facility_type) }}</template>
          </span>
        </span>
        <Button
          size="sm"
          :label="__('Link')"
          :loading="busy === `link-${candidate.hfr_facility_id}`"
          @click="link('hfr', candidate.hfr_facility_id)"
        />
      </div>
    </div>

    <Dialog v-model="confirmDialog.show" :options="{ title: __('Link anyway?'), size: 'sm' }">
      <template #body-content>
        <p class="text-base text-ink-gray-7">
          {{
            __(
              'This Facility ID is already on {0}. Link it anyway?',
              confirmDialog.holders.map((holder) => `${holder.doctype} ${holder.name}`).join(', '),
            )
          }}
        </p>
      </template>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button variant="subtle" :label="__('Cancel')" @click="confirmDialog.show = false" />
          <Button variant="solid" :label="__('Link anyway')" @click="link(confirmDialog.source, confirmDialog.fid, 1)" />
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { Button, Dialog, FormControl, call, toast } from 'frappe-ui'
import { isValidFacilityId } from '@/utils/facilityId'

const props = defineProps({
  dealId: { type: String, required: true },
  facility: { type: Object, required: true },
})
const emit = defineEmits(['linked'])

const fid = ref('')
const ownerId = ref('')
const busy = ref(null)
const candidates = ref([])
const findError = ref('')
const confirmDialog = reactive({ show: false, fid: '', source: 'manual', holders: [] })

function message(error) {
  return error?.messages?.join(' ') || error?.message || __('Something went wrong.')
}

async function link(source, value = null, confirmShared = 0) {
  const target = value || fid.value.trim()
  if (!value && !isValidFacilityId(target)) {
    toast.error(__('Enter a Facility ID like FID-00-12345-1.'))
    return
  }
  busy.value = value ? `link-${value}` : 'link'
  try {
    const result = await call('crm.api.metering_admin.link_deal_facility', {
      deal: props.dealId,
      row_name: props.facility.row_name,
      hfr_facility_id: target,
      source,
      confirm_shared: confirmShared,
    })
    if (result.status === 'in_use') {
      confirmDialog.holders = result.holders || []
      confirmDialog.fid = target
      confirmDialog.source = source
      confirmDialog.show = true
      return
    }
    fid.value = ''
    emit('linked', props.facility.row_name)
  } catch (error) {
    toast.error(message(error))
  } finally {
    busy.value = null
  }
}

async function findFacilities() {
  busy.value = 'find'
  findError.value = ''
  candidates.value = []
  try {
    const result = await call('crm.api.metering_admin.find_owner_facilities', {
      deal: props.dealId,
      owner_id_number: ownerId.value.trim(),
    })
    if (result.status === 'ok') {
      candidates.value = result.candidates || []
    } else {
      findError.value = textFor(result.status)
    }
  } catch (error) {
    findError.value =
      error?.messages?.[0] ||
      __("The registry can't be reached right now. Try again, or enter the Facility ID above.")
  } finally {
    ownerId.value = ''
    busy.value = null
  }
}

function textFor(status) {
  const text = {
    no_facilities: __('No facilities were found for that ID. Check the number, or enter the Facility ID above.'),
    invalid_id: __('Enter the ID number as it appears on the document, or enter the Facility ID above.'),
    unavailable: __("The registry can't be reached right now. Try again, or enter the Facility ID above."),
    rate_limited: __('Too many searches. Try again shortly, or enter the Facility ID above.'),
  }
  return text[status] || text.unavailable
}
</script>
