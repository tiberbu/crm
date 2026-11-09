import './index.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { FrappeUI, setConfig, frappeRequest } from 'frappe-ui'

import FacilityOnboardingLanding from './pages/FacilityOnboarding/FacilityOnboardingLanding.vue'
import translationPlugin from './translation'

const el = document.getElementById('facility-onboarding-app')
const params = new URLSearchParams(window.location.search)
const networkSlug = el?.dataset.network || params.get('network') || ''
const facilityName = el?.dataset.facility || params.get('facility') || ''

const app = createApp(FacilityOnboardingLanding, {
  networkSlug,
  facilityName,
  invitationToken: params.get('invitation') || '',
})

setConfig('resourceFetcher', frappeRequest)
app.use(FrappeUI)
app.use(createPinia())
app.use(translationPlugin)

app.mount(el || '#facility-onboarding-app')
