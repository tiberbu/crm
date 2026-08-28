<template>
  <div class="flex h-full flex-col overflow-hidden">

    <!-- Header -->
    <div class="flex items-center justify-between border-b border-outline-gray-2 px-5 py-3">
      <h1 class="text-xl font-semibold text-ink-gray-9">{{ __('Opt-In Networks') }}</h1>
      <Button variant="solid" size="sm" @click="router.push({ name: 'NewNetwork' })">{{ __('Add Network') }}</Button>
    </div>

    <!-- Table area -->
    <div class="flex-1 overflow-auto">
      <div v-if="listResource.loading" class="flex items-center justify-center py-16">
        <div class="h-6 w-6 animate-spin rounded-full border-2 border-red-600 border-t-transparent" />
      </div>

      <div v-else-if="!rows.length" class="flex flex-col items-center justify-center py-16 text-center">
        <p class="text-sm font-medium text-ink-gray-5">{{ __('No networks found') }}</p>
        <p class="mt-1 text-xs text-ink-gray-4">{{ __('Create a network to configure its portal, pricing, partners, coordinators, and signatories.') }}</p>
      </div>

      <table v-else class="w-full text-sm">
        <thead class="sticky top-0 z-10 bg-surface-gray-1 text-xs uppercase tracking-wide text-ink-gray-5">
          <tr>
            <th class="px-5 py-2.5 text-left font-medium">{{ __('Display Name') }}</th>
            <th class="px-4 py-2.5 text-left font-medium">{{ __('Slug') }}</th>
            <th class="px-4 py-2.5 text-left font-medium">{{ __('Status') }}</th>
            <th class="px-4 py-2.5 text-left font-medium">{{ __('Contact Email') }}</th>
            <th class="px-4 py-2.5 text-left font-medium">{{ __('Footer Name') }}</th>
            <th class="px-4 py-2.5 text-right font-medium"></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-outline-elevation-2">
          <tr
            v-for="row in rows"
            :key="row.name"
            class="cursor-pointer transition-colors hover:bg-surface-gray-1"
            @click="openNetwork(row)"
          >
            <td class="px-5 py-3 font-medium text-ink-gray-9">{{ row.display_name }}</td>
            <td class="px-4 py-3 font-mono text-xs text-ink-gray-6">{{ row.slug }}</td>
            <td class="px-4 py-3">
              <span :class="statusPill(row.enabled)">
                {{ row.enabled ? __('Enabled') : __('Disabled') }}
              </span>
            </td>
            <td class="px-4 py-3 text-xs text-ink-gray-6">{{ row.contact_email || '—' }}</td>
            <td class="px-4 py-3 text-xs text-ink-gray-6">{{ row.footer_legal_name || '—' }}</td>
            <td class="px-4 py-3 text-right text-ink-gray-4">
              <svg xmlns="http://www.w3.org/2000/svg" class="inline h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="9 18 15 12 9 6"/>
              </svg>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- Pagination -->
      <div v-if="total > pageSize" class="flex items-center justify-between border-t border-outline-gray-2 px-5 py-3">
        <span class="text-xs text-ink-gray-5">
          {{ __('Showing {0}–{1} of {2}', [page * pageSize + 1, Math.min((page + 1) * pageSize, total), total]) }}
        </span>
        <div class="flex gap-2">
          <Button size="sm" variant="subtle" :disabled="page === 0" @click="prevPage">{{ __('Prev') }}</Button>
          <Button size="sm" variant="subtle" :disabled="(page + 1) * pageSize >= total" @click="nextPage">{{ __('Next') }}</Button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { createResource, Button } from 'frappe-ui'

const router = useRouter()

const page = ref(0)
const pageSize = 20
const listResource = createResource({
  url: 'crm.api.optin_admin.list_networks',
  makeParams: () => ({ page: page.value, page_size: pageSize }),
  auto: true,
})

const rows = computed(() => listResource.data?.rows ?? [])
const total = computed(() => listResource.data?.total ?? 0)

function openNetwork(row) {
  router.push({ name: 'NetworkDetail', params: { networkSlug: row.slug } })
}

function prevPage() {
  page.value--
  listResource.reload()
}

function nextPage() {
  page.value++
  listResource.reload()
}

function statusPill(enabled) {
  const base = 'rounded-full px-2 py-0.5 text-xs font-medium'
  return enabled
    ? `${base} bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400`
    : `${base} bg-surface-gray-2 text-ink-gray-6 dark:bg-surface-gray-4 dark:text-ink-gray-4`
}
</script>
