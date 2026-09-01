<template>
  <DoctypeModal
    v-if="doctypeModal.show.value"
    v-model="doctypeModal.show.value"
    :doctypeTitle="doctypeModal.title.value"
    :doctype="doctypeModal.doctype.value"
    :docname="doctypeModal.name.value"
    :defaults="doctypeModal.defaults.value"
    @afterInsert="(d) => doctypeModal.triggerCallback('afterInsert', d)"
    @afterUpdate="(d) => doctypeModal.triggerCallback('afterUpdate', d)"
  />
</template>
<script setup>
import { useDoctypeModal } from '@/composables/doctypeModal'
import { defineAsyncComponent } from 'vue'

// The doctype form is only needed after an action requests it. Keep this
// global mount lightweight while preserving the existing modal composable.
const DoctypeModal = defineAsyncComponent(
  () => import('@/components/Modals/DoctypeModal.vue'),
)

const doctypeModal = useDoctypeModal()
</script>
