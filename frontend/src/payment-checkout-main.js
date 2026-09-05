import './index.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { FrappeUI, frappeRequest, setConfig } from 'frappe-ui'

import PaymentCheckout from './pages/PaymentCheckout.vue'
import translationPlugin from './translation'

const el = document.getElementById('payment-checkout-app')
const app = createApp(PaymentCheckout, {
  initialOis: el?.dataset.ois || '',
})

setConfig('resourceFetcher', frappeRequest)
app.use(FrappeUI)
app.use(createPinia())
app.use(translationPlugin)
app.mount(el || '#payment-checkout-app')
