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
          :tooltip="__(
            'Reload the metering data for this facility from CRM and OpenMeter.',
          )"
          :loading="probe.loading"
          @click="probe.reload()"
        />
      </div>
    </div>

    <FacilityIdLinkPanel
      v-if="!facility.fid"
      class="mt-3"
      :deal-id="dealId"
      :facility="facility"
      @linked="$emit('linked', facility.row_name)"
    />
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
        :tooltip="__(
          'Create or update one metering site (Draft) per facility on this deal. Safe to repeat; existing sites are refreshed, not duplicated.',
        )"
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

      <div class="mt-5" data-testid="facility-plan">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="flex flex-wrap items-center gap-2">
            <span class="text-base-semibold text-ink-gray-8">{{ __('Plan') }}</span>
            <Badge
              data-testid="plan-type"
              :label="__(plan.label)"
              theme="gray"
            />
            <Badge
              v-if="plan.subscription"
              data-testid="subscription-status"
              :label="__(capitalise(plan.subscription.status))"
              :theme="plan.subscriptionTone"
            />
          </div>
          <div class="flex flex-wrap gap-2">
            <Button
              v-if="plan.canCancel"
              data-testid="cancel-subscription"
              :label="__('Cancel subscription')"
              :tooltip="__(
                'End the Fixed subscription now, including renewals already paid. HMIS loses access at once. Refunds are handled by Finance.',
              )"
              :loading="busy === 'cancel_subscription'"
              @click="emit('lifecycle', { action: 'cancel_subscription', fid: facility.fid })"
            />
            <Button
              v-if="plan.canSuspend"
              data-testid="suspend-site"
              :label="__('Suspend site')"
              :tooltip="__(
                'Refuse all HMIS calls for this facility at the gateway, whatever its plan. Tokens and subscription terms are kept.',
              )"
              :loading="busy === 'suspend_site'"
              @click="emit('lifecycle', { action: 'suspend_site', fid: facility.fid })"
            />
            <Button
              v-if="plan.canReactivate"
              data-testid="reactivate-site"
              :label="__('Reactivate site')"
              :tooltip="__('Lift the suspension. HMIS is accepted again within 5 minutes.')"
              :loading="busy === 'reactivate_site'"
              @click="emit('lifecycle', { action: 'reactivate_site', fid: facility.fid })"
            />
            <Button
              :label="__('Refresh plan')"
              :tooltip="__(
                'Write this plan into OpenMeter again, where HMIS reads it (GET /ingest/v1/plan). Safe to repeat.',
              )"
              :loading="busy === 'refresh_plan'"
              @click="run('refresh_plan')"
            />
          </div>
        </div>
        <dl
          v-if="plan.subscription"
          class="mt-2 grid grid-cols-2 gap-x-4 gap-y-2 text-sm lg:grid-cols-4"
        >
          <div>
            <dt class="text-ink-gray-6">{{ __('Package') }}</dt>
            <dd class="text-ink-gray-8">
              {{ plan.subscription.package || '—' }}
              <span v-if="plan.subscription.billing_period">
                · {{ __(plan.subscription.billing_period) }}</span
              >
            </dd>
          </div>
          <div>
            <dt class="text-ink-gray-6">{{ __('Activated') }}</dt>
            <dd data-testid="subscription-activated" class="text-ink-gray-8">
              {{ formatDate(plan.subscription.activated_at) || '—' }}
            </dd>
          </div>
          <div>
            <dt class="text-ink-gray-6">
              {{
                plan.subscription.status === 'cancelled'
                  ? __('Ended')
                  : plan.subscription.status === 'expired'
                    ? __('Expired')
                    : __('Expires')
              }}
            </dt>
            <dd data-testid="subscription-expires" class="text-ink-gray-8">
              {{ formatDate(plan.subscription.expires_at) || '—' }}
            </dd>
          </div>
          <div v-if="plan.subscription.cancelled_at">
            <dt class="text-ink-gray-6">{{ __('Cancelled') }}</dt>
            <dd class="text-ink-gray-8">
              {{ formatDate(plan.subscription.cancelled_at) }}
            </dd>
          </div>
        </dl>
        <p v-else class="mt-2 text-sm text-ink-gray-7">
          {{
            plan.type === 'tokens'
              ? __('Prepaid tokens. They never expire; only an exhausted balance stops clinical work.')
              : __('No paid package yet. A fully paid Fixed invoice starts a subscription; a paid Flex invoice grants tokens.')
          }}
        </p>
        <table
          v-if="plan.terms.length"
          class="mt-2 w-full text-sm"
          data-testid="subscription-terms"
        >
          <thead class="text-left text-ink-gray-6">
            <tr>
              <th class="py-1 font-normal">{{ __('Invoice') }}</th>
              <th class="py-1 font-normal">{{ __('Starts') }}</th>
              <th class="py-1 font-normal">{{ __('Ends') }}</th>
              <th class="py-1 font-normal">{{ __('Status') }}</th>
            </tr>
          </thead>
          <tbody class="text-ink-gray-8">
            <tr
              v-for="term in plan.terms"
              :key="term.name"
              class="border-t border-outline-gray-1"
            >
              <td class="py-1">
                <a
                  v-if="term.invoice"
                  :href="recordHref('Sales Invoice', term.invoice)"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="text-ink-blue-6 hover:underline"
                  >{{ term.invoice }}</a
                >
              </td>
              <td class="py-1">{{ formatDate(term.starts_at) }}</td>
              <td class="py-1">{{ formatDate(term.ends_at) }}</td>
              <td class="py-1" :title="term.cancel_reason || ''">
                {{ __(term.status) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="mt-5" data-testid="token-grants">
        <div class="text-base-semibold text-ink-gray-8">
          {{ __('Token grants') }}
        </div>

        <div
          v-if="bonus.data"
          class="mt-2 flex flex-wrap items-center justify-between gap-3 rounded border border-outline-gray-1 p-3"
          data-testid="welcome-bonus"
        >
          <div class="min-w-0">
            <div class="text-sm font-medium text-ink-gray-8">
              {{ __('Welcome bonus') }}
            </div>
            <p
              class="mt-0.5 text-base text-ink-gray-7"
              data-testid="welcome-bonus-state"
            >
              <template v-if="bonusParts">
                <template v-for="(part, i) in bonusParts" :key="i">
                  <a
                    v-if="part.link"
                    :href="recordHref(part.link.doctype, part.link.name)"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="text-ink-blue-6 hover:underline"
                    >{{ part.link.name }}</a
                  >
                  <span v-else>{{ part.text }}</span>
                </template>
              </template>
              <template v-else>{{ bonusStateText }}</template>
            </p>
          </div>
          <Button
            data-testid="dispense-welcome-bonus"
            :label="
              bonus.data.dispensed
                ? __('Bonus dispensed')
                : __('Dispense {0} bonus tokens', [
                    Number(bonus.data.configured_tokens).toLocaleString(),
                  ])
            "
            :tooltip="__(
              'Grant the one-time welcome bonus for this facility now. It can only ever be dispensed once.',
            )"
            :variant="bonus.data.dispensed ? 'subtle' : 'solid'"
            :disabled="!canDispense"
            :loading="busy === 'welcome_bonus'"
            @click="emit('bonus', facility.fid)"
          />
        </div>

        <div
          v-if="purchaseGrants.length"
          class="mt-2 rounded border border-outline-gray-1 p-3"
          data-testid="token-purchase"
        >
          <div class="text-sm font-medium text-ink-gray-8">
            {{ __('Token purchase') }}
          </div>
          <p
            v-for="grant in purchaseGrants"
            :key="grant.name"
            class="mt-0.5 text-base text-ink-gray-7"
          >
            <template v-if="grant.status === 'Granted'">
              {{ Number(grant.amount || 0).toLocaleString() }}
              {{ __('tokens · paid invoice') }}
              <a
                v-if="
                  recordHref(grant.source_doctype || 'Sales Invoice', grant.source_name)
                "
                :href="
                  recordHref(
                    grant.source_doctype || 'Sales Invoice',
                    grant.source_name,
                  )
                "
                target="_blank"
                rel="noopener noreferrer"
                class="text-ink-blue-6 hover:underline"
                >{{ grant.source_name }}</a
              >
              <template v-else>{{ grant.source_name }}</template
              ><span v-if="grant.effective_at"
                >
                · {{ formatDate(grant.effective_at) }}</span
              >.
            </template>
            <template v-else>
              {{ Number(grant.amount || 0).toLocaleString() }}
              {{ __('tokens') }} — {{ __(grant.status) }}
              <span v-if="grant.last_error">: {{ grant.last_error }}</span
              ><span v-if="grant.source_name">
                ({{ grant.source_name }})</span
              >.
            </template>
          </p>
        </div>

        <div
          v-if="couponGrants.length"
          class="mt-2 rounded border border-outline-gray-1 p-3"
          data-testid="partner-coupon"
        >
          <div class="text-sm font-medium text-ink-gray-8">
            {{ __('Partner coupon') }}
          </div>
          <p
            v-for="grant in couponGrants"
            :key="grant.name"
            class="mt-0.5 text-base text-ink-gray-7"
          >
            <template v-if="grant.status === 'Granted'">
              <template v-if="partner">
                {{ __('Partner') }}
                <a
                  v-if="recordHref('CRM Opt-In Network', partner.name)"
                  :href="recordHref('CRM Opt-In Network', partner.name)"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="text-ink-blue-6 hover:underline"
                  >{{ partner.display_name }} ({{ partner.partner_id }})</a
                >
                <template v-else
                  >{{ partner.display_name }} ({{ partner.partner_id }})</template
                > ·
              </template>
              {{ Number(grant.amount || 0).toLocaleString() }}
              {{ __('tokens via invoice') }}
              <a
                v-if="
                  recordHref(grant.source_doctype || 'Sales Invoice', grant.source_name)
                "
                :href="
                  recordHref(
                    grant.source_doctype || 'Sales Invoice',
                    grant.source_name,
                  )
                "
                target="_blank"
                rel="noopener noreferrer"
                class="text-ink-blue-6 hover:underline"
                >{{ grant.source_name }}</a
              >
              <template v-else>{{ grant.source_name }}</template
              ><span v-if="grant.effective_at"
                >
                · {{ formatDate(grant.effective_at) }}</span
              >.
            </template>
            <template v-else>
              {{ Number(grant.amount || 0).toLocaleString() }}
              {{ __('tokens') }} — {{ __(grant.status) }}
              <span v-if="grant.last_error">: {{ grant.last_error }}</span
              ><span v-if="grant.source_name"> ({{ grant.source_name }})</span>.
            </template>
          </p>
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
              :tooltip="__(
                'Show the stored site key again. Requires the Administrator password; the reveal is recorded on the site.',
              )"
              @click="emit('reveal', facility.fid)"
            />
            <Button
              v-if="keyMode !== 'legacy'"
              :label="__('Issue site key')"
              :tooltip="__(
                'Generate a new ingest key for this facility. Any existing key stops working immediately; the facility must be re-configured with the new key.',
              )"
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
              :tooltip="__(
                'Create or update the customer and entitlement for this facility in OpenMeter, and push the site key metadata. Never grants tokens.',
              )"
              :loading="busy === 'sync'"
              @click="run('sync')"
            />
            <Button
              :label="__('Send probe event')"
              :tooltip="__(
                'Send a one-off metering event that does not count toward usage, then verify OpenMeter stored it. Checks the whole ingest path.',
              )"
              :loading="busy === 'send_probe'"
              @click="emit('probe', facility.fid)"
            />
            <Button
              v-if="data.queue.Failed"
              :label="__('Retry failed events')"
              :tooltip="__('Re-queue usage events that failed delivery to OpenMeter. Safe to repeat.')"
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
            :tooltip="__(
              'Replace grants that would lose tokens at a period reset with one grant for their remaining tokens. Run it while the site is quiet.',
            )"
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
              <td class="py-1">
                <Tooltip placement="top">
                  <span class="text-ink-gray-8">{{ __(grant.grant_source) }}</span>
                  <template #content>
                    {{ grantSourceTip(grant) }}
                    <a
                      v-if="sourceHref(grant)"
                      :href="sourceHref(grant)"
                      target="_blank"
                      rel="noopener noreferrer"
                      class="underline"
                      >{{ __('Open {0}', [__(grant.source_doctype)]) }}</a
                    >
                  </template>
                </Tooltip>
              </td>
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
              <td class="py-1">
                <Tooltip placement="top" :text="grantStatusTip(grant)">
                  <span data-testid="grant-status">{{ __(grant.status) }}</span>
                </Tooltip>
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
import { Badge, Button, Tooltip, createResource } from 'frappe-ui'
import {
  balanceStats,
  keyState,
  maskedKey,
  planSummary,
  tokenLines,
  tone,
  welcomeBonusVia,
} from '@/utils/metering'
import { cockpitRecordHref } from '@/pages/FinanceCockpit/composables/useFinanceNavigation.js'
import FacilityIdLinkPanel from './FacilityIdLinkPanel.vue'

