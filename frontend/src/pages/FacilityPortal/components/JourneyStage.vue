<script setup>
import { computed, ref } from 'vue'
import CxIcon from './CxIcon.vue'

const props = defineProps({
  stageKey: { type: String, required: true },
  title: { type: String, required: true },
  rows: { type: Array, default: () => [] },
  emptyText: { type: String, default: '' },
  sectionId: { type: String, default: '' },
  limit: { type: Number, default: 5 },
})

const expanded = ref(false)
const count = computed(() => props.rows.length)
const visibleRows = computed(() => (expanded.value ? props.rows : props.rows.slice(0, props.limit)))

function expand() {
  expanded.value = true
}

defineExpose({ expand })
</script>

<template>
  <section
    class="rounded-cx border border-cx-border bg-cx-surface p-5 shadow-cx"
    :data-testid="`stage-${stageKey}`"
    :id="sectionId"
  >
    <div class="mb-4 flex items-center justify-between gap-3">
      <h3 class="text-lg font-semibold text-cx-ink">{{ title }}</h3>
      <span class="rounded-full bg-cx-well px-2.5 py-1 text-[11px] font-semibold text-cx-ink-2">{{ count }}</span>
    </div>
    <div v-if="!rows.length" class="rounded-cx-sm bg-cx-well p-4 text-xs text-cx-ink-2">{{ emptyText }}</div>
    <div v-else>
      <div class="divide-y divide-cx-border-soft">
        <slot
          v-for="row in visibleRows"
          :key="row.name"
          :row="row"
        />
      </div>
      <div v-if="rows.length > limit" class="pt-3">
        <button
          type="button"
          class="inline-flex min-h-10 items-center gap-1.5 rounded-cx-sm border border-cx-border bg-cx-surface px-3 py-2 text-xs font-semibold text-cx-brand hover:bg-cx-well"
          :aria-expanded="expanded"
          :data-testid="`stage-${stageKey}-toggle`"
          @click="expanded = !expanded"
        >
          <CxIcon name="chevron-down" class="size-3.5" :class="expanded ? 'rotate-180' : ''" />
          {{ expanded ? 'Show fewer' : `Show all ${rows.length}` }}
        </button>
      </div>
    </div>
  </section>
</template>
