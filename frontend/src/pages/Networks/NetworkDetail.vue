<template>
  <div class="flex flex-col h-full overflow-y-auto px-3 pb-3 sm:px-10 sm:pb-5">
    <!-- ── NETWORK HERO CARD ─────────────────────────────────────────────── -->
    <div
      class="mt-4 rounded-xl border-2 border-outline-gray-2 bg-surface-white dark:bg-surface-gray-1 p-5"
    >
      <!-- Loading skeleton -->
      <div v-if="networkResource.loading" class="space-y-2">
        <div
          v-for="n in 3"
          :key="n"
          class="h-4 animate-pulse rounded bg-surface-gray-2"
        />
      </div>

      <!-- View mode -->
      <template v-else-if="!editingNetwork && !isNewNetwork">
        <div class="mb-1 flex flex-wrap items-start justify-between gap-2">
          <div class="flex flex-wrap items-center gap-2">
            <img
              v-if="networkDoc?.logo_url"
              :src="networkDoc.logo_url"
              :alt="__('Network logo')"
              class="size-9 rounded border border-outline-gray-2 object-contain"
            />
            <h1 class="text-xl font-bold text-ink-gray-9">
              {{ networkDoc?.display_name || networkSlug }}
            </h1>
            <span class="font-mono text-xs text-ink-gray-4">{{
              networkDoc?.slug || networkSlug
            }}</span>
            <span :class="enabledPill(networkDoc?.enabled)">
              {{ networkDoc?.enabled ? __('Enabled') : __('Disabled') }}
            </span>
          </div>
          <div class="flex items-center gap-2">
            <a
              :href="optInUrl"
              target="_blank"
              rel="noopener"
              class="text-xs text-ink-blue-6 hover:text-ink-blue-7 hover:underline"
              >{{ __('Open Opt-In Portal') }}</a
            >
            <router-link
              to="/networks"
              class="text-xs text-ink-gray-5 hover:text-ink-gray-7"
              >← {{ __('Back to Networks') }}</router-link
            >
            <Button variant="subtle" size="sm" @click="startEditNetwork">{{
              __('Edit Network')
            }}</Button>
          </div>
        </div>
        <p class="text-sm text-ink-gray-5">
          {{
            [networkDoc?.contact_email, networkDoc?.footer_legal_name]
              .filter(Boolean)
              .join(' · ') || '—'
          }}
        </p>
        <div
          class="mt-5 grid gap-4 border-t border-outline-gray-2 pt-4 sm:grid-cols-2 lg:grid-cols-3"
        >
          <div>
            <p
              class="text-xs font-medium uppercase tracking-wide text-ink-gray-5"
            >
              {{ __('Portal configuration') }}
            </p>
            <p class="mt-2 text-sm text-ink-gray-7">
              {{
                networkDoc?.custom_header_copy || __('No custom header copy')
              }}
            </p>
            <p class="mt-2 text-sm text-ink-gray-6">
              {{
                __('Price list: {0}', [
                  networkDoc?.price_list_override || __('Opt-In default'),
                ])
              }}
            </p>
            <div class="mt-2 flex items-center gap-2 text-sm text-ink-gray-6">
              <span
                class="size-3 rounded-full border border-outline-gray-3"
                :style="{
                  backgroundColor: networkDoc?.primary_colour || '#e53e3e',
                }"
              />{{ networkDoc?.primary_colour || '#e53e3e' }}
            </div>
          </div>
          <div>
            <p
              class="text-xs font-medium uppercase tracking-wide text-ink-gray-5"
            >
              {{ __('Partners') }}
            </p>
            <div
              v-if="networkDoc?.partner_logos?.length"
              class="mt-2 flex flex-wrap gap-2"
            >
              <a
                v-for="partner in networkDoc.partner_logos"
                :key="partner.name || partner.partner_name"
                :href="partner.website || undefined"
                target="_blank"
                rel="noopener"
                class="flex items-center gap-2 rounded border border-outline-gray-2 px-2 py-1 text-sm text-ink-gray-7"
              >
                <img
                  v-if="partner.logo"
                  :src="partner.logo"
                  :alt="partner.partner_name"
                  class="size-5 object-contain"
                />
                {{ partner.partner_name }}
              </a>
            </div>
            <p v-else class="mt-2 text-sm text-ink-gray-5">
              {{ __('No partners configured') }}
            </p>
          </div>
          <div class="space-y-3">
            <div>
              <p
                class="text-xs font-medium uppercase tracking-wide text-ink-gray-5"
              >
                {{ __('Coordinators') }}
              </p>
              <p class="mt-1 text-sm text-ink-gray-7">
                {{
                  networkDoc?.coordinators?.map((row) => row.user).join(', ') ||
                  __('None')
                }}
              </p>
            </div>
            <div>
              <p
                class="text-xs font-medium uppercase tracking-wide text-ink-gray-5"
              >
                {{ __('Network signatories') }}
              </p>
              <p class="mt-1 text-sm text-ink-gray-7">
                {{
                  networkDoc?.network_signers
                    ?.map((row) => `${row.full_name} (${row.email})`)
                    .join(', ') || __('None')
                }}
              </p>
            </div>
          </div>
        </div>
      </template>

      <!-- Edit mode -->
      <template v-else>
        <div class="mb-4 flex items-center justify-between">
          <h2 class="text-lg font-semibold text-ink-gray-9">
            {{ isNewNetwork ? __('New Opt-In Network') : __('Edit Network') }}
          </h2>
        </div>
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <FormControl
            v-if="isNewNetwork"
            v-model="networkForm.slug"
            :label="__('Slug')"
            :placeholder="__('e.g. careverse-ke')"
          />
          <FormControl
            v-else
            :model-value="networkForm.slug"
            :label="__('Slug')"
            disabled
          />
          <FormControl
            v-model="networkForm.display_name"
            :label="__('Display Name')"
            :placeholder="__('Name shown to facilities')"
          />
          <FormControl
            v-model="networkForm.contact_email"
            :label="__('Contact Email')"
            type="email"
          />
          <FormControl
            v-model="networkForm.footer_legal_name"
            :label="__('Footer Legal Name')"
          />
          <div class="flex flex-col gap-1">
            <label class="text-xs font-medium text-ink-gray-6">{{
              __('Network Logo')
            }}</label>
            <FileUploader
              :validateFile="validateIsImageFile"
              @success="setNetworkLogo"
            >
              <template
                #default="{ openFileSelector, uploading, progress, error }"
              >
                <div class="flex items-center gap-3">
                  <img
                    v-if="networkForm.logo_url"
                    :src="networkForm.logo_url"
                    :alt="__('Network logo preview')"
                    class="h-10 w-10 rounded border border-outline-gray-2 object-contain bg-surface-white"
                  />
                  <button
                    type="button"
                    class="rounded border border-outline-gray-2 bg-surface-white px-3 py-1.5 text-sm text-ink-gray-7 hover:bg-surface-gray-2 disabled:opacity-50 dark:bg-surface-gray-3 dark:text-ink-gray-4"
                    :disabled="uploading"
                    @click="openFileSelector"
                  >
                    {{
                      uploading
                        ? __('Uploading {0}%', [progress])
                        : networkForm.logo_url
                          ? __('Change Logo')
                          : __('Upload Logo')
                    }}
                  </button>
                  <button
                    v-if="networkForm.logo_url && !uploading"
                    type="button"
                    class="text-xs text-red-600 hover:underline"
                    @click="networkForm.logo_url = ''"
                  >
                    {{ __('Remove') }}
                  </button>
                </div>
                <p v-if="error" class="mt-1 text-xs text-red-600">
                  {{ __(error) }}
                </p>
              </template>
            </FileUploader>
          </div>
          <div class="flex flex-col gap-1">
            <label class="text-xs font-medium text-ink-gray-6">{{
              __('Primary Colour')
            }}</label>
            <div class="flex items-center gap-2">
              <input
                v-model="networkForm.primary_colour"
                type="color"
                class="h-8 w-10 cursor-pointer rounded border border-outline-gray-2 bg-surface-white p-0.5"
              />
              <input
                v-model="networkForm.primary_colour"
                type="text"
                class="flex-1 rounded border border-outline-gray-2 bg-surface-white px-3 py-1.5 text-sm text-ink-gray-9 focus:outline-none focus:ring-2 focus:ring-red-600 dark:bg-surface-gray-3 dark:text-ink-gray-3"
                placeholder="#e53e3e"
              />
            </div>
          </div>
          <div class="flex flex-col gap-1">
            <label class="text-xs font-medium text-ink-gray-6">{{
              __('Price List Override')
            }}</label>
            <select
              v-model="networkForm.price_list_override"
              class="rounded border border-outline-gray-2 bg-surface-white px-3 py-1.5 text-sm text-ink-gray-9 focus:outline-none focus:ring-2 focus:ring-red-600 dark:bg-surface-gray-3 dark:text-ink-gray-3"
            >
              <option value="">{{ __('Use opt-in default') }}</option>
              <option
                v-for="priceList in negotiatedPriceLists"
                :key="priceList.value"
                :value="priceList.value"
              >
                {{ priceList.label }}
              </option>
            </select>
          </div>
          <div class="flex flex-col gap-1">
            <label class="text-xs font-medium text-ink-gray-6">{{
              __('Status')
            }}</label>
            <Switch
              v-model="networkForm.enabled"
              :label="__('Enabled')"
              size="sm"
            />
          </div>
          <FormControl
            v-model="networkForm.custom_header_copy"
            :label="__('Custom Header Copy')"
            type="textarea"
            class="sm:col-span-2"
          />
        </div>
        <div
          class="mt-6 grid gap-5 border-t border-outline-gray-2 pt-5 lg:grid-cols-3"
        >
          <div>
            <div class="mb-3 flex items-center justify-between">
              <h3 class="text-sm font-semibold text-ink-gray-8">
                {{ __('Partner Logos') }}
              </h3>
              <Button size="sm" variant="subtle" @click="addPartner">{{
                __('Add Partner')
              }}</Button>
            </div>
            <div
              v-if="!networkForm.partner_logos.length"
              class="text-sm text-ink-gray-5"
            >
              {{ __('No partners configured') }}
            </div>
            <div
              v-for="(partner, index) in networkForm.partner_logos"
              :key="partner.key"
              class="mb-3 space-y-2 rounded-lg border border-outline-gray-2 p-3"
            >
              <div class="flex gap-2">
                <FormControl
                  v-model="partner.partner_name"
                  :label="__('Partner Name')"
                  class="flex-1"
                /><Button
                  variant="ghost"
                  theme="red"
                  icon="lucide-trash-2"
                  @click="networkForm.partner_logos.splice(index, 1)"
                />
              </div>
              <FormControl
                v-model="partner.website"
                :label="__('Website')"
                type="url"
              />
              <FileUploader
                :validateFile="validateIsImageFile"
                @success="(file) => setPartnerLogo(index, file)"
              >
                <template #default="{ openFileSelector, uploading }">
                  <div class="flex items-center gap-2">
                    <img
                      v-if="partner.logo"
                      :src="partner.logo"
                      :alt="partner.partner_name"
                      class="size-7 rounded border border-outline-gray-2 object-contain"
                    />
                    <Button
                      size="sm"
                      variant="subtle"
                      :loading="uploading"
                      @click="openFileSelector"
                      >{{
                        partner.logo ? __('Change Logo') : __('Upload Logo')
                      }}</Button
                    >
                    <Button
                      v-if="partner.logo && !uploading"
                      size="sm"
                      variant="ghost"
                      theme="red"
                      @click="partner.logo = ''"
                      >{{ __('Remove') }}</Button
                    >
                  </div>
                </template>
              </FileUploader>
            </div>
          </div>
          <div>
            <div class="mb-3 flex items-center justify-between">
              <h3 class="text-sm font-semibold text-ink-gray-8">
                {{ __('Network Coordinators') }}
              </h3>
              <Button
                size="sm"
                variant="subtle"
                @click="
                  networkForm.coordinators.push({ key: newRowKey(), user: '' })
                "
                >{{ __('Add Coordinator') }}</Button
              >
            </div>
            <div
              v-if="!networkForm.coordinators.length"
              class="text-sm text-ink-gray-5"
            >
              {{ __('No coordinators configured') }}
            </div>
            <div
              v-for="(coordinator, index) in networkForm.coordinators"
              :key="coordinator.key"
              class="mb-2 flex items-end gap-2"
            >
              <FormControl
                v-model="coordinator.user"
                :label="__('CRM User')"
                class="flex-1"
              /><Button
                variant="ghost"
                theme="red"
                icon="lucide-trash-2"
                @click="networkForm.coordinators.splice(index, 1)"
              />
            </div>
          </div>
          <div>
            <div class="mb-3 flex items-center justify-between">
              <h3 class="text-sm font-semibold text-ink-gray-8">
                {{ __('Network Signatories') }}
              </h3>
              <Button size="sm" variant="subtle" @click="addSigner">{{
                __('Add Signatory')
              }}</Button>
            </div>
            <div
              v-if="!networkForm.network_signers.length"
              class="text-sm text-ink-gray-5"
            >
              {{ __('No signatories configured') }}
            </div>
            <div
              v-for="(signer, index) in networkForm.network_signers"
              :key="signer.key"
              class="mb-3 space-y-2 rounded-lg border border-outline-gray-2 p-3"
            >
              <div class="flex items-end gap-2">
                <FormControl
                  v-model="signer.full_name"
                  :label="__('Full Name')"
                  class="flex-1"
                /><Button
                  variant="ghost"
                  theme="red"
                  icon="lucide-trash-2"
                  @click="networkForm.network_signers.splice(index, 1)"
                />
              </div>
              <FormControl
                v-model="signer.email"
                :label="__('Email')"
                type="email"
              />
              <FormControl
                v-model="signer.phone"
                :label="__('Phone for SMS')"
                type="tel"
              />
            </div>
          </div>
        </div>

        <p v-if="networkFormError" class="mt-2 text-xs text-red-600">
          {{ networkFormError }}
        </p>
        <div class="mt-4 flex gap-2">
          <Button
            variant="solid"
            :loading="saveNetworkResource.loading"
            @click="saveNetwork"
            >{{ __('Save') }}</Button
          >
          <Button variant="subtle" @click="cancelEditNetwork">{{
            __('Cancel')
          }}</Button>
        </div>
      </template>
    </div>

    <template v-if="!isNewNetwork">
      <!-- ── PREQUALIFIED CONTACTS ─────────────────────────────────────────── -->
      <div class="mt-6 flex items-center justify-between">
        <div class="flex items-center gap-2">
          <h2 class="text-base font-semibold text-ink-gray-9">
            {{ __('Prequalified Contacts') }}
          </h2>
          <span
            class="rounded-full bg-surface-gray-2 px-2 py-0.5 text-xs font-semibold text-ink-gray-6 dark:bg-surface-gray-4 dark:text-ink-gray-4"
          >
            {{ contactTotal }}
          </span>
        </div>
        <div class="flex gap-2">
          <Button variant="subtle" size="sm" @click="toggleCsvSection">{{
            __('Import CSV')
          }}</Button>
          <Button variant="solid" size="sm" @click="openAddForm">{{
            __('+ Add Contact')
          }}</Button>
        </div>
      </div>

      <div
        class="mt-3 flex flex-wrap items-end gap-2 border-y border-outline-gray-2 py-3"
      >
        <label class="flex flex-col gap-1 text-xs font-medium text-ink-gray-6">
          {{ __('Facility') }}
          <input
            v-model="facilitySearch"
            class="h-8 w-48 rounded border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-8 dark:bg-surface-gray-3 dark:text-ink-gray-3"
            :placeholder="__('Name, MFL or organization')"
            @keyup.enter="applyContactFilters"
          />
        </label>
        <label class="flex flex-col gap-1 text-xs font-medium text-ink-gray-6">
          {{ __('Facility level') }}
          <select
            v-model="facilityLevelFilter"
            class="h-8 min-w-28 rounded border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-8 dark:bg-surface-gray-3 dark:text-ink-gray-3"
            @change="applyContactFilters"
          >
            <option value="">{{ __('All levels') }}</option>
            <option v-for="level in facilityLevels" :key="level" :value="level">
              {{ level }}
            </option>
          </select>
        </label>
        <label class="flex flex-col gap-1 text-xs font-medium text-ink-gray-6">
          {{ __('Organization') }}
          <input
            v-model="organizationFilter"
            class="h-8 w-40 rounded border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-8 dark:bg-surface-gray-3 dark:text-ink-gray-3"
            :placeholder="__('Organization name')"
            @keyup.enter="applyContactFilters"
          />
        </label>
        <label class="flex flex-col gap-1 text-xs font-medium text-ink-gray-6">
          {{ __('Contact') }}
          <input
            v-model="contactSearch"
            class="h-8 w-44 rounded border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-8 dark:bg-surface-gray-3 dark:text-ink-gray-3"
            :placeholder="__('Name, email or phone')"
            @keyup.enter="applyContactFilters"
          />
        </label>
        <label class="flex flex-col gap-1 text-xs font-medium text-ink-gray-6">
          {{ __('Opt-in') }}
          <select
            v-model="contactOptInFilter"
            class="h-8 min-w-28 rounded border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-8 dark:bg-surface-gray-3 dark:text-ink-gray-3"
            @change="applyContactFilters"
          >
            <option value="">{{ __('All opt-in states') }}</option>
            <option value="1">{{ __('Opted in') }}</option>
            <option value="0">{{ __('Not opted in') }}</option>
          </select>
        </label>
        <label class="flex flex-col gap-1 text-xs font-medium text-ink-gray-6">
          {{ __('Invitation') }}
          <select
            v-model="inviteStatusFilter"
            class="h-8 min-w-28 rounded border border-outline-gray-2 bg-surface-white px-2 text-sm text-ink-gray-8 dark:bg-surface-gray-3 dark:text-ink-gray-3"
            @change="applyContactFilters"
          >
            <option value="">{{ __('All delivery states') }}</option>
            <option
              v-for="status in inviteStatuses"
              :key="status"
              :value="status"
            >
              {{ __(status) }}
            </option>
          </select>
        </label>
        <Button size="sm" variant="subtle" @click="applyContactFilters">{{
          __('Apply')
        }}</Button>
        <Button size="sm" variant="ghost" @click="clearContactFilters">{{
          __('Clear')
        }}</Button>
      </div>

      <!-- Loading skeleton -->
      <div v-if="facilitiesResource.loading" class="mt-4 space-y-2">
        <div
          v-for="n in 3"
          :key="n"
          class="h-10 animate-pulse rounded-lg bg-surface-gray-2"
        />
      </div>

      <!-- Empty state -->
      <div
        v-else-if="!contactRows.length && !showForm"
        class="mt-16 flex flex-col items-center gap-3 text-center"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          class="h-12 w-12 text-ink-gray-3"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path
            d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"
          />
          <polyline points="14 2 14 8 20 8" />
          <line x1="16" y1="13" x2="8" y2="13" />
          <line x1="16" y1="17" x2="8" y2="17" />
        </svg>
        <p class="text-sm font-medium text-ink-gray-5">
          {{
            hasContactFilters
              ? __('No contacts match these filters')
              : __('No prequalified contacts')
          }}
        </p>
        <p class="text-xs text-ink-gray-4">
          {{
            hasContactFilters
              ? __('Clear or adjust the filters to see more contacts.')
              : __('Add facilities to this network to allow them to opt in.')
          }}
        </p>
        <Button class="mt-2" variant="solid" @click="openAddForm">{{
          __('+ Add Contact')
        }}</Button>
      </div>

      <!-- Contacts table -->
      <div
        v-else-if="contactRows.length"
        class="mt-3 overflow-x-auto rounded-lg border border-outline-gray-2"
      >
        <table class="w-full text-sm">
          <thead
            class="bg-surface-gray-1 text-xs uppercase tracking-wide text-ink-gray-5"
          >
            <tr>
              <th class="px-4 py-2.5 text-left font-medium">
                {{ __('Facility') }}
              </th>
              <th class="px-4 py-2.5 text-left font-medium">
                {{ __('KEPH Level') }}
              </th>
              <th class="px-4 py-2.5 text-left font-medium">
                {{ __('Opt-in') }}
              </th>
              <th class="px-4 py-2.5 text-left font-medium">
                {{ __('Contact') }}
              </th>
              <th class="px-4 py-2.5 text-left font-medium">
                {{ __('Invitation') }}
              </th>
              <th class="px-4 py-2.5 text-right font-medium">
                {{ __('Actions') }}
              </th>
            </tr>
          </thead>
          <tbody class="divide-y divide-outline-elevation-2">
            <tr
              v-for="row in contactRows"
              :key="row.name"
              class="transition-colors hover:bg-surface-gray-1"
            >
              <td class="px-4 py-3">
                <p class="font-medium text-ink-gray-9">
                  {{ row.facility_name }}
                </p>
                <p class="mt-0.5 text-xs text-ink-gray-5">
                  {{ row.organization || row.facility_name }} ·
                  {{ row.mfl_code }}
                </p>
                <p class="mt-0.5 text-xs text-ink-gray-5">
                  {{ facilityPriceListLabel(row) }}
                </p>
              </td>
              <td class="px-4 py-3">
                <span
                  class="rounded-full bg-surface-gray-2 px-2 py-0.5 text-xs font-medium text-ink-gray-7 dark:bg-surface-gray-4 dark:text-ink-gray-4"
                  >{{ row.keph_level || '—' }}</span
                >
              </td>
              <td class="px-4 py-3">
                <span :class="optInPill(isOptedIn(row))">
                  {{ isOptedIn(row) ? __('Opted in') : __('Not opted in') }}
                </span>
              </td>
              <td class="px-4 py-3">
                <p class="text-xs font-medium text-ink-gray-7">
                  {{ networkMembership(row)?.contact_name || '—' }}
                </p>
                <p class="mt-0.5 text-xs text-ink-gray-5">
                  {{ networkMembership(row)?.contact_email || '—' }}
                  <template v-if="networkMembership(row)?.contact_phone">
                    · {{ networkMembership(row).contact_phone }}
                  </template>
                </p>
              </td>
              <td class="px-4 py-3">
                <span
                  :class="
                    inviteStatusPill(networkMembership(row)?.invite_status)
                  "
                >
                  {{ networkMembership(row)?.invite_status || __('Not sent') }}
                </span>
                <p
                  v-if="networkMembership(row)?.invite_sent_at"
                  class="mt-1 text-xs text-ink-gray-5"
                >
                  {{ formatDate(networkMembership(row).invite_sent_at) }}
                </p>
              </td>
              <td class="px-4 py-3 text-right" @click.stop>
                <div class="flex items-center justify-end gap-2">
                  <Button
                    size="sm"
                    variant="subtle"
                    :loading="sampleQuoteFacility === row.name"
                    @click="viewSampleQuote(row)"
                    >{{ __('Sample quote') }}</Button
                  >
                  <Button
                    size="sm"
                    variant="subtle"
                    :loading="
                      resendingMembership === networkMembership(row)?.name
                    "
                    :disabled="!canResendInvite(networkMembership(row))"
                    @click="resendInvite(row)"
                    >{{ __('Resend Invite') }}</Button
                  >
                  <Button
                    size="sm"
                    variant="subtle"
                    @click="editContact(row)"
                    >{{ __('Edit') }}</Button
                  >
                  <button
                    class="rounded px-2 py-1 text-xs font-medium text-red-600 hover:bg-surface-red-1 disabled:opacity-50"
                    :disabled="removingName === row.name"
                    @click="removeContact(row)"
                  >
                    <span
                      v-if="removingName === row.name"
                      class="inline-flex items-center gap-1"
                    >
                      <span
                        class="h-3 w-3 animate-spin rounded-full border border-red-600 border-t-transparent"
                      />
                    </span>
                    <span v-else>{{ __('Remove') }}</span>
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>

        <!-- Pagination -->
        <div
          v-if="contactTotal > pageSize"
          class="flex items-center justify-between border-t border-outline-gray-2 px-4 py-3"
        >
          <span class="text-xs text-ink-gray-5">
            {{
              __('Showing {0}–{1} of {2}', [
                page * pageSize + 1,
                Math.min((page + 1) * pageSize, contactTotal),
                contactTotal,
              ])
            }}
          </span>
          <div class="flex gap-2">
            <Button
              size="sm"
              variant="subtle"
              :disabled="page === 0"
              @click="prevPage"
              >{{ __('Prev') }}</Button
            >
            <Button
              size="sm"
              variant="subtle"
              :disabled="(page + 1) * pageSize >= contactTotal"
              @click="nextPage"
              >{{ __('Next') }}</Button
            >
          </div>
        </div>
      </div>

      <Dialog
        v-model="showSampleQuote"
        :options="{ title: __('Sample quotation'), size: 'lg' }"
      >
        <template #body-content>
          <div
            v-if="sampleQuoteLoading"
            class="py-10 text-center text-sm text-ink-gray-5"
          >
            {{ __('Loading sample quotation…') }}
          </div>
          <div v-else-if="sampleQuote" class="space-y-4">
            <div>
              <p class="text-lg font-semibold text-ink-gray-9">
                {{ sampleQuote.facility }}
              </p>
              <p class="text-sm text-ink-gray-5">
                {{ sampleQuote.organization }} · {{ sampleQuote.keph_level }} ·
                {{ sampleQuote.network }}
              </p>
            </div>
            <div
              class="rounded-lg bg-surface-gray-1 p-3 text-sm dark:bg-surface-gray-2"
            >
              <div class="flex justify-between gap-4">
                <span class="text-ink-gray-5">{{ __('Price list') }}</span>
                <span class="font-medium text-ink-gray-9">{{
                  sampleQuote.price_list
                }}</span>
              </div>
              <div class="mt-1 flex justify-between gap-4">
                <span class="text-ink-gray-5">{{ __('Item') }}</span>
                <span class="text-right text-ink-gray-8">{{
                  sampleQuote.item_name
                }}</span>
              </div>
            </div>
            <div class="grid gap-3 sm:grid-cols-2">
              <div class="rounded-lg border border-outline-gray-2 p-3">
                <p class="text-xs uppercase tracking-wide text-ink-gray-5">
                  {{ __('Monthly total') }}
                </p>
                <p class="mt-1 text-base font-semibold text-ink-gray-9">
                  {{ formatKes(sampleQuote.monthly_gross) }}
                </p>
                <p class="text-xs text-ink-gray-5">
                  {{ formatKes(sampleQuote.monthly_net) }}
                  {{ __('excl. VAT') }} ·
                  {{ sampleQuote.vat_label }}
                </p>
              </div>
              <div class="rounded-lg border border-outline-gray-2 p-3">
                <p class="text-xs uppercase tracking-wide text-ink-gray-5">
                  {{ __('Annual total') }}
                </p>
                <p class="mt-1 text-base font-semibold text-ink-gray-9">
                  {{ formatKes(sampleQuote.annual_gross) }}
                </p>
                <p class="text-xs text-ink-gray-5">
                  {{ formatKes(sampleQuote.annual_net) }}
                  {{ __('excl. VAT') }} ·
                  {{ sampleQuote.vat_label }}
                </p>
              </div>
            </div>
          </div>
        </template>
      </Dialog>

      <!-- Add / Edit inline form -->
      <div
        v-if="showForm"
        class="mt-3 rounded-xl border border-outline-gray-2 bg-surface-gray-1 dark:bg-surface-gray-2 p-5"
      >
        <h3 class="mb-4 text-sm font-semibold text-ink-gray-9">
          {{ editingFacility ? __('Edit Contact') : __('Add Contact') }}
        </h3>

        <!-- Row 1: MFL lookup -->
        <div class="mb-4 flex flex-wrap items-end gap-3">
          <div class="flex flex-col gap-1">
            <label class="text-xs font-medium text-ink-gray-6"
              >{{ __('MFL Code') }} <span class="text-red-600">*</span></label
            >
            <input
              v-model="form.mfl_code"
              type="text"
              :disabled="!!editingFacility"
              class="w-32 rounded border border-outline-gray-2 bg-surface-white px-3 py-1.5 text-sm text-ink-gray-9 focus:outline-none focus:ring-2 focus:ring-red-600 disabled:opacity-50 dark:bg-surface-gray-3 dark:text-ink-gray-3"
              placeholder="12345"
            />
          </div>
          <button
            class="rounded border border-outline-gray-2 bg-surface-white px-3 py-1.5 text-sm text-ink-gray-7 hover:bg-surface-gray-2 disabled:opacity-50 dark:bg-surface-gray-3 dark:text-ink-gray-4"
            :disabled="hfrLoading"
            @click="lookupHFR"
          >
            <span v-if="hfrLoading" class="inline-flex items-center gap-1.5">
              <span
                class="h-3 w-3 animate-spin rounded-full border border-ink-gray-6 border-t-transparent"
              />
              {{ __('Looking up…') }}
            </span>
            <span v-else>{{ __('Lookup HFR') }}</span>
          </button>
          <div class="flex flex-col gap-1">
            <label class="text-xs font-medium text-ink-gray-6"
              >{{ __('Facility Name') }}
              <span class="text-red-600">*</span></label
            >
            <input
              v-model="form.facility_name"
              type="text"
              class="w-56 rounded border border-outline-gray-2 bg-surface-white px-3 py-1.5 text-sm text-ink-gray-9 focus:outline-none focus:ring-2 focus:ring-red-600 dark:bg-surface-gray-3 dark:text-ink-gray-3"
              @input="defaultOrganizationFromFacility"
            />
          </div>
          <div class="flex flex-col gap-1">
            <label class="text-xs font-medium text-ink-gray-6"
              >{{ __('KEPH Level') }} <span class="text-red-600">*</span></label
            >
            <input
              v-model="form.keph_level"
              type="text"
              class="w-28 rounded border border-outline-gray-2 bg-surface-white px-3 py-1.5 text-sm text-ink-gray-9 focus:outline-none focus:ring-2 focus:ring-red-600 dark:bg-surface-gray-3 dark:text-ink-gray-3"
            />
          </div>
        </div>

        <!-- Row 2: Contact fields -->
        <div class="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <div class="flex flex-col gap-1">
            <label class="text-xs font-medium text-ink-gray-6">{{
              __('Organization')
            }}</label>
            <input
              v-model="form.organization"
              type="text"
              :placeholder="__('Defaults to the facility name')"
              class="rounded border border-outline-gray-2 bg-surface-white px-3 py-1.5 text-sm text-ink-gray-9 focus:outline-none focus:ring-2 focus:ring-red-600 dark:bg-surface-gray-3 dark:text-ink-gray-3"
              @input="organizationEdited = true"
            />
          </div>
          <div class="flex flex-col gap-1">
            <label class="text-xs font-medium text-ink-gray-6">
              {{ __('Facility price list') }}
            </label>
            <select
              v-model="form.price_list_override"
              class="rounded border border-outline-gray-2 bg-surface-white px-3 py-1.5 text-sm text-ink-gray-9 focus:outline-none focus:ring-2 focus:ring-red-600 dark:bg-surface-gray-3 dark:text-ink-gray-3"
            >
              <option value="">{{ __('Use network price list') }}</option>
              <option
                v-for="priceList in negotiatedPriceLists"
                :key="priceList.value"
                :value="priceList.value"
              >
                {{ priceList.label }}
              </option>
            </select>
            <span class="text-[11px] text-ink-gray-5">
              {{
                __(
                  'Use this only when the facility has negotiated a different rate.',
                )
              }}
            </span>
          </div>
          <div class="flex flex-col gap-1">
            <label class="text-xs font-medium text-ink-gray-6"
              >{{ __('Contact Name') }}
              <span class="text-red-600">*</span></label
            >
            <input
              v-model="form.contact_name"
              type="text"
              class="rounded border border-outline-gray-2 bg-surface-white px-3 py-1.5 text-sm text-ink-gray-9 focus:outline-none focus:ring-2 focus:ring-red-600 dark:bg-surface-gray-3 dark:text-ink-gray-3"
            />
          </div>
          <div class="flex flex-col gap-1">
            <label class="text-xs font-medium text-ink-gray-6"
              >{{ __('Contact Email') }}
              <span class="text-red-600">*</span></label
            >
            <input
              v-model="form.contact_email"
              type="email"
              class="rounded border border-outline-gray-2 bg-surface-white px-3 py-1.5 text-sm text-ink-gray-9 focus:outline-none focus:ring-2 focus:ring-red-600 dark:bg-surface-gray-3 dark:text-ink-gray-3"
            />
          </div>
          <div class="flex flex-col gap-1">
            <label class="text-xs font-medium text-ink-gray-6"
              >{{ __('Contact Phone') }}
              <span class="text-red-600">*</span></label
            >
            <input
              v-model="form.contact_phone"
              type="tel"
              class="rounded border border-outline-gray-2 bg-surface-white px-3 py-1.5 text-sm text-ink-gray-9 focus:outline-none focus:ring-2 focus:ring-red-600 dark:bg-surface-gray-3 dark:text-ink-gray-3"
            />
          </div>
          <div class="flex flex-col gap-1">
            <label class="text-xs font-medium text-ink-gray-6">{{
              __('Status')
            }}</label>
            <select
              v-model="form.status"
              class="rounded border border-outline-gray-2 bg-surface-white px-3 py-1.5 text-sm text-ink-gray-7 focus:outline-none focus:ring-2 focus:ring-red-600 dark:bg-surface-gray-3 dark:text-ink-gray-4"
            >
              <option value="Active">{{ __('Active') }}</option>
              <option value="Opted In">{{ __('Opted In') }}</option>
              <option value="Declined">{{ __('Declined') }}</option>
            </select>
          </div>
        </div>

        <p v-if="formError" class="mb-2 text-xs text-red-600">
          {{ formError }}
        </p>
        <div class="flex gap-2">
          <Button variant="solid" :loading="saveLoading" @click="saveContact">{{
            __('Save')
          }}</Button>
          <Button variant="subtle" @click="cancelForm">{{
            __('Cancel')
          }}</Button>
        </div>
      </div>

      <!-- CSV Import section -->
      <div
        v-if="showCsvSection"
        class="mt-3 rounded-xl border border-outline-gray-2 bg-surface-gray-1 dark:bg-surface-gray-2 p-5"
      >
        <h3 class="mb-3 text-sm font-semibold text-ink-gray-9">
          {{ __('Import Contacts via CSV') }}
        </h3>
        <p class="mb-3 text-xs text-ink-gray-5">
          {{ __('Upload a CSV file to bulk-add facilities to this network.') }}
          <button
            class="text-ink-blue-6 underline hover:text-ink-blue-7"
            @click="downloadTemplate"
          >
            {{ __('Download template') }}
          </button>
        </p>
        <input
          ref="csvFileInput"
          type="file"
          accept=".csv"
          class="mb-3 text-sm text-ink-gray-7"
          @change="onFileChange"
        />

        <!-- Preview table -->
        <div
          v-if="csvPreviewRows.length"
          class="mb-3 overflow-x-auto rounded-lg border border-outline-gray-2"
        >
          <table class="w-full text-xs">
            <thead
              class="bg-surface-gray-1 text-xs uppercase tracking-wide text-ink-gray-5"
            >
              <tr>
                <th class="px-3 py-2 text-left font-medium">{{ __('Row') }}</th>
                <th class="px-3 py-2 text-left font-medium">
                  {{ __('MFL Code') }}
                </th>
                <th class="px-3 py-2 text-left font-medium">
                  {{ __('Facility Name') }}
                </th>
                <th class="px-3 py-2 text-left font-medium">
                  {{ __('Organization') }}
                </th>
                <th class="px-3 py-2 text-left font-medium">
                  {{ __('Price List') }}
                </th>
                <th class="px-3 py-2 text-left font-medium">
                  {{ __('Contact Email') }}
                </th>
                <th class="px-3 py-2 text-left font-medium">
                  {{ __('Status') }}
                </th>
              </tr>
            </thead>
            <tbody class="divide-y divide-outline-elevation-2">
              <tr
                v-for="r in csvPreviewRows"
                :key="r.row"
                :class="r.error ? 'bg-red-50 dark:bg-red-900/10' : ''"
              >
                <td class="px-3 py-2 text-ink-gray-6">{{ r.row }}</td>
                <td class="px-3 py-2 font-mono text-ink-gray-9">
                  {{ r.mfl_code }}
                </td>
                <td class="px-3 py-2 text-ink-gray-7">{{ r.facility_name }}</td>
                <td class="px-3 py-2 text-ink-gray-7">
                  {{ r.organization || r.facility_name }}
                </td>
                <td class="px-3 py-2 text-ink-gray-7">
                  {{ r.price_list_override || __('Use network price list') }}
                </td>
                <td class="px-3 py-2 text-ink-gray-6">{{ r.contact_email }}</td>
                <td v-if="r.error" class="px-3 py-2 text-red-600">
                  {{ r.error }}
                </td>
                <td v-else class="px-3 py-2 text-green-600">{{ __('OK') }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-if="csvFile" class="flex flex-wrap items-center gap-2">
          <Button
            variant="solid"
            :loading="csvImporting || csvPreviewLoading"
            :disabled="!validCsvCount"
            @click="importCsv"
          >
            {{
              csvPreviewLoading
                ? __('Preparing preview…')
                : __('Import {0} valid rows', [validCsvCount])
            }}
          </Button>
          <Button variant="subtle" @click="clearCsv">{{ __('Clear') }}</Button>
        </div>
        <p
          v-if="csvFile && !csvPreviewLoading"
          class="mt-2 text-xs text-ink-gray-5"
        >
          {{
            __('{0} valid rows, {1} rows needing correction.', [
              validCsvCount,
              csvPreviewRows.length - validCsvCount,
            ])
          }}
        </p>
        <p v-if="csvResult" class="mt-2 text-sm text-ink-gray-7">
          {{ csvResult }}
        </p>
      </div>

      <div class="h-8" />
    </template>
  </div>
</template>

<script setup>
import { ref, computed, reactive } from 'vue'
import { useRouter } from 'vue-router'
import {
  createResource,
  Button,
  Dialog,
  FileUploader,
  FormControl,
  Switch,
  toast,
} from 'frappe-ui'
import { validateIsImageFile } from '@/utils'

const props = defineProps({
  networkSlug: { type: String, required: true },
})
const router = useRouter()
const isNewNetwork = computed(() => props.networkSlug === 'new')

// ── Network doc ────────────────────────────────────────────────────────────

const networkResource = createResource({
  url: 'frappe.client.get',
  makeParams: () => ({
    doctype: 'CRM Opt-In Network',
    name: props.networkSlug,
  }),
  auto: !isNewNetwork.value,
})

const networkDoc = computed(() => networkResource.data ?? null)
const optInUrl = computed(
  () => `/opt-in?network=${encodeURIComponent(props.networkSlug)}`,
)

// ── Network edit form ──────────────────────────────────────────────────────

const editingNetwork = ref(false)
const networkFormError = ref('')
const networkForm = reactive({
  slug: '',
  display_name: '',
  enabled: true,
  contact_email: '',
  footer_legal_name: '',
  logo_url: '',
  primary_colour: '#e53e3e',
  price_list_override: '',
  custom_header_copy: '',
  partner_logos: [],
  coordinators: [],
  network_signers: [],
})

function startEditNetwork() {
  const doc = networkDoc.value
  Object.assign(networkForm, {
    slug: doc?.slug ?? '',
    display_name: doc?.display_name ?? '',
    enabled: !!doc?.enabled,
    contact_email: doc?.contact_email ?? '',
    footer_legal_name: doc?.footer_legal_name ?? '',
    logo_url: doc?.logo_url ?? '',
    primary_colour: doc?.primary_colour ?? '#e53e3e',
    price_list_override: doc?.price_list_override ?? '',
    custom_header_copy: doc?.custom_header_copy ?? '',
    partner_logos: (doc?.partner_logos ?? []).map((row) => ({
      ...row,
      key: newRowKey(),
    })),
    coordinators: (doc?.coordinators ?? []).map((row) => ({
      ...row,
      key: newRowKey(),
    })),
    network_signers: (doc?.network_signers ?? []).map((row) => ({
      ...row,
      phone: row.phone ?? '',
      key: newRowKey(),
    })),
  })
  networkFormError.value = ''
  editingNetwork.value = true
}

function cancelEditNetwork() {
  if (isNewNetwork.value) {
    router.push({ name: 'Networks' })
  } else {
    editingNetwork.value = false
  }
  networkFormError.value = ''
}

function setNetworkLogo(file) {
  networkForm.logo_url = file?.file_url ?? ''
}

const saveNetworkResource = createResource({
  url: 'crm.api.optin_admin.save_network',
})
const negotiatedPriceListsResource = createResource({
  url: 'crm.api.optin_admin.list_negotiated_price_lists',
  auto: true,
})
const negotiatedPriceLists = computed(
  () => negotiatedPriceListsResource.data ?? [],
)

async function saveNetwork() {
  if (isNewNetwork.value && !networkForm.slug.trim()) {
    networkFormError.value = __('Slug is required.')
    return
  }
  if (!networkForm.display_name.trim()) {
    networkFormError.value = __('Display Name is required.')
    return
  }
  networkFormError.value = ''
  const data = {
    ...networkForm,
  }
  if (!isNewNetwork.value) {
    data.name = props.networkSlug
    data.slug = props.networkSlug
  } else {
    data.slug = networkForm.slug.trim()
  }
  try {
    const result = await saveNetworkResource.submit({ data })
    editingNetwork.value = false
    if (isNewNetwork.value) {
      router.replace({
        name: 'NetworkDetail',
        params: { networkSlug: result.name },
      })
    } else {
      networkResource.reload()
    }
  } catch (e) {
    networkFormError.value =
      e?.messages?.[0] ?? e?.message ?? __('Save failed.')
  }
}

function newRowKey() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function addPartner() {
  networkForm.partner_logos.push({
    key: newRowKey(),
    partner_name: '',
    logo: '',
    website: '',
  })
}

function setPartnerLogo(index, file) {
  networkForm.partner_logos[index].logo = file?.file_url ?? ''
}

function addSigner() {
  networkForm.network_signers.push({
    key: newRowKey(),
    full_name: '',
    email: '',
    phone: '',
  })
}

if (isNewNetwork.value) {
  startEditNetwork()
}

// ── Facilities list ────────────────────────────────────────────────────────

const page = ref(0)
const pageSize = 20
const facilitySearch = ref('')
const facilityLevelFilter = ref('')
const organizationFilter = ref('')
const contactSearch = ref('')
const contactOptInFilter = ref('')
const inviteStatusFilter = ref('')
const facilityLevels = [
  'Level 2',
  'Level 3',
  'Level 3C',
  'Level 3A',
  'Level 3B',
  'Level 4',
  'Level 4B',
  'Level 5A',
  'Level 5',
  'Level 6',
]
const inviteStatuses = ['Not Sent', 'Sending', 'Sent', 'Error']

const facilitiesResource = createResource({
  url: 'crm.api.optin_admin.list_facilities',
  makeParams: () => ({
    network: props.networkSlug,
    facility: facilitySearch.value || null,
    facility_level: facilityLevelFilter.value || null,
    organization: organizationFilter.value || null,
    contact: contactSearch.value || null,
    opted_in: contactOptInFilter.value || null,
    invite_status: inviteStatusFilter.value || null,
    page: page.value,
    page_size: pageSize,
  }),
  auto: true,
})

const contactRows = computed(() => facilitiesResource.data?.rows ?? [])
const contactTotal = computed(() => facilitiesResource.data?.total ?? 0)
const hasContactFilters = computed(
  () =>
    Boolean(facilitySearch.value) ||
    Boolean(facilityLevelFilter.value) ||
    Boolean(organizationFilter.value) ||
    Boolean(contactSearch.value) ||
    Boolean(contactOptInFilter.value) ||
    Boolean(inviteStatusFilter.value),
)

function applyContactFilters() {
  page.value = 0
  facilitiesResource.reload()
}

function clearContactFilters() {
  facilitySearch.value = ''
  facilityLevelFilter.value = ''
  organizationFilter.value = ''
  contactSearch.value = ''
  contactOptInFilter.value = ''
  inviteStatusFilter.value = ''
  applyContactFilters()
}

function prevPage() {
  page.value--
  facilitiesResource.reload()
}

function nextPage() {
  page.value++
  facilitiesResource.reload()
}

function networkMembership(row) {
  const memberships = row.memberships ?? []
  return (
    memberships.find((m) => m.network === props.networkSlug) ??
    memberships[0] ??
    null
  )
}

const showSampleQuote = ref(false)
const sampleQuote = ref(null)
const sampleQuoteLoading = ref(false)
const sampleQuoteFacility = ref(null)
const sampleQuoteResource = createResource({
  url: 'crm.api.optin_admin.get_facility_sample_quote',
})

function effectiveFacilityPriceList(row) {
  const membership = networkMembership(row)
  return (
    membership?.price_list_override ||
    networkDoc.value?.price_list_override ||
    ''
  )
}

function formatKes(value) {
  return `KES ${Number(value || 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

async function viewSampleQuote(row) {
  sampleQuoteFacility.value = row.name
  sampleQuoteLoading.value = true
  sampleQuote.value = null
  showSampleQuote.value = true
  try {
    sampleQuote.value = await sampleQuoteResource.submit({
      facility: row.name,
      network: props.networkSlug,
      price_list: effectiveFacilityPriceList(row),
    })
  } catch (error) {
    showSampleQuote.value = false
    toast.error(
      error?.messages?.[0] ??
        error?.message ??
        __('Could not load sample quote'),
    )
  } finally {
    sampleQuoteLoading.value = false
    sampleQuoteFacility.value = null
  }
}

function facilityPriceListLabel(row) {
  const membership = networkMembership(row)
  return membership?.price_list_override
    ? `${__('Price list')}: ${membership.price_list_override}`
    : `${__('Price list')}: ${networkDoc.value?.price_list_override || __('Opt-In default')}`
}

function isOptedIn(row) {
  return networkMembership(row)?.status === 'Opted In'
}

// ── Add / Edit contact form ────────────────────────────────────────────────

const showForm = ref(false)
const editingFacility = ref(null)
const formError = ref('')
const saveLoading = ref(false)
const removingName = ref(null)
const hfrLoading = ref(false)

const form = reactive({
  mfl_code: '',
  facility_name: '',
  organization: '',
  price_list_override: '',
  keph_level: '',
  contact_name: '',
  contact_email: '',
  contact_phone: '',
  status: 'Active',
})
const organizationEdited = ref(false)

function resetForm() {
  form.mfl_code = ''
  form.facility_name = ''
  form.organization = ''
  form.price_list_override = ''
  form.keph_level = ''
  form.contact_name = ''
  form.contact_email = ''
  form.contact_phone = ''
  form.status = 'Active'
  organizationEdited.value = false
  formError.value = ''
  editingFacility.value = null
}

function openAddForm() {
  resetForm()
  showForm.value = true
}

function editContact(row) {
  const m = networkMembership(row) ?? {}
  Object.assign(form, {
    mfl_code: row.mfl_code ?? '',
    facility_name: row.facility_name ?? '',
    organization: row.organization ?? row.facility_name ?? '',
    price_list_override: m.price_list_override ?? '',
    keph_level: row.keph_level ?? '',
    contact_name: m.contact_name ?? '',
    contact_email: m.contact_email ?? '',
    contact_phone: m.contact_phone ?? '',
    status: m.status ?? 'Active',
  })
  editingFacility.value = row
  organizationEdited.value = true
  formError.value = ''
  showForm.value = true
}

function cancelForm() {
  showForm.value = false
  resetForm()
}

const hfrResource = createResource({ url: 'crm.api.optin_admin.lookup_hfr' })

async function lookupHFR() {
  if (!form.mfl_code.trim()) return
  hfrLoading.value = true
  formError.value = ''
  try {
    const result = await hfrResource.submit({ mfl_code: form.mfl_code.trim() })
    if (result) {
      form.facility_name = result.facility_name ?? form.facility_name
      form.keph_level = result.keph_level ?? form.keph_level
      defaultOrganizationFromFacility()
    }
  } catch (e) {
    formError.value = e?.messages?.[0] ?? __('HFR lookup failed.')
  } finally {
    hfrLoading.value = false
  }
}

function defaultOrganizationFromFacility() {
  if (!editingFacility.value && !organizationEdited.value) {
    form.organization = form.facility_name
  }
}

const saveFacilityResource = createResource({
  url: 'crm.api.optin_admin.save_facility',
})

async function saveContact() {
  if (!form.mfl_code.trim()) {
    formError.value = __('MFL Code is required.')
    return
  }
  if (!form.facility_name.trim()) {
    formError.value = __('Facility Name is required.')
    return
  }
  if (!form.keph_level.trim()) {
    formError.value = __('KEPH Level is required.')
    return
  }
  if (!form.contact_name.trim()) {
    formError.value = __('Contact Name is required.')
    return
  }
  if (!form.contact_email.trim()) {
    formError.value = __('Contact Email is required.')
    return
  }
  if (!form.contact_phone.trim()) {
    formError.value = __('Contact Phone is required.')
    return
  }
  formError.value = ''
  saveLoading.value = true
  const data = {
    mfl_code: form.mfl_code,
    facility_name: form.facility_name,
    organization: form.organization,
    keph_level: form.keph_level,
    memberships: [
      {
        network: props.networkSlug,
        price_list_override: form.price_list_override,
        status: form.status,
        contact_name: form.contact_name,
        contact_email: form.contact_email,
        contact_phone: form.contact_phone,
      },
    ],
  }
  if (editingFacility.value?.name) data.name = editingFacility.value.name
  try {
    await saveFacilityResource.submit({ data })
    facilitiesResource.reload()
    showForm.value = false
    resetForm()
  } catch (e) {
    formError.value = e?.messages?.[0] ?? e?.message ?? __('Save failed.')
  } finally {
    saveLoading.value = false
  }
}

const deleteFacilityResource = createResource({
  url: 'crm.api.optin_admin.delete_facility',
})

async function removeContact(row) {
  if (
    !confirm(
      __('Remove "{0}" from this network? This cannot be undone.', [
        row.facility_name,
      ]),
    )
  )
    return
  removingName.value = row.name
  try {
    await deleteFacilityResource.submit({ name: row.name })
    facilitiesResource.reload()
  } finally {
    removingName.value = null
  }
}

const resendInviteResource = createResource({
  url: 'crm.api.optin_admin.resend_facility_invitation',
})
const resendingMembership = ref(null)

function canResendInvite(membership) {
  return (
    !!membership?.name &&
    membership.status === 'Active' &&
    !!membership.contact_email
  )
}

async function resendInvite(row) {
  const membership = networkMembership(row)
  if (!canResendInvite(membership)) return
  resendingMembership.value = membership.name
  try {
    await resendInviteResource.submit({
      facility_name: row.name,
      membership_name: membership.name,
    })
  } finally {
    resendingMembership.value = null
    facilitiesResource.reload()
  }
}

// ── CSV Import ─────────────────────────────────────────────────────────────

const showCsvSection = ref(false)
const csvFile = ref(null)
const csvFileInput = ref(null)
const csvPreviewRows = ref([])
const csvPreviewLoading = ref(false)
const csvImporting = ref(false)
const csvResult = ref('')

const validCsvCount = ref(0)

function toggleCsvSection() {
  showCsvSection.value = !showCsvSection.value
}

function readFileAsText(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = (e) => resolve(e.target.result)
    reader.onerror = () => reject(new Error('File read failed'))
    reader.readAsText(file)
  })
}

const csvPreviewResource = createResource({
  url: 'crm.api.optin_admin.import_facilities_csv',
})
const csvImportResource = createResource({
  url: 'crm.api.optin_admin.import_facilities_csv',
})

async function onFileChange(e) {
  const file = e.target.files?.[0] ?? null
  csvFile.value = file
  csvPreviewRows.value = []
  validCsvCount.value = 0
  csvResult.value = ''
  if (!file) return
  csvPreviewLoading.value = true
  try {
    const csvData = await readFileAsText(file)
    const result = await csvPreviewResource.submit({
      csv_data: csvData,
      network_slug: props.networkSlug,
      dry_run: 1,
    })
    csvPreviewRows.value = result?.rows ?? []
    validCsvCount.value =
      result?.valid_count ??
      csvPreviewRows.value.filter((row) => !row.error).length
  } catch (e) {
    csvResult.value = e?.messages?.[0] ?? __('Preview failed.')
  } finally {
    csvPreviewLoading.value = false
  }
}

async function importCsv() {
  if (!csvFile.value) return
  csvImporting.value = true
  csvResult.value = ''
  try {
    const csvData = await readFileAsText(csvFile.value)
    const result = await csvImportResource.submit({
      csv_data: csvData,
      network_slug: props.networkSlug,
      dry_run: 0,
    })
    const imported = result?.imported ?? 0
    const errors = result?.error_count ?? result?.errors?.length ?? 0
    csvResult.value = __('{0} imported, {1} errors.', [imported, errors])
    facilitiesResource.reload()
    csvFile.value = null
    csvPreviewRows.value = []
    validCsvCount.value = 0
  } catch (e) {
    csvResult.value = e?.messages?.[0] ?? __('Import failed.')
  } finally {
    csvImporting.value = false
  }
}

function clearCsv() {
  csvFile.value = null
  if (csvFileInput.value) csvFileInput.value.value = ''
  csvPreviewRows.value = []
  validCsvCount.value = 0
  csvResult.value = ''
}

const csvTemplateResource = createResource({
  url: 'crm.api.optin_admin.csv_template',
})

async function downloadTemplate() {
  try {
    const csvString = await csvTemplateResource.submit({})
    const blob = new Blob([csvString], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'facility_import_template.csv'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (e) {
    console.error('Template download failed', e)
  }
}

// ── Helpers ────────────────────────────────────────────────────────────────

function enabledPill(enabled) {
  const base = 'rounded-full px-2 py-0.5 text-xs font-medium'
  return enabled
    ? `${base} bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400`
    : `${base} bg-surface-gray-2 text-ink-gray-6 dark:bg-surface-gray-4 dark:text-ink-gray-4`
}

function statusPill(status) {
  const base = 'rounded-full px-2 py-0.5 text-xs font-medium'
  const map = {
    Active: `${base} bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400`,
    'Opted In': `${base} bg-surface-gray-3 text-ink-gray-8 dark:bg-surface-gray-5 dark:text-ink-gray-3`,
    Declined: `${base} bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400`,
  }
  return (
    map[status] ??
    `${base} bg-surface-gray-2 text-ink-gray-6 dark:bg-surface-gray-4 dark:text-ink-gray-4`
  )
}

function optInPill(optedIn) {
  const base = 'rounded-full px-2 py-0.5 text-xs font-medium'
  return optedIn
    ? `${base} bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400`
    : `${base} bg-surface-gray-2 text-ink-gray-6 dark:bg-surface-gray-4 dark:text-ink-gray-4`
}

function inviteStatusPill(status) {
  const base = 'rounded-full px-2 py-0.5 text-xs font-medium'
  const map = {
    Sent: `${base} bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400`,
    Error: `${base} bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400`,
    'Not Sent': `${base} bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400`,
    Sending: `${base} bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400`,
  }
  return (
    map[status] ??
    `${base} bg-surface-gray-2 text-ink-gray-6 dark:bg-surface-gray-4 dark:text-ink-gray-4`
  )
}

function formatDate(value) {
  if (!value) return ''
  return new Date(value).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}
</script>
