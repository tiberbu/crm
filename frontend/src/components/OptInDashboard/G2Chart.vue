<template>
  <div class="relative" :style="{ height: `${height}px` }">
    <div
      v-if="!hasData"
      class="absolute inset-0 grid place-items-center text-sm text-ink-gray-4"
    >
      {{ emptyLabel }}
    </div>
    <div
      ref="container"
      class="h-full w-full"
      :class="!hasData && 'invisible'"
    />
  </div>
</template>

<script setup>
import { Chart } from '@antv/g2'
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  options: { type: Object, required: true },
  hasData: { type: Boolean, default: true },
  height: { type: Number, default: 264 },
  emptyLabel: { type: String, default: 'No activity in this period' },
})

const container = ref(null)
let chart = null

function destroyChart() {
  chart?.destroy()
  chart = null
}

async function renderChart() {
  destroyChart()
  if (!props.hasData) return

  await nextTick()
  if (!container.value) return

  chart = new Chart({
    container: container.value,
    autoFit: true,
    height: props.height,
  })
  chart.options(props.options)
  await chart.render()
}

watch(() => [props.options, props.hasData, props.height], renderChart, {
  deep: true,
  immediate: true,
})

onBeforeUnmount(destroyChart)
</script>
