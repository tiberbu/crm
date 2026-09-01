import { computed, ref } from 'vue'

export const mobileSidebarOpened = ref(false)

// This module is imported by shared CRM controls, so keep one small reactive
// viewport signal instead of each component reading window.innerWidth once.
// It also makes the existing mobile affordances respond to rotation/resizing.
const viewportWidth = ref(
  typeof window === 'undefined' ? 1024 : window.innerWidth,
)

if (typeof window !== 'undefined') {
  window.addEventListener(
    'resize',
    () => {
      viewportWidth.value = window.innerWidth
    },
    { passive: true },
  )
}

export const isMobileView = computed(() => viewportWidth.value < 768)

export const showSettings = ref(false)

export const disableSettingModalOutsideClick = ref(false)

export const activeSettingsPage = ref('')
