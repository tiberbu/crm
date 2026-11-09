import { createResource } from 'frappe-ui'
import { computed } from 'vue'

// Whether this site's metering app lets the user run OpenMeter Probe activities from the CRM.
const access = createResource({
  url: 'crm.api.metering_admin.get_access',
  method: 'GET',
  cache: 'crmMeteringAccess',
})

export function useMeteringAccess() {
  if (!access.fetched && !access.loading) access.fetch()
  return {
    canManage: computed(() =>
      Boolean(access.data?.enabled && access.data?.can_manage),
    ),
    canReveal: computed(() => Boolean(access.data?.can_reveal)),
  }
}