const props = defineProps({
  facility: { type: Object, required: true },
  dealId: { type: String, default: '' },
  canReveal: { type: Boolean, default: false },
  busy: { type: String, default: null },
})
const emit = defineEmits([
  'bonus',
  'action',
  'import',
  'issue',
  'reveal',
  'probe',
  'reissue',
  'linked',
  'lifecycle',
])

const probe = createResource({
  url: 'crm.api.metering_admin.get_facility',
  method: 'GET',
  makeParams: () => ({ fid: props.facility.fid }),
  auto: Boolean(props.facility.fid),
})

const bonus = createResource({
  url: 'crm.api.metering_admin.get_welcome_bonus',
  method: 'GET',
  makeParams: () => ({ fid: props.facility.fid }),
  auto: Boolean(props.facility.fid),
})

// Once Granted (by this button, auto-assign or the first paid invoice) it can never be dispensed again.
const canDispense = computed(
  () =>
    bonus.data?.available &&
    !bonus.data.dispensed &&
    bonus.data.configured_tokens > 0 &&
    !props.busy,
)

// The dispensed bonus as text and link parts, so the order/invoice number is a
// link while the sentence reads like the undispensed state.
const bonusParts = computed(() => {
  const state = bonus.data || {}
  const via = welcomeBonusVia(state)
  if (!via) return null
  const head = __('{0} tokens dispensed on {1}', [
    Number(state.tokens || 0).toLocaleString(),
    formatDate(state.dispensed_at),
  ])
  if (via.kind === 'order')
    return [
      { text: `${head} ${__('automatically when order')} ` },
      { link: { doctype: 'Sales Order', name: via.name } },
      { text: ` ${__('was selected.')}` },
    ]
  if (via.kind === 'invoice')
    return [
      { text: `${head} ${__('with paid invoice')} ` },
      { link: { doctype: 'Sales Invoice', name: via.name } },
      { text: '.' },
    ]
  if (!via.label) return [{ text: `${head}.` }]
  return [{ text: `${head} ${__('by {0}.', [via.label])}` }]
})

