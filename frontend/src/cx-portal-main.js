import './index.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { FrappeUI, frappeRequest, setConfig } from 'frappe-ui'

import FacilityPortal from './pages/FacilityPortal/FacilityPortal.vue'
import translationPlugin from './translation'

const el = document.getElementById('facility-portal-app')
const app = createApp(FacilityPortal)

setConfig('resourceFetcher', frappeRequest)
app.use(FrappeUI)
app.use(createPinia())
app.use(translationPlugin)
app.mount(el || '#facility-portal-app')
