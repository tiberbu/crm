<template>
  <div
    class="crm-mobile-shell flex h-screen w-screen overflow-hidden bg-surface-base"
  >
    <MobileSidebar />
    <div
      class="flex min-h-0 h-full flex-1 flex-col overflow-hidden bg-surface-base"
    >
      <MobileAppHeader />
      <main class="min-h-0 flex-1 overflow-hidden">
        <slot />
      </main>
    </div>
    <GlobalModals />
  </div>
</template>
<script setup>
import MobileSidebar from '@/components/Mobile/MobileSidebar.vue'
import MobileAppHeader from '@/components/Mobile/MobileAppHeader.vue'
import GlobalModals from '@/components/Modals/GlobalModals.vue'
</script>
