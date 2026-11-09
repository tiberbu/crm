<template>
  <div
    v-if="pager.pages > 1"
    class="flex items-center justify-between gap-2 border-t border-outline-gray-2 px-4 py-2 text-xs text-ink-gray-5"
    data-testid="c360-pager"
  >
    <span data-testid="c360-pager-label">
      {{ __('{0}–{1} of {2}', [pager.start, pager.end, pager.total]) }}
    </span>
    <div class="flex items-center gap-1">
      <Button
        variant="ghost"
        size="sm"
        :disabled="pager.page <= 1"
        :aria-label="__('Previous page')"
        data-testid="c360-pager-prev"
        @click="emit('update:page', pager.page - 1)"
      >
        <template #icon><LucideChevronLeft class="size-4" /></template>
      </Button>
      <Button
        variant="ghost"
        size="sm"
        :disabled="pager.page >= pager.pages"
        :aria-label="__('Next page')"
        data-testid="c360-pager-next"
        @click="emit('update:page', pager.page + 1)"
      >
        <template #icon><LucideChevronRight class="size-4" /></template>
      </Button>
    </div>
  </div>
</template>

<script setup>
import { Button } from 'frappe-ui'
import LucideChevronLeft from '~icons/lucide/chevron-left'
import LucideChevronRight from '~icons/lucide/chevron-right'

// pager: the result of paginate() from @/utils/customer360.js
defineProps({
	pager: { type: Object, required: true },
})
const emit = defineEmits(['update:page'])
</script>
