<template>
  <div class="flex h-full flex-col gap-4 px-3 pb-5 sm:px-10">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <p class="text-base text-ink-gray-7">
        {{
          __(
            "Onboarding, site keys and token balances for this deal's facilities.",
          )
        }}
      </p>
      <div class="flex flex-wrap gap-2">
        <Button
          :label="__('Test connection')"
          :loading="busy === 'test_connection'"
          @click="testConnection"
        />
        <Button
          :label="__('Import sites from CRM')"
          :loading="busy === 'import_sites'"
          @click="importSites"
        />
        <Dropdown :options="moreActions">
          <Button :label="__('More')" />
        </Dropdown>
      </div>
    </div>

    <div v-if="facilities.loading" class="text-base text-ink-gray-6">
      {{ __('Loading facilities…') }}
    </div>
    <p v-else-if="facilities.error" class="text-base text-ink-red-4">
      {{
        facilities.error.messages?.join(' ') ||
        __("Could not load this deal's facilities.")
      }}
    </p>
    <p v-else-if="!facilities.data?.length" class="text-base text-ink-gray-7">
      {{ __('This deal has no facilities yet.') }}
    </p>
    <FacilityMeteringCard
      v-for="facility in facilities.data || []"
      :key="facility.fid || facility.facility_name"
      :ref="(el) => (cards[facility.fid] = el)"
      :facility="facility"
      :can-reveal="canReveal"
      :busy="busyFid === facility.fid ? busy : null"
      @action="({ action, fid }) => runAndReload(action, fid)"
      @import="importSites"
      @issue="(fid) => confirm('issue', fid)"
      @reissue="(fid) => confirm('reissue', fid)"
      @reveal="openReveal"
      @probe="sendProbe"
    />

    <Dialog
      v-model="confirmDialog.show"
      :options="{ title: confirmDialog.title, size: 'md' }"
    >
      <template #body-content>
        <p class="text-base text-ink-gray-7">{{ confirmDialog.message }}</p>
      </template>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button
            variant="subtle"
            :label="__('Cancel')"
            @click="confirmDialog.show = false"
          />
          <Button
            variant="solid"
            theme="red"
            :label="confirmDialog.confirmLabel"
            @click="confirmDialog.onConfirm"
          />
        </div>
      </template>
    </Dialog>

    <Dialog
      v-model="revealDialog.show"
      :options="{ title: __('Confirm your password'), size: 'sm' }"
      @close="revealDialog.password = ''"
    >
      <template #body-content>
        <p class="mb-3 text-base text-ink-gray-7">
          {{
            __(
              'Enter the Administrator password to reveal the full site key for {0}. The reveal is recorded on the site.',
              [revealDialog.fid],
            )
          }}
        </p>
        <FormControl
          v-model="revealDialog.password"
          type="password"
          :label="__('Administrator password')"
          autocomplete="current-password"
          @keydown.enter="reveal"
        />
        <p v-if="revealDialog.error" class="mt-2 text-sm text-ink-red-4">
          {{ revealDialog.error }}
        </p>
      </template>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button
            variant="subtle"
            :label="__('Cancel')"
            @click="revealDialog.show = false"
          />
          <Button
            variant="solid"
            :label="__('Reveal')"
            :loading="revealDialog.loading"
            :disabled="!revealDialog.password"
            @click="reveal"
          />
        </div>
      </template>
    </Dialog>

    <Dialog
      v-model="keyDialog.show"
      :options="{ title: keyDialog.title, size: 'lg' }"
      @after-leave="keyDialog.key = ''"
    >
      <template #body-content>
        <p class="mb-3 text-base text-ink-gray-7">{{ keyDialog.note }}</p>
        <div
          class="break-all rounded bg-surface-gray-2 p-3 font-mono text-sm text-ink-gray-9"
        >
          {{ keyDialog.key }}
        </div>
        <p v-if="keyDialog.header" class="mt-3 text-sm text-ink-gray-7">
          {{ __('Header') }}: <code>{{ keyDialog.header }}</code>
        </p>
        <p v-if="keyDialog.endpoint" class="text-sm text-ink-gray-7">
          {{ __('Endpoint') }}: <code>{{ keyDialog.endpoint }}</code>
        </p>
        <p v-if="keyDialog.suspended" class="mt-3 text-sm text-ink-red-4">
          {{
            __(
              'This site is suspended, so the key is refused until the site is Active again.',
            )
          }}
        </p>
      </template>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button
            variant="subtle"
            :label="__('Close')"
            @click="keyDialog.show = false"
          />
          <Button
            variant="solid"
            :label="__('Copy key')"
            @click="copyToClipboard(keyDialog.key)"
          />
        </div>
      </template>
    </Dialog>

    <Dialog
      v-model="rolloutDialog.show"
      :options="{ title: __('Site keys for existing facilities'), size: '2xl' }"
    >
      <template #body-content>
        <p class="mb-3 text-base text-ink-gray-7">
          {{
            __(
              'These facilities have no delivered key. Sending keys issues one for each facility whose HMIS site already exists and has the setup service deliver it in a signed license update. Nobody sees the key.',
            )
          }}
        </p>
        <table v-if="rolloutDialog.rows.length" class="w-full text-sm">
          <thead class="text-left text-ink-gray-6">
            <tr>
              <th class="py-1 font-normal">{{ __('Facility ID') }}</th>
              <th class="py-1 font-normal">{{ __('Facility') }}</th>
              <th class="py-1 font-normal">{{ __('Site') }}</th>
              <th class="py-1 font-normal">{{ __('Key delivery') }}</th>
            </tr>
          </thead>
          <tbody class="text-ink-gray-8">
            <tr
              v-for="row in rolloutDialog.rows"
              :key="row.fid"
              class="border-t border-outline-gray-1"
            >
              <td class="py-1">{{ row.fid }}</td>
              <td class="py-1">{{ row.facility_name }}</td>
              <td class="py-1">
                {{ __(row.status)
                }}<span v-if="row.sync_status">
                  · {{ __(row.sync_status) }}</span
                >
              </td>
              <td class="py-1">
                {{
                  row.site_key_delivery
                    ? __(row.site_key_delivery)
                    : __('No key')
                }}
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else class="text-base text-ink-gray-7">
          {{ __('Every facility has a delivered site key.') }}
        </p>
      </template>
      <template #actions>
        <div class="flex justify-end gap-2">
          <Button
            variant="subtle"
            :label="__('Close')"
            @click="rolloutDialog.show = false"
          />
          <Button
            v-if="rolloutDialog.rows.length"
            variant="solid"
            :label="__('Send keys to existing HMIS sites')"
            :loading="busy === 'deliver_keys'"
            @click="deliverKeys"
          />
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import {
  Button,
  Dialog,
  Dropdown,
  FormControl,
  call,
  createResource,
  toast,
} from 'frappe-ui'
import FacilityMeteringCard from './FacilityMeteringCard.vue'
import { copyToClipboard } from '@/utils'
import { probeOutcome } from '@/utils/metering'
import { useMeteringAccess } from '@/composables/meteringAccess'