const bonusStateText = computed(() => {
  const state = bonus.data || {}
  if (state.dispensed) return ''
  if (!state.available) return __('No metering app is installed on this site.')
  if (!(state.configured_tokens > 0))
    return __(
      'The first-purchase bonus is set to 0 tokens in Settings › Opt-In.',
    )
  if (state.status === 'Failed')
    return __('The last attempt failed: {0} You can try again.', [
      state.error || '',
    ])
  return state.auto_dispense
    ? __(
        'Not dispensed yet. It is auto-assigned when a Flex package is selected, or added to the first paid package.',
      )
    : __(
        'Not dispensed yet. It is added to the first paid package, or you can dispense it now (once).',
      )
})

// The Token purchase / Partner coupon lines, one per grant, from the ledger.
const tokenGrantLines = computed(() => tokenLines(data.value?.grants))
const purchaseGrants = computed(() => tokenGrantLines.value.purchase)
const couponGrants = computed(() => tokenGrantLines.value.coupon)
const partner = computed(() => data.value?.partner || null)

function recordHref(doctype, name) {
  return doctype && name
    ? cockpitRecordHref(doctype, name, { absolute: true })
    : ''
}

const data = computed(() => probe.data)
const site = computed(() => data.value?.site || {})
const stats = computed(() => balanceStats(data.value))
const plan = computed(() => planSummary(data.value?.plan, site.value.status))

