<template>
  <div class="flex h-full overflow-hidden bg-surface-gray-1">
    <aside class="flex w-80 shrink-0 flex-col border-r border-outline-gray-2 bg-surface-white">
      <div class="border-b border-outline-gray-2 px-5 py-4">
        <h1 class="text-xl font-semibold text-ink-gray-9">{{ __('Terms & Conditions') }}</h1>
        <p class="mt-1 text-sm text-ink-gray-5">{{ __('Control the agreement accepted with every Opt-In submission.') }}</p>
      </div>
      <div class="flex-1 overflow-y-auto p-3">
        <button
          v-for="document in documents"
          :key="document.name"
          class="mb-1 w-full rounded-lg p-3 text-left transition-colors"
          :class="selectedName === document.name ? 'bg-surface-gray-2' : 'hover:bg-surface-gray-1'"
          @click="selectDocument(document.name)"
        >
          <div class="flex items-start justify-between gap-2">
            <span class="line-clamp-2 font-medium text-ink-gray-9">{{ document.title }}</span>
            <Badge v-if="document.active" :label="__('Active')" theme="green" variant="subtle" />
          </div>
          <p class="mt-1 text-xs text-ink-gray-5">{{ formatDate(document.modified) }}</p>
        </button>
      </div>
      <div class="border-t border-outline-gray-2 p-3">
        <Button class="w-full" variant="solid" icon-left="plus" :label="__('New terms')" @click="newDocument" />
      </div>
    </aside>

    <main class="flex min-w-0 flex-1 flex-col">
      <div v-if="editor" class="flex items-center justify-between gap-4 border-b border-outline-gray-2 bg-surface-white px-6 py-3">
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <h2 class="truncate text-base font-semibold text-ink-gray-9">{{ editor.title || __('Untitled agreement') }}</h2>
            <Badge v-if="isActive" :label="__('Default for Opt-In')" theme="green" variant="subtle" />
          </div>
          <p class="mt-0.5 text-sm text-ink-gray-5">{{ __('The active agreement is rendered when a facility reviews its commitment.') }}</p>
        </div>
        <div class="flex shrink-0 items-center gap-2">
          <Button v-if="editor.name && !isActive" variant="subtle" :loading="settingDefault" :label="__('Set as default')" @click="setDefault" />
          <Button variant="solid" :disabled="!isDirty" :loading="saving" :label="__('Save changes')" @click="save" />
        </div>
      </div>

      <div v-if="loading" class="grid flex-1 place-items-center"><LoadingIndicator /></div>
      <div v-else-if="editor" class="flex flex-1 flex-col gap-5 overflow-y-auto p-6">
        <FormControl v-model="editor.title" :label="__('Document title')" :required="true" :placeholder="__('CareverseHIMS Opt-In Terms and Conditions')" />
        <div>
          <label class="mb-1.5 block text-sm font-medium text-ink-gray-7">{{ __('Agreement content') }} <span class="text-ink-red-6">*</span></label>
          <TextEditor
            :content="editor.terms"
            :bubble-menu="true"
            editor-class="min-h-[28rem] max-w-none rounded-lg border border-outline-gray-2 bg-surface-white p-4 prose-sm"
            :placeholder="__('Write the terms that facilities must accept before submitting an Opt-In request.')"
            @change="editor.terms = $event"
          />
          <p class="mt-2 text-xs text-ink-gray-5">{{ termsHint }}</p>
        </div>
      </div>
      <div v-else class="grid flex-1 place-items-center text-sm text-ink-gray-5">{{ __('Create or select a Terms and Conditions document.') }}</div>
    </main>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Badge, Button, FormControl, LoadingIndicator, TextEditor, createResource, toast } from 'frappe-ui'

const documents = ref([])
const activeName = ref('')
const selectedName = ref('')
const editor = ref(null)
const loading = ref(true)
const saving = ref(false)
const settingDefault = ref(false)
const original = ref('')
const termsHint = __(
  'You can use dynamic values such as {{ network.display_name }} and {{ pricing_table }}. '
  + 'Other text inside {{ ... }} is saved and shown as ordinary agreement text.',
)

const listResource = createResource({ url: 'crm.api.optin_admin.list_optin_terms' })
const getResource = createResource({ url: 'crm.api.optin_admin.get_optin_terms' })
const saveResource = createResource({ url: 'crm.api.optin_admin.save_optin_terms' })
const defaultResource = createResource({ url: 'crm.api.optin_admin.set_default_optin_terms' })

const isActive = computed(() => editor.value?.name === activeName.value)
const isDirty = computed(() => JSON.stringify(editor.value) !== original.value)

async function loadDocuments(selectName = selectedName.value) {
  loading.value = true
  try {
    const result = await listResource.fetch()
    documents.value = result.rows
    activeName.value = result.active
    if (selectName || result.active || result.rows[0]?.name) {
      await selectDocument(selectName || result.active || result.rows[0].name)
    }
  } catch (error) {
    toast.error(error?.messages?.[0] ?? error?.message ?? __('Could not load Terms and Conditions'))
  } finally {
    loading.value = false
  }
}

async function selectDocument(name) {
  selectedName.value = name
  try {
    const document = await getResource.submit({ name })
    editor.value = { ...document }
    original.value = JSON.stringify(editor.value)
  } catch (error) {
    toast.error(error?.messages?.[0] ?? error?.message ?? __('Could not load this document'))
  }
}

function newDocument() {
  selectedName.value = ''
  editor.value = { name: '', title: '', terms: '' }
  original.value = JSON.stringify(editor.value)
}

async function save() {
  if (!editor.value.title.trim() || !editor.value.terms.trim()) {
    toast.error(__('Enter a title and agreement content'))
    return
  }
  saving.value = true
  try {
    const result = await saveResource.submit(editor.value)
    editor.value.name = result.name
    editor.value.terms = result.terms
    selectedName.value = result.name
    original.value = JSON.stringify(editor.value)
    await loadDocuments(result.name)
    toast.success(
      result.normalized
        ? __('Terms and Conditions saved. Unsupported dynamic text was preserved as agreement text.')
        : __('Terms and Conditions saved'),
    )
  } catch (error) {
    toast.error(error?.messages?.[0] ?? error?.message ?? __('Could not save Terms and Conditions'))
  } finally {
    saving.value = false
  }
}

async function setDefault() {
  settingDefault.value = true
  try {
    await defaultResource.submit({ name: editor.value.name })
    activeName.value = editor.value.name
    documents.value = documents.value.map((document) => ({ ...document, active: document.name === activeName.value }))
    toast.success(__('Default Opt-In agreement updated'))
  } catch (error) {
    toast.error(error?.messages?.[0] ?? error?.message ?? __('Could not update the default agreement'))
  } finally {
    settingDefault.value = false
  }
}

function formatDate(value) {
  return value ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(value)) : ''
}

loadDocuments()
</script>
