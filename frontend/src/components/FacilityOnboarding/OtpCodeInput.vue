<template>
  <div>
    <div
      role="group"
      :aria-label="label"
      :aria-describedby="error ? errorId : undefined"
      class="flex justify-center gap-1.5 sm:gap-3"
    >
      <input
        v-for="(_, index) in length"
        :key="index"
        :ref="(el) => (boxes[index] = el)"
        :value="digits[index] || ''"
        :disabled="disabled"
        :aria-label="`${label}: ${index + 1} / ${length}`"
        :aria-invalid="error ? 'true' : undefined"
        :autocomplete="index === 0 ? 'one-time-code' : 'off'"
        inputmode="numeric"
        pattern="[0-9]*"
        :maxlength="index === 0 && !digits.length ? length : 1"
        class="size-10 sm:size-14 rounded-lg border bg-surface-white text-center text-lg sm:text-xl font-semibold text-ink-gray-9 outline-none transition focus:border-[#bc1823] focus:ring-2 focus:ring-[#bc1823]/30 disabled:opacity-50"
        :class="error ? 'border-outline-red-2' : 'border-outline-gray-3'"
        @input="onInput(index, $event)"
        @keydown="onKeydown(index, $event)"
        @paste.prevent="onPaste(index, $event)"
        @focus="$event.target.select()"
      />
    </div>
    <p
      v-if="error"
      :id="errorId"
      class="mt-3 text-center text-sm text-ink-red-7"
      role="alert"
    >
      {{ error }}
    </p>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUpdate } from 'vue'
import {
  OTP_LENGTH,
  applyBackspace,
  applyInput,
  applyPaste,
  isComplete,
  sanitizeOtp,
} from '@/utils/otpCode'

const props = defineProps({
  modelValue: { type: String, default: '' },
  length: { type: Number, default: OTP_LENGTH },
  disabled: { type: Boolean, default: false },
  error: { type: String, default: '' },
  label: { type: String, default: 'Verification code' },
})
const emit = defineEmits(['update:modelValue', 'complete'])

const boxes = []
const errorId = `otp-error-${Math.random().toString(36).slice(2, 8)}`
const digits = computed(() => sanitizeOtp(props.modelValue, props.length))

onBeforeUpdate(() => {
  boxes.length = 0
})

function commit({ code, focusIndex }) {
  emit('update:modelValue', code)
  if (isComplete(code, props.length)) emit('complete', code)
  nextTick(() => boxes[focusIndex]?.focus())
}

function onInput(index, event) {
  const next = applyInput(digits.value, index, event.target.value, props.length)
  // Keep the DOM in step with the model when a non-digit was rejected.
  event.target.value = next.code[index] || ''
  commit(next)
}

function onKeydown(index, event) {
  if (event.key === 'Backspace') {
    event.preventDefault()
    commit(applyBackspace(digits.value, index, props.length))
  } else if (event.key === 'ArrowLeft' && index > 0) {
    event.preventDefault()
    boxes[index - 1]?.focus()
  } else if (event.key === 'ArrowRight' && index < props.length - 1) {
    event.preventDefault()
    boxes[index + 1]?.focus()
  }
}

function onPaste(index, event) {
  commit(
    applyPaste(
      digits.value,
      index,
      event.clipboardData?.getData('text') || '',
      props.length,
    ),
  )
}
</script>