function capitalise(text) {
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : ''
}
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

const GRANT_SOURCE_TIPS = {
  'Initial Package': __(
    "The package selected for this facility during onboarding. Free packages are granted here; paid packages stay Skipped until their token invoice is fully paid.",
  ),
  'Token Purchase': __('Tokens bought on a fully paid token invoice.'),
  'Welcome Bonus': __("The facility's one-time welcome bonus."),
  'Partner Coupon': __('Complimentary tokens from the referring partner.'),
  'CRM Coupon': __('Complimentary tokens from a coupon set by the CRM.'),
  Reissue: __('Tokens re-issued in place of a grant that would expire.'),
  Manual: __('Tokens granted manually by an administrator.'),
}

function sourceHref(grant) {
  return recordHref(grant.source_doctype, grant.source_name)
}

function grantSourceTip(grant) {
  const tip = GRANT_SOURCE_TIPS[grant.grant_source] || ''
  if (grant.source_doctype === 'CRM Deal' && grant.source_name)
    return `${tip} ${__('The link opens the deal where the package was selected.')}`
  return tip
}

function grantStatusTip(grant) {
  const reason = grant.last_error ? ` ${grant.last_error}` : ''
  if (grant.status === 'Granted')
    return __('These tokens are active in OpenMeter.')
  if (grant.status === 'Skipped')
    return __('No tokens were granted from this source.') + reason
  if (grant.status === 'Failed')
    return __('The last attempt to grant these tokens failed.') + reason
  return __('The grant has not been confirmed yet.')
}

function formatDate(value) {
  return value ? new Date(String(value).replace(' ', 'T')).toLocaleString() : ''
}

defineExpose({
  reload: () => {
    probe.reload()
    bonus.reload()
  },
})
</script>
