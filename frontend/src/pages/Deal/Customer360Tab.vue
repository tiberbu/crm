<template>
  <div class="h-full overflow-y-auto">
    <Customer360Sections v-if="data" :data="data" />
    <div v-else-if="resource.loading" class="flex h-full items-center justify-center">
      <Spinner size="md" />
    </div>
    <div v-else class="flex h-full flex-col items-center justify-center gap-1">
      <p class="text-sm font-medium text-ink-gray-7">{{ __('No customer 360 data') }}</p>
      <p class="text-xs text-ink-gray-4">
        {{ __('This deal has no customer of record yet.') }}
      </p>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { createResource, Spinner } from 'frappe-ui'
import Customer360Sections from '@/components/Customer360/Customer360Sections.vue'

const props = defineProps({
	dealId: { type: String, default: '' },
})

const resource = createResource({
	url: 'crm.api.customer_360.get_customer_360',
	params: { deal: props.dealId },
	auto: true,
	transform: (data) => data,
})

const data = computed(() => resource.data)
</script>