const props = defineProps({
  dealId: { type: String, required: true },
})
const { canReveal } = useMeteringAccess()

const API = 'crm.api.metering_admin.'
const busy = ref(null)
const busyFid = ref(null)
const cards = reactive({})

const facilities = createResource({
  url: API + 'get_deal_facilities',
  method: 'GET',
  params: { deal: props.dealId },
  auto: true,
})

const moreActions = [
  {
    label: __('Site keys for existing facilities'),
    onClick: () => openRollout(),
  },
  { label: __('Scan paid token purchases'), onClick: () => scanPurchases() },
]

function message(error) {
  return (
    error?.messages?.join(' ') || error?.message || __('Something went wrong.')
  )
}

async function runAction(action, fid = null, params = {}) {
  busy.value = action
  busyFid.value = fid
  try {
    return await call(API + 'run_action', { action, fid, params })
  } catch (error) {
    toast.error(message(error))
    return null
  } finally {
    busy.value = null
    busyFid.value = null
  }
}

function reloadCards() {
  Object.values(cards).forEach((card) => card?.reload())
}

async function runAndReload(action, fid) {
  const result = await runAction(action, fid)
  if (!result) return
  if (action === 'sync') {
    if (result.error) toast.error(result.error)
    else toast.success(__('Synced to OpenMeter'))
  } else if (action === 'retry_failed') {
    toast.success(__('{0} failed event(s) requeued', [result.requeued]))
  }
  cards[fid]?.reload()
}

async function testConnection() {
  const result = await runAction('test_connection')
  if (!result) return
  if (result.status === 'Reachable') toast.success(result.message)
  else toast.error(result.message)
  reloadCards()
}

async function importSites() {
  const result = await runAction('import_sites')
  if (!result) return
  toast.success(
    __(
      'Created {0}, updated {1}, skipped {2}. New sites are Draft: set them Active to start metering.',
      [result.created.length, result.updated.length, result.skipped.length],
    ),
  )
  reloadCards()
}

