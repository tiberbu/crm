<template>
  <div class="rounded-lg border border-outline-gray-2 p-4 sm:p-5">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div class="min-w-0">
        <div class="text-lg-semibold text-ink-gray-9">
          {{ __('Facility ID') }}: {{ facility.fid || __('not set') }}
        </div>
        <div class="mt-0.5 text-sm text-ink-gray-6">
          {{ facility.facility_name || __('Unnamed facility') }}
          <span v-if="facility.mfl_code"> · MFL {{ facility.mfl_code }}</span>
        </div>
      </div>
      <div v-if="data?.imported" class="flex flex-wrap items-center gap-1.5">
        <Badge :label="__(site.status)" :theme="tone('status', site.status)" />
        <Badge
          :label="__(site.sync_status)"
          :theme="tone('sync', site.sync_status)"
        />
        <Badge
          v-if="data.entitlement"
          :label="
            data.entitlement.hasAccess ? __('Has access') : __('No access')
          "
          :theme="data.entitlement.hasAccess ? 'green' : 'red'"
        />
        <Button
          :label="__('Refresh')"
          size="sm"
          :loading="probe.loading"
          @click="probe.reload()"
        />
      </div>
    </div>

    <p v-if="!facility.fid" class="mt-3 text-base text-ink-gray-7">
      {{
        __(
          "This facility has no Facility ID. Add it on the deal's facility row before metering it.",
        )
      }}
    </p>
    <div
      v-else-if="probe.loading && !data"
      class="mt-3 text-base text-ink-gray-6"
    >
      {{ __('Loading metering…') }}
    </div>
    <p v-else-if="probe.error" class="mt-3 text-base text-ink-red-4">
      {{ errorText(probe.error) }}
    </p>
    <div
      v-else-if="data && !data.imported"
      class="mt-3 flex flex-wrap items-center gap-3"
    >
      <span class="text-base text-ink-gray-7">{{
        __('Not imported into metering yet.')
      }}</span>
      <Button
        :label="__('Import sites from CRM')"
        :loading="busy === 'import_sites'"
        @click="emit('import')"
      />
    </div>

    <template v-else-if="data">
      <div
        v-if="errors.length"
        class="mt-3 rounded bg-surface-red-1 p-3 text-sm text-ink-red-4"
      >
        <div v-for="[section, message] in errors" :key="section">
          <span class="font-medium">{{ section }}:</span> {{ message }}
        </div>
      </div>

      <div class="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div
          v-for="stat in stats"
          :key="stat.label"
          class="rounded border border-outline-gray-1 p-3"
        >
          <div class="text-sm text-ink-gray-6">{{ __(stat.label) }}</div>
          <div class="mt-1 text-2xl-semibold text-ink-gray-9">
            {{
              stat.value === null ? '—' : Number(stat.value).toLocaleString()
            }}
          </div>
          <div v-if="stat.hint" class="mt-0.5 text-sm text-ink-gray-6">
            {{ stat.hint }}
          </div>
        </div>
      </div>

      <div class="mt-5">
        <div class="text-base-semibold text-ink-gray-8">
          {{ __('Site key') }}
        </div>
        <p class="mt-1 text-base text-ink-gray-7">
          <template v-if="site.site_key_prefix">
            {{
              __('Issued {0} ({1} delivery). Last event received: {2}.', [
                formatDate(site.site_key_issued_on),
                __(site.site_key_delivery || 'Manual'),
                site.last_event_at
                  ? formatDate(site.last_event_at)
                  : __('never'),
              ])
            }}
          </template>
          <template v-else>{{ __('No key issued yet.') }}</template>
        </p>
        <div class="mt-2 flex flex-wrap items-center gap-2">
          <code
            v-if="site.site_key_prefix"
            class="select-none rounded bg-surface-gray-2 px-2 py-1 text-sm text-ink-gray-8"
            >{{ maskedKey(site.site_key_prefix) }}</code
          >
          <Button
            v-if="keyMode === 'revealable'"
            :label="__('Reveal full key')"
            @click="emit('reveal', facility.fid)"
          />
          <Button
            v-if="keyMode !== 'legacy'"
            :label="__('Issue site key')"
            :loading="busy === 'issue_key'"
            @click="emit('issue', facility.fid)"
          />
        </div>
        <div
          v-if="keyMode === 'legacy'"
          class="mt-3 rounded border border-outline-amber-2 bg-surface-amber-1 p-3"
        >
          <p class="text-base text-ink-gray-8">
            {{
              __(
                "This key was issued before CRM kept a copy, so it can't be shown. Issue a new key to get one you can copy now and reveal again later.",
              )
            }}
          </p>
          <p class="mt-1 text-sm text-ink-gray-7">
            {{
              site.last_event_at
                ? __(
                    'This facility has used the current key (last event {0}). Its HMIS site stops sending until it has the new key.',
                    [formatDate(site.last_event_at)],
                  )
                : __(
                    "No events have arrived with the current key, so replacing it shouldn't interrupt the facility.",
                  )
            }}
          </p>
          <Button
            class="mt-2"
            variant="solid"
            :label="__('Issue a new key to copy')"
            :loading="busy === 'issue_key'"
            @click="emit('issue', facility.fid)"
          />
        </div>
      </div>

      <div class="mt-5">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="text-base-semibold text-ink-gray-8">
            {{ __('Recent events') }}
            <span class="ml-1 text-sm font-normal text-ink-gray-6">
              {{
                __('Queued {0} · Delivered {1} · Failed {2}', [
                  data.queue.Queued,
                  data.queue.Delivered,
                  data.queue.Failed,
                ])
              }}
            </span>
          </div>
          <div class="flex flex-wrap gap-2">
            <Button
              :label="__('Sync to OpenMeter')"
              :loading="busy === 'sync'"
              @click="run('sync')"
            />
            <Button
              :label="__('Send probe event')"
              :loading="busy === 'send_probe'"
              @click="emit('probe', facility.fid)"
            />
            <Button
              v-if="data.queue.Failed"
              :label="__('Retry failed events')"
              :loading="busy === 'retry_failed'"
              @click="run('retry_failed')"
            />
          </div>
        </div>
        <table v-if="data.events.length" class="mt-2 w-full text-sm">
          <thead class="text-left text-ink-gray-6">
            <tr>
              <th class="py-1 font-normal">{{ __('When') }}</th>
              <th class="py-1 font-normal">{{ __('Event') }}</th>
              <th class="py-1 text-right font-normal">{{ __('Tokens') }}</th>
              <th class="py-1 font-normal">{{ __('Status') }}</th>
            </tr>
          </thead>
          <tbody class="text-ink-gray-8">
            <tr
              v-for="event in data.events.slice(0, 8)"
              :key="event.name"
              class="border-t border-outline-gray-1"
            >
              <td class="py-1">{{ formatDate(event.occurred_at) }}</td>
              <td class="py-1">
                {{ event.is_probe ? __('Probe') : event.event_type }}
              </td>
              <td class="py-1 text-right">{{ event.tokens }}</td>
              <td class="py-1" :title="event.last_error || ''">
                {{ __(event.status) }}
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else class="mt-2 text-sm text-ink-gray-7">
          {{ __('No events yet.') }}
        </p>
      </div>

      <div class="mt-5">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="text-base-semibold text-ink-gray-8">
            {{ __('Grants') }}
          </div>
          <Button
            :label="__('Re-issue expiring grants')"
            :loading="busy === 'reissue_grants'"
            @click="emit('reissue', facility.fid)"
          />
        </div>
        <table v-if="data.grants.length" class="mt-2 w-full text-sm">
          <thead class="text-left text-ink-gray-6">
            <tr>
              <th class="py-1 font-normal">{{ __('Source') }}</th>
              <th class="py-1 text-right font-normal">{{ __('Tokens') }}</th>
              <th class="py-1 font-normal">{{ __('Expires after') }}</th>
              <th class="py-1 font-normal">{{ __('Status') }}</th>
            </tr>
          </thead>
          <tbody class="text-ink-gray-8">
            <tr
              v-for="grant in data.grants"
              :key="grant.name"
              class="border-t border-outline-gray-1"
            >
              <td class="py-1">{{ __(grant.grant_source) }}</td>
              <td class="py-1 text-right">
                {{ Number(grant.amount || 0).toLocaleString() }}
              </td>
              <td class="py-1">
                {{
                  grant.expiration_days
                    ? __('{0} days', [grant.expiration_days])
                    : __('Never')
                }}
              </td>
              <td class="py-1" :title="grant.last_error || ''">
                {{ __(grant.status) }}
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else class="mt-2 text-sm text-ink-gray-7">
          {{ __('No grants yet.') }}
        </p>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Badge, Button, createResource } from 'frappe-ui'
import { balanceStats, keyState, maskedKey, tone } from '@/utils/metering'

const props = defineProps({
  facility: { type: Object, required: true },
  canReveal: { type: Boolean, default: false },
  busy: { type: String, default: null },
})
const emit = defineEmits([
  'action',
  'import',
  'issue',
  'reveal',
  'probe',
  'reissue',
])

const probe = createResource({
  url: 'crm.api.metering_admin.get_facility',
  method: 'GET',
  makeParams: () => ({ fid: props.facility.fid }),
  auto: Boolean(props.facility.fid),
})

const data = computed(() => probe.data)
const site = computed(() => data.value?.site || {})
const stats = computed(() => balanceStats(data.value))
const errors = computed(() => Object.entries(data.value?.errors || {}))
const keyMode = computed(() =>
  keyState(site.value, props.canReveal && data.value?.can_reveal_key),
)

function run(action) {
  emit('action', { action, fid: props.facility.fid })
}

function errorText(error) {
  return (
    error?.messages?.join(' ') ||
    error?.message ||
    __('Could not load metering for this facility.')
  )
}

function formatDate(value) {
  return value ? new Date(String(value).replace(' ', 'T')).toLocaleString() : ''
}

defineExpose({ reload: () => probe.reload() })
</script>
