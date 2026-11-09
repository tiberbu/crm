<template>
  <section
    class="rounded-xl border px-4 py-4"
    :class="toneClass"
    role="alert"
    aria-live="polite"
  >
    <div class="flex items-start gap-3">
      <span :class="[iconClass, 'mt-0.5 size-4 shrink-0']" aria-hidden="true" />
      <div class="min-w-0 flex-1">
        <h3 class="text-sm font-semibold">{{ presentation.title }}</h3>
        <p class="mt-1 text-sm leading-5">{{ presentation.message }}</p>
        <p class="mt-2 text-xs leading-5 opacity-80">{{ presentation.nextStep }}</p>
        <p v-if="presentation.reference" class="mt-2 font-mono text-[11px] opacity-70">
          Reference: {{ presentation.reference }}
        </p>
        <div class="mt-3 flex flex-wrap gap-2">
          <button
            v-if="presentation.retryable"
            type="button"
            class="rounded-md border border-current/20 bg-white/60 px-2.5 py-1.5 text-xs font-semibold hover:bg-white"
            @click="$emit('retry')"
          >
            Retry
          </button>
          <button
            v-if="presentation.kind === 'permission'"
            type="button"
            class="rounded-md border border-current/20 px-2.5 py-1.5 text-xs font-semibold hover:bg-white/60"
            @click="$emit('change-company')"
          >
            Change company
          </button>
          <button
            v-if="presentation.kind === 'configuration'"
            type="button"
            class="rounded-md border border-current/20 px-2.5 py-1.5 text-xs font-semibold hover:bg-white/60"
            @click="$emit('contact-support')"
          >
            Contact support
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { getErrorPresentation } from '../composables/financeErrors.js'

const props = defineProps({
  error: { type: [Object, String], default: null },
})

defineEmits(['retry', 'change-company', 'contact-support'])

const presentation = computed(() => getErrorPresentation(props.error))
const toneClass = computed(() => {
  if (presentation.value.kind === 'permission') return 'border-outline-amber-2 bg-surface-amber-1 text-ink-amber-8'
  if (presentation.value.kind === 'configuration') return 'border-outline-red-2 bg-surface-red-1 text-ink-red-8'
  return 'border-outline-red-2 bg-surface-red-1 text-ink-red-7'
})
const iconClass = computed(() => {
  if (presentation.value.kind === 'permission') return 'lucide-lock-keyhole'
  if (presentation.value.kind === 'configuration') return 'lucide-server-off'
  return 'lucide-circle-alert'
})
</script>