async function scanPurchases() {
  const result = await runAction('scan_purchases')
  if (result) toast.success(__('Paid token purchases scanned'))
  reloadCards()
}

async function sendProbe(fid) {
  const result = await runAction('send_probe', fid)
  if (!result) return
  const outcome = probeOutcome(result)
  if (!outcome.delivered) {
    toast.error(__('Probe not delivered: {0}', [outcome.message]))
    return cards[fid]?.reload()
  }
  toast.info(__('Probe delivered. Checking OpenMeter stored it…'))
  // OpenMeter stores events asynchronously; check a few times.
  for (let i = 0; i < 6; i++) {
    await new Promise((resolve) => setTimeout(resolve, 2000))
    const check = await runAction('verify_probe', fid, { event: outcome.event })
    if (check?.found) {
      toast.success(
        __(
          'Round trip confirmed: OpenMeter stored the probe event. It does not count toward usage.',
        ),
      )
      return cards[fid]?.reload()
    }
  }
  toast.warning(
    __('Delivered, but not visible in OpenMeter yet. Refresh in a minute.'),
  )
  cards[fid]?.reload()
}

const confirmDialog = reactive({
  show: false,
  title: '',
  message: '',
  confirmLabel: '',
  onConfirm: null,
})

function confirm(kind, fid) {
  const texts = {
    issue: {
      title: __('Issue a new site key?'),
      message: __('Any existing key for {0} stops working immediately.', [fid]),
      confirmLabel: __('Issue key'),
      onConfirm: () => issueKey(fid),
    },
    reissue: {
      title: __('Re-issue expiring grants?'),
      message: __(
        'Replace grants for {0} that expire or lose tokens at a reset with one grant for their remaining tokens. Run it while the site is quiet.',
        [fid],
      ),
      confirmLabel: __('Re-issue grants'),
      onConfirm: () => reissueGrants(fid),
    },
  }[kind]
  Object.assign(confirmDialog, texts, { show: true })
}

const keyDialog = reactive({
  show: false,
  title: '',
  note: '',
  key: '',
  header: '',
  endpoint: '',
  suspended: false,
})

function showKey(result, title, note) {
  Object.assign(keyDialog, {
    show: true,
    title,
    note,
    key: result.key,
    header: result.header,
    endpoint: result.endpoint,
    suspended: result.status === 'Suspended',
  })
}

async function issueKey(fid) {
  confirmDialog.show = false
  const result = await runAction('issue_key', fid)
  if (!result) return
  showKey(
    result,
    __('New site key — copy it now'),
    __(
      'Send it to the HMIS administrator over a secure channel. Later, only the Administrator can reveal it again.',
    ),
  )
  cards[fid]?.reload()
}

async function reissueGrants(fid) {
  confirmDialog.show = false
  const result = await runAction('reissue_grants', fid)
  if (result) toast.success(__('Grants re-issued'))
  cards[fid]?.reload()
}

// The key and the password live only in this component and are dropped when their dialog closes.
const revealDialog = reactive({
  show: false,
  fid: '',
  password: '',
  error: '',
  loading: false,
})

function openReveal(fid) {
  Object.assign(revealDialog, {
    show: true,
    fid,
    password: '',
    error: '',
    loading: false,
  })
}

async function reveal() {
  if (!revealDialog.password || revealDialog.loading) return
  revealDialog.loading = true
  revealDialog.error = ''
  try {
    const result = await call(API + 'reveal_key', {
      fid: revealDialog.fid,
      password: revealDialog.password,
    })
    revealDialog.show = false
    showKey(
      result,
      __('Site key for {0}', [revealDialog.fid]),
      __(
        "Share it with the facility's HMIS administrator over a secure channel.",
      ),
    )
    cards[revealDialog.fid]?.reload()
  } catch (error) {
    revealDialog.error = message(error)
  } finally {
    revealDialog.password = ''
    revealDialog.loading = false
  }
}

const rolloutDialog = reactive({ show: false, rows: [] })

async function openRollout() {
  const rows = await runAction('key_rollout_status')
  if (!rows) return
  Object.assign(rolloutDialog, { show: true, rows })
}

async function deliverKeys() {
  busy.value = 'deliver_keys'
  try {
    const result = await call('crm.api.hfr.deliver_metering_site_keys')
    rolloutDialog.show = false
    toast.success(
      __('Key delivery is queued (job {0}). Results appear on each site.', [
        result.job_id,
      ]),
    )
  } catch (error) {
    toast.error(message(error))
  } finally {
    busy.value = null
  }
}
</script>
