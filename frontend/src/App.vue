<template>
  <FrappeUIProvider>
    <NotPermitted v-if="$route.name === 'Not Permitted'" />
    <router-view v-else-if="$route.name === 'Onboarding'" />
    <Layout v-else-if="session.isLoggedIn" class="isolate">
      <router-view :key="$route.fullPath" />
    </Layout>
    <Dialogs />
    <DoctypeModals />
    <EventNotificationPopup />
  </FrappeUIProvider>
</template>

<script setup>
import NotPermitted from '@/pages/NotPermitted.vue'
import EventNotificationPopup from '@/components/EventNotificationPopup.vue'
import DoctypeModals from '@/components/Modals/DoctypeModals.vue'
import { Dialogs } from '@/utils/dialogs'
import { sessionStore } from '@/stores/session'
import { FrappeUIProvider, setConfig, useIsMobile, useTheme } from 'frappe-ui'
import { computed, defineAsyncComponent, provide, ref } from 'vue'
import { createResource } from 'frappe-ui'

const session = sessionStore()
provide('session', session)

const hfrEnabled = ref(false)
provide('hfrEnabled', hfrEnabled)

createResource({
  url: 'crm.api.hfr.get_hfr_settings',
  auto: true,
  onSuccess(data) {
    hfrEnabled.value = !!(data && data.hfr_enabled)
  },
})

const { setTheme } = useTheme()
if (!localStorage.getItem('theme')) {
  setTheme('light')
}

const MobileLayout = defineAsyncComponent(
  () => import('./components/Layouts/MobileLayout.vue'),
)
const DesktopLayout = defineAsyncComponent(
  () => import('./components/Layouts/DesktopLayout.vue'),
)
// Keep the shell in sync with viewport changes (orientation changes, split
// view, and browser resizing). The old one-time width check left the CRM in
// the wrong shell until a full reload.
// Keep the shell breakpoint aligned with the router/mobile page breakpoint so
// tablet-sized viewports do not render a mobile page inside the desktop shell.
const isMobileShell = useIsMobile(768)
const Layout = computed(() =>
  isMobileShell.value ? MobileLayout : DesktopLayout,
)

setConfig('systemTimezone', window.timezone?.system || null)
setConfig('localTimezone', window.timezone?.user || null)
setConfig('translatedMessages', window.translated_messages || {})
</script>
