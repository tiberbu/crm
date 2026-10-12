<template>
  <nav class="overflow-x-auto border-b border-outline-gray-1" :aria-label="ariaLabel">
    <div class="flex min-w-max gap-1" role="tablist">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        type="button"
        role="tab"
        :aria-selected="modelValue === tab.key"
        :tabindex="modelValue === tab.key ? 0 : -1"
        class="-mb-px rounded-t-md border-b-2 px-3 py-2.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-blue-3 sm:px-4"
        :class="modelValue === tab.key
          ? 'border-outline-red-5 text-ink-red-7'
          : 'border-transparent text-ink-gray-5 hover:border-outline-gray-2 hover:text-ink-gray-8'"
        @click="$emit('update:modelValue', tab.key)"
      >{{ tab.label }}</button>
    </div>
  </nav>
</template>

<script setup>
defineProps({
  modelValue: { type: String, required: true },
  tabs: { type: Array, default: () => [] },
  ariaLabel: { type: String, default: 'Section views' },
})

defineEmits(['update:modelValue'])
</script>
