<template>
  <CreateDocumentModal
    v-if="showCreateDocumentModal"
    v-model="showCreateDocumentModal"
    :doctype="createDocumentDoctype"
    :data="createDocumentData"
    @callback="(data) => createDocumentCallback(data)"
  />
  <QuickEntryModal
    v-if="showQuickEntryModal"
    v-model="showQuickEntryModal"
    v-bind="quickEntryProps"
  />
  <ChangePasswordModal
    v-if="showChangePasswordModal"
    v-model="showChangePasswordModal"
  />
  <AboutModal v-if="showAboutModal" v-model="showAboutModal" />
  <FieldLayoutDialogContainer v-if="fieldLayoutDialogs.length" />
</template>
<script setup>
import {
  showCreateDocumentModal,
  createDocumentDoctype,
  createDocumentData,
  createDocumentCallback,
} from '@/composables/document'
import {
  showQuickEntryModal,
  quickEntryProps,
  showAboutModal,
  showChangePasswordModal,
} from '@/composables/modals'
import { fieldLayoutDialogs } from '@/utils/renderFieldLayoutDialog'
import { defineAsyncComponent } from 'vue'

// These modals are app-wide entry points but are not needed for the initial
// route. Loading them on demand keeps the shell responsive without changing
// their public composable APIs or behavior once opened.
const CreateDocumentModal = defineAsyncComponent(
  () => import('@/components/Modals/CreateDocumentModal.vue'),
)
const QuickEntryModal = defineAsyncComponent(
  () => import('@/components/Modals/QuickEntryModal.vue'),
)
const ChangePasswordModal = defineAsyncComponent(
  () => import('@/components/Modals/ChangePasswordModal.vue'),
)
const AboutModal = defineAsyncComponent(
  () => import('@/components/Modals/AboutModal.vue'),
)
const FieldLayoutDialogContainer = defineAsyncComponent(
  () => import('@/components/Modals/FieldLayoutDialogContainer.vue'),
)
</script>
