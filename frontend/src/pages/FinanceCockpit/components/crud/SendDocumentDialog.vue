<template>
  <Dialog v-model:open="open" :title="`Email ${documentLabel}`" :size="'md'">
    <div class="space-y-4">
      <p class="text-sm text-ink-gray-6">
        Send a PDF copy with the configured ERPNext Letter Head.
      </p>
      <FormControl
        v-model="recipient"
        type="email"
        label="Recipient"
        placeholder="customer@example.com"
        required
      />
      <FormControl v-model="subject" type="text" label="Subject" />
      <div>
        <label class="mb-1 block text-xs font-medium text-ink-gray-6">Message</label>
        <textarea
          v-model="message"
          rows="5"
          class="w-full rounded-lg border border-outline-gray-2 bg-surface-white px-3 py-2 text-sm text-ink-gray-8 focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
      </div>
      <p v-if="errorMessage" class="text-sm text-ink-red-6" role="alert">
        {{ errorMessage }}
      </p>
      <div class="flex justify-end gap-2">
        <Button variant="outline" theme="gray" @click="open = false">Cancel</Button>
        <Button
          variant="solid"
          theme="blue"
          :loading="sending"
          :disabled="sending || !recipient.trim()"
          @click="send"
        >
          Send copy
        </Button>
      </div>
    </div>
  </Dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Button, Dialog, FormControl, call, toast } from 'frappe-ui'
import { readableError } from '../../composables/useCrud.js'
import { printFormatFor } from '../../constants/printFormats.js'

const props = defineProps({
  doctype: { type: String, required: true },
  name: { type: String, required: true },
  doc: { type: Object, default: () => ({}) },
})

const open = defineModel('open', { type: Boolean, default: false })
const recipient = ref('')
const subject = ref('')
const message = ref('')
const sending = ref(false)
const errorMessage = ref('')

const documentLabel = computed(() => props.doctype.replace('Sales ', ''))

function reset() {
  recipient.value =
    props.doc.contact_email || props.doc.contact_person_email || props.doc.email || ''
  subject.value = `${documentLabel.value} ${props.name}`
  message.value = `Please find attached a copy of ${props.doctype} ${props.name}.`
  errorMessage.value = ''
}

watch(open, (value) => value && reset())

async function send() {
  errorMessage.value = ''
  sending.value = true
  try {
    await call('frappe.core.doctype.communication.email.make', {
      doctype: props.doctype,
      name: props.name,
      recipients: recipient.value.trim(),
      subject: subject.value.trim(),
      content: message.value,
      send_email: 1,
      print_format: printFormatFor(props.doctype) || undefined,
      print_letterhead: 1,
    })
    toast.success(`Sent ${documentLabel.value.toLowerCase()} copy`)
    open.value = false
  } catch (error) {
    errorMessage.value = readableError(error) || 'The document could not be sent.'
  } finally {
    sending.value = false
  }
}
</script>
