import { call } from 'frappe-ui'
import { ref, watch } from 'vue'

// Facility IDs for records that carry only MFL codes (quotes, opt-in submissions, finance
// documents). `mflCodes` is a getter; the lookup reruns when its codes change.
export function useFacilityIds(mflCodes) {
  const ids = ref({})
  let request = 0
  watch(
    () => [...new Set((mflCodes() || []).map((code) => String(code || '').trim()).filter(Boolean))].sort().join('|'),
    async (key) => {
      const codes = key ? key.split('|') : []
      const current = ++request
      if (!codes.length) {
        ids.value = {}
        return
      }
      try {
        const found = await call('crm.api.facility_ids.get_facility_ids', { mfl_codes: codes })
        if (current === request) ids.value = found || {}
      } catch {
        if (current === request) ids.value = {}
      }
    },
    { immediate: true },
  )
  const facilityIdFor = (mflCode) => ids.value[String(mflCode || '').trim()] || ''
  return { facilityIdFor }
}
