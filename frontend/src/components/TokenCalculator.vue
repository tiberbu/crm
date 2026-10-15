<script setup>
import { computed, ref, watch } from 'vue'

function __(text) {
  return typeof window !== 'undefined' && typeof window.__ === 'function' ? window.__(text) : text
}

const props = defineProps({
  packages: {
    type: Array,
    default: () => [],
  },
  config: {
    type: Object,
    default: () => ({}),
  },
  selectedPackageCode: {
    type: String,
    default: '',
  },
  context: {
    type: String,
    default: 'onboarding', // 'onboarding' | 'portal'
  },
  facilityName: {
    type: String,
    default: '',
  },
  compact: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['select-package', 'apply-plan'])

// Defaults from Excel model
const fallbackConfig = {
  monthly_platform_fee: 500,
  bill_value_per_token: 750,
  default_avg_bill: 1500,
  default_operating_days: 24,
  service_points: [
    { id: 'consultation', name: 'Consultation visit', tokens: 3, default_frequency: 1.0, applies_to: ['opd', 'ipd'] },
    { id: 'laboratory', name: 'Laboratory order', tokens: 6, default_frequency: 0.5, applies_to: ['opd', 'ipd'] },
    { id: 'prescription', name: 'Prescription processing', tokens: 6, default_frequency: 0.5, applies_to: ['opd', 'ipd'] },
    { id: 'imaging', name: 'Imaging order (X-ray, Ultrasound)', tokens: 12, default_frequency: 0.1, applies_to: ['opd', 'ipd'] },
    { id: 'procedure', name: 'Medical / Minor surgical procedure', tokens: 12, default_frequency: 0.05, applies_to: ['ipd'] },
    { id: 'inpatient_admission', name: 'Inpatient admission', tokens: 3, default_frequency: 0.05, applies_to: ['ipd'] },
    { id: 'program_visit', name: 'Chronic care / Program visit', tokens: 6, default_frequency: 0.05, applies_to: ['opd', 'ipd'] },
  ],
  presets: [
    { id: 'solo', label: 'Solo Practice / Clinic', description: 'Pilots & small community clinics', facility_type: 'opd', daily_patients: 5, avg_bill: 1500, operating_days: 24 },
    { id: 'active_opd', label: 'Active Outpatient Clinic', description: 'Steady patient volume & diagnostics', facility_type: 'opd', daily_patients: 10, avg_bill: 1500, operating_days: 24 },
    { id: 'medical_center', label: 'Medical Center / Hospital', description: 'OPD + Inpatient wards & procedures', facility_type: 'ipd', daily_patients: 25, avg_bill: 2500, operating_days: 24 },
  ],
}

const activeConfig = computed(() => {
  return {
    monthly_platform_fee: Number(props.config?.monthly_platform_fee ?? fallbackConfig.monthly_platform_fee),
    bill_value_per_token: Number(props.config?.bill_value_per_token ?? fallbackConfig.bill_value_per_token),
    default_avg_bill: Number(props.config?.default_avg_bill ?? fallbackConfig.default_avg_bill),
    default_operating_days: Number(props.config?.default_operating_days ?? fallbackConfig.default_operating_days),
    service_points: (props.config?.service_points?.length ? props.config.service_points : fallbackConfig.service_points),
    presets: (props.config?.presets?.length ? props.config.presets : fallbackConfig.presets),
  }
})

// Calculator Reactive State
const facilityType = ref('opd') // 'opd' | 'ipd'
const dailyPatients = ref(15)
const avgBill = ref(1500)
const operatingDays = ref(24)
const showCustomMix = ref(false)
const activePreset = ref('active_opd')

// Frequency overrides per service point: id -> percentage (0 to 100)
const serviceFrequencies = ref({})

function initFrequencies() {
  const map = {}
  for (const sp of activeConfig.value.service_points) {
    map[sp.id] = Math.round((sp.default_frequency ?? 0.5) * 100)
  }
  serviceFrequencies.value = map
}
initFrequencies()

// Apply Preset
function applyPreset(preset) {
  activePreset.value = preset.id
  facilityType.value = preset.facility_type || 'opd'
  dailyPatients.value = Number(preset.daily_patients || 15)
  avgBill.value = Number(preset.avg_bill || 1500)
  operatingDays.value = Number(preset.operating_days || 24)
}

function resetDefaults() {
  dailyPatients.value = 15
  avgBill.value = activeConfig.value.default_avg_bill
  operatingDays.value = activeConfig.value.default_operating_days
  facilityType.value = 'opd'
  activePreset.value = 'active_opd'
  initFrequencies()
}

// Service calculations
const eligibleServicePoints = computed(() => {
  return activeConfig.value.service_points.map((sp) => {
    const isApplicable = sp.applies_to ? sp.applies_to.includes(facilityType.value) : true
    const freqPercent = isApplicable ? (serviceFrequencies.value[sp.id] ?? 50) : 0
    const weightedTokens = isApplicable ? (sp.tokens * (freqPercent / 100)) : 0
    return {
      ...sp,
      isApplicable,
      freqPercent,
      weightedTokens,
    }
  })
})

const serviceTokensPerPatient = computed(() => {
  return eligibleServicePoints.value.reduce((acc, sp) => acc + (sp.weightedTokens || 0), 0)
})

const billTokensPerPatient = computed(() => {
  const ratio = activeConfig.value.bill_value_per_token || 750
  const bill = Math.max(0, Number(avgBill.value) || 0)
  return Math.ceil(bill / ratio)
})

const totalTokensPerPatient = computed(() => {
  return serviceTokensPerPatient.value + billTokensPerPatient.value
})

const monthlyEncounters = computed(() => {
  const patients = Math.max(1, Number(dailyPatients.value) || 1)
  const days = Math.max(1, Number(operatingDays.value) || 1)
  return patients * days
})

const monthlyPatientTokens = computed(() => {
  return Math.round(monthlyEncounters.value * totalTokensPerPatient.value)
})

const platformFee = computed(() => {
  return activeConfig.value.monthly_platform_fee || 500
})

const totalMonthlyDemand = computed(() => {
  return monthlyPatientTokens.value + platformFee.value
})

// Compare packages & generate metrics
const evaluatedPackages = computed(() => {
  const list = props.packages.filter((p) => Number(p.token_quantity) > 25) // Exclude sandbox/trial
  const pool = list.length ? list : props.packages

  return pool.map((pkg) => {
    const tokens = Number(pkg.token_quantity) || 0
    const demand = totalMonthlyDemand.value || 1
    const days = operatingDays.value || 24
    const dailyDemand = demand / days

    const runwayDays = dailyDemand > 0 ? tokens / dailyDemand : 0
    const runwayMonths = demand > 0 ? tokens / demand : 0

    const gross = Number(pkg.gross_total ?? pkg.price ?? 0)
    const costPerEncounter = tokens > 0 ? (gross / (tokens / totalTokensPerPatient.value)) : 0

    return {
      ...pkg,
      tokens,
      runwayDays: Math.round(runwayDays * 10) / 10,
      runwayMonths: Math.round(runwayMonths * 10) / 10,
      costPerEncounter: Math.round(costPerEncounter * 100) / 100,
    }
  })
})

// Determine Recommended Package
const recommendedPackage = computed(() => {
  if (!evaluatedPackages.value.length) return null
  const demand = totalMonthlyDemand.value

  // Starter tier: monthly demand <= 2200
  if (demand <= 2200) {
    return evaluatedPackages.value.find((p) => p.item_code === 'CV-TOKEN-STARTER') || evaluatedPackages.value[0]
  }
  // Growth tier: monthly demand 2201 - 4800 (covers 2,500-4,999 band)
  if (demand <= 4800) {
    return evaluatedPackages.value.find((p) => p.item_code === 'CV-TOKEN-GROWTH') || evaluatedPackages.value[1] || evaluatedPackages.value[0]
  }
  // Scale tier: monthly demand > 4800 (5,000+ tokens)
  return evaluatedPackages.value.find((p) => p.item_code === 'CV-TOKEN-SCALE') || evaluatedPackages.value.at(-1)
})

function selectPackage(pkg) {
  if (!pkg) return
  emit('select-package', pkg.item_code)
  emit('apply-plan', pkg)
}

function money(val, currency = 'KES') {
  if (val == null || isNaN(val)) return '—'
  return `${currency} ${Number(val).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
}
</script>

<template>
  <section
    class="rounded-2xl border border-[#f0d6d8] bg-gradient-to-br from-[#fffdfd] via-white to-[#fbf7f7] p-5 sm:p-7 shadow-[0_8px_30px_rgb(0,0,0,0.04)] backdrop-blur-md text-ink-gray-9 transition-all"
    data-testid="token-calculator"
  >
    <!-- Header -->
    <div class="flex flex-wrap items-center justify-between gap-3 border-b border-[#f0d6d8]/80 pb-5">
      <div>
        <div class="inline-flex items-center gap-2 rounded-full border border-[#f0d6d8] bg-[#fdf2f3] px-3 py-1 text-xs font-semibold text-[#bc1823]">
          <span class="text-sm">🧮</span>
          <span>{{ __('Interactive Token Sizing Calculator') }}</span>
        </div>
        <h3 class="mt-2 text-xl sm:text-2xl font-bold tracking-tight text-ink-gray-9">
          {{ facilityName ? `${facilityName}: ${__('Token Demand & Runway')}` : __('Estimate Your Facility Token Needs') }}
        </h3>
        <p class="mt-1 text-xs sm:text-sm text-ink-gray-7">
          {{ __('Tailored to your clinical encounter volume, diagnostic services, and billing patterns.') }}
        </p>
      </div>

      <button
        type="button"
        class="inline-flex items-center gap-1.5 rounded-xl border border-outline-gray-3 bg-white px-3 py-1.5 text-xs font-semibold text-ink-gray-7 shadow-sm hover:bg-surface-gray-1 hover:text-[#bc1823] transition-colors"
        @click="resetDefaults"
      >
        <span>↺</span>
        <span>{{ __('Reset to defaults') }}</span>
      </button>
    </div>

    <!-- Presets Bar -->
    <div class="mt-5">
      <label class="block text-xs font-bold uppercase tracking-wider text-ink-gray-7 mb-2">
        {{ __('Quick Facility Presets') }}
      </label>
      <div class="grid gap-2.5 sm:grid-cols-3">
        <button
          v-for="preset in activeConfig.presets"
          :key="preset.id"
          type="button"
          class="flex flex-col text-left rounded-xl p-3 border transition-all text-xs"
          :class="activePreset === preset.id
            ? 'border-[#bc1823] bg-[#fdf2f3] ring-2 ring-[#bc1823]/20 shadow-sm'
            : 'border-outline-gray-2 bg-white hover:border-[#f0d6d8] hover:bg-[#fffafa]'"
          @click="applyPreset(preset)"
        >
          <div class="flex items-center justify-between w-full">
            <span class="font-bold text-ink-gray-9">{{ preset.label }}</span>
            <span
              v-if="activePreset === preset.id"
              class="size-2 rounded-full bg-[#bc1823]"
            ></span>
          </div>
          <span class="mt-1 text-ink-gray-6 text-[11px] leading-tight">{{ preset.description }}</span>
          <span class="mt-2 font-mono text-[10px] text-[#bc1823] font-semibold">
            ~{{ preset.daily_patients }} {{ __('pts/day') }} · {{ preset.facility_type.toUpperCase() }}
          </span>
        </button>
      </div>
    </div>

    <!-- Main Form Grid -->
    <div class="mt-6 grid gap-6 lg:grid-cols-12 items-start">
      <!-- Input Controls (Left Column) -->
      <div class="lg:col-span-7 space-y-5">
        <!-- Facility Scope Toggle -->
        <div>
          <label class="block text-xs font-bold uppercase tracking-wider text-ink-gray-7 mb-2">
            {{ __('Clinical Scope & Departments') }}
          </label>
          <div class="grid grid-cols-2 gap-2 rounded-xl bg-surface-gray-2 p-1 border border-outline-gray-2">
            <button
              type="button"
              class="flex items-center justify-center gap-1.5 rounded-lg py-2 text-xs font-semibold transition-all"
              :class="facilityType === 'opd'
                ? 'bg-white text-[#bc1823] shadow-sm'
                : 'text-ink-gray-7 hover:text-ink-gray-9'"
              @click="facilityType = 'opd'; activePreset = ''"
            >
              <span>🩺</span>
              <span>{{ __('Outpatient Only (OPD)') }}</span>
            </button>
            <button
              type="button"
              class="flex items-center justify-center gap-1.5 rounded-lg py-2 text-xs font-semibold transition-all"
              :class="facilityType === 'ipd'
                ? 'bg-white text-[#bc1823] shadow-sm'
                : 'text-ink-gray-7 hover:text-ink-gray-9'"
              @click="facilityType = 'ipd'; activePreset = ''"
            >
              <span>🏥</span>
              <span>{{ __('Outpatient & Inpatient (OPD + IPD)') }}</span>
            </button>
          </div>
          <p class="mt-1.5 text-[11px] text-ink-gray-6 leading-tight">
            {{ facilityType === 'opd'
              ? __('OPD-only facilities are exempt from inpatient admission and surgical procedure token deductions.')
              : __('Comprehensive coverage including inpatient admissions, surgical procedures, and specialty care.')
            }}
          </p>
        </div>

        <!-- Daily Patients Slider & Direct Input -->
        <div class="rounded-xl border border-outline-gray-2 bg-white p-4 shadow-sm">
          <div class="flex items-center justify-between gap-3">
            <div>
              <label class="text-xs font-bold uppercase tracking-wider text-ink-gray-8 block">
                {{ __('Average Daily Patients') }}
              </label>
              <p class="text-[11px] text-ink-gray-6">
                {{ __('Unique patient encounters recorded per working day.') }}
              </p>
            </div>
            <div class="flex items-center gap-1.5">
              <input
                v-model.number="dailyPatients"
                type="number"
                min="1"
                max="250"
                class="w-20 rounded-lg border border-outline-gray-3 bg-surface-gray-1 px-3 py-1.5 text-right font-mono text-base font-bold text-ink-gray-9 focus:border-[#bc1823] focus:outline-none focus:ring-2 focus:ring-[#bc1823]/10"
                @input="activePreset = ''"
              />
              <span class="text-xs text-ink-gray-6 font-medium">{{ __('pts/day') }}</span>
            </div>
          </div>

          <div class="mt-4">
            <input
              v-model.number="dailyPatients"
              type="range"
              min="1"
              max="100"
              step="1"
              class="w-full accent-[#bc1823] cursor-pointer"
              @input="activePreset = ''"
            />
            <div class="flex justify-between text-[10px] font-mono text-ink-gray-5 mt-1">
              <span>1</span>
              <span>10</span>
              <span>25</span>
              <span>50</span>
              <span>75</span>
              <span>100+</span>
            </div>
          </div>

          <div class="mt-3 flex items-center justify-between border-t border-outline-gray-2/70 pt-2.5 text-xs text-ink-gray-7">
            <span>{{ __('Estimated Monthly Encounters') }}:</span>
            <span class="font-bold text-ink-gray-9 font-mono">
              ~{{ monthlyEncounters.toLocaleString() }} {{ __('encounters') }}
              <span class="text-ink-gray-5 font-normal">({{ operatingDays }} {{ __('operating days') }})</span>
            </span>
          </div>
        </div>

        <!-- Average Patient Bill & Operating Days -->
        <div class="grid gap-3 sm:grid-cols-2">
          <div class="rounded-xl border border-outline-gray-2 bg-white p-4 shadow-sm">
            <label class="text-xs font-bold uppercase tracking-wider text-ink-gray-8 block">
              {{ __('Average Patient Bill') }}
            </label>
            <p class="text-[11px] text-ink-gray-6 mb-2">
              {{ __('1 token per KES 750 bill value') }}
            </p>
            <div class="relative">
              <span class="absolute left-3 top-2 text-xs font-bold text-ink-gray-5">KES</span>
              <input
                v-model.number="avgBill"
                type="number"
                min="0"
                step="250"
                class="w-full rounded-lg border border-outline-gray-3 bg-surface-gray-1 pl-12 pr-3 py-1.5 font-mono text-sm font-bold text-ink-gray-9 focus:border-[#bc1823] focus:outline-none focus:ring-2 focus:ring-[#bc1823]/10"
                @input="activePreset = ''"
              />
            </div>
            <p class="mt-2 text-[11px] text-ink-gray-6 font-medium">
              = <strong class="text-ink-gray-9 font-mono">{{ billTokensPerPatient }} tokens</strong> {{ __('per patient bill') }}
            </p>
          </div>

          <div class="rounded-xl border border-outline-gray-2 bg-white p-4 shadow-sm">
            <label class="text-xs font-bold uppercase tracking-wider text-ink-gray-8 block">
              {{ __('Operating Days / Month') }}
            </label>
            <p class="text-[11px] text-ink-gray-6 mb-2">
              {{ __('Days facility is open per month') }}
            </p>
            <div class="flex items-center gap-1.5">
              <button
                v-for="days in [20, 24, 26, 30]"
                :key="days"
                type="button"
                class="flex-1 rounded-lg py-1.5 text-xs font-semibold transition-all font-mono"
                :class="operatingDays === days
                  ? 'bg-[#bc1823] text-white shadow-sm'
                  : 'bg-surface-gray-2 text-ink-gray-7 hover:bg-surface-gray-3'"
                @click="operatingDays = days"
              >
                {{ days }}d
              </button>
            </div>
            <p class="mt-2 text-[11px] text-ink-gray-6 font-medium">
              {{ operatingDays === 24 ? __('Standard 6-day work weeks') : operatingDays === 30 ? __('24/7 continuous operations') : `${operatingDays} days open` }}
            </p>
          </div>
        </div>

        <!-- Advanced Accordion: Service Point Mix -->
        <div class="rounded-xl border border-outline-gray-2 bg-white overflow-hidden shadow-sm">
          <button
            type="button"
            class="w-full flex items-center justify-between p-4 text-left text-xs font-semibold text-ink-gray-8 hover:bg-surface-gray-1 transition-colors"
            @click="showCustomMix = !showCustomMix"
          >
            <div class="flex items-center gap-2">
              <span class="text-sm">⚙️</span>
              <span class="font-bold">{{ __('Customize Service Points & Encounter Mix') }}</span>
              <span class="rounded bg-surface-gray-2 px-1.5 py-0.5 text-[10px] text-ink-gray-6 font-mono">
                {{ serviceTokensPerPatient.toFixed(1) }} {{ __('tokens/pt') }}
              </span>
            </div>
            <span class="text-ink-gray-5 font-mono text-xs">
              {{ showCustomMix ? '▲' : '▼' }}
            </span>
          </button>

          <div v-show="showCustomMix" class="border-t border-outline-gray-2 p-4 bg-surface-gray-1/40 space-y-3">
            <p class="text-[11px] text-ink-gray-6 leading-relaxed">
              {{ __('The pricing model applies service-point token billing only to the 7 clinical events below. Patient registrations, triage vitals, and dispensing consume 0 service tokens.') }}
            </p>

            <div class="space-y-2.5">
              <div
                v-for="sp in eligibleServicePoints"
                :key="sp.id"
                class="flex items-center justify-between gap-3 p-2.5 rounded-lg border bg-white text-xs"
                :class="sp.isApplicable ? 'border-outline-gray-2' : 'border-outline-gray-2/60 bg-surface-gray-2/60 opacity-60'"
              >
                <div class="min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="font-semibold text-ink-gray-9 truncate">{{ sp.name }}</span>
                    <span class="font-mono text-[11px] text-amber-700 bg-amber-50 border border-amber-200 px-1.5 py-0.2 rounded font-bold shrink-0">
                      {{ sp.tokens }} 🪙
                    </span>
                    <span
                      v-if="!sp.isApplicable"
                      class="text-[10px] font-bold uppercase tracking-wider text-emerald-700 bg-emerald-50 px-1.5 py-0.2 rounded border border-emerald-200 shrink-0"
                    >
                      {{ __('Exempt for OPD') }}
                    </span>
                  </div>
                  <p class="text-[10px] text-ink-gray-5 truncate mt-0.5">{{ sp.description }}</p>
                </div>

                <div v-if="sp.isApplicable" class="flex items-center gap-2 shrink-0">
                  <input
                    v-model.number="serviceFrequencies[sp.id]"
                    type="range"
                    min="0"
                    max="100"
                    step="5"
                    class="w-20 sm:w-28 accent-[#bc1823] cursor-pointer"
                  />
                  <span class="w-10 text-right font-mono font-bold text-ink-gray-9">
                    {{ serviceFrequencies[sp.id] ?? 0 }}%
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Live Calculation Results & Recommendation (Right Column Cockpit) -->
      <div class="lg:col-span-5 space-y-4">
        <!-- Monthly Demand Card -->
        <div class="rounded-2xl border-2 border-[#f0d6d8] bg-white p-5 shadow-sm">
          <span class="text-[10px] font-bold uppercase tracking-wider text-[#bc1823] bg-[#fdf2f3] px-2.5 py-0.5 rounded-full border border-[#f0d6d8]">
            {{ __('Projected Monthly Demand') }}
          </span>

          <div class="mt-4 flex items-baseline justify-between gap-2">
            <div>
              <p class="text-3xl sm:text-4xl font-extrabold tracking-tight text-ink-gray-9 font-mono">
                {{ totalMonthlyDemand.toLocaleString() }}
              </p>
              <p class="text-xs font-semibold text-[#bc1823] flex items-center gap-1 mt-0.5">
                <span>🪙</span>
                <span>{{ __('Care Tokens / month') }}</span>
              </p>
            </div>
            <div class="text-right text-xs text-ink-gray-6 font-mono">
              <div>~{{ (totalMonthlyDemand / operatingDays).toFixed(0) }} {{ __('tokens/day') }}</div>
              <div>{{ totalTokensPerPatient.toFixed(1) }} {{ __('tokens/pt') }}</div>
            </div>
          </div>

          <!-- Formula Breakdown -->
          <div class="mt-4 rounded-xl bg-surface-gray-1 p-3 text-xs space-y-1.5 border border-outline-gray-2/70 text-ink-gray-7">
            <div class="flex justify-between">
              <span>{{ __('Patient usage') }} ({{ monthlyEncounters }} × {{ totalTokensPerPatient.toFixed(1) }}):</span>
              <strong class="font-mono text-ink-gray-9">{{ monthlyPatientTokens.toLocaleString() }} 🪙</strong>
            </div>
            <div class="flex justify-between">
              <span>{{ __('Monthly platform access fee') }}:</span>
              <strong class="font-mono text-ink-gray-9">{{ platformFee }} 🪙</strong>
            </div>
            <div class="border-t border-outline-gray-2 pt-1.5 flex justify-between font-bold text-ink-gray-9">
              <span>{{ __('Total monthly requirement') }}:</span>
              <span class="font-mono text-[#bc1823]">{{ totalMonthlyDemand.toLocaleString() }} 🪙</span>
            </div>
          </div>
        </div>

        <!-- Recommended Package Value Card -->
        <div
          v-if="recommendedPackage"
          class="rounded-2xl border-2 border-[#bc1823] bg-gradient-to-br from-[#fff7f8] via-white to-[#fff0f2] p-5 shadow-md relative overflow-hidden"
          data-testid="recommended-package-card"
        >
          <div class="flex items-center justify-between gap-2">
            <span class="rounded-full bg-[#bc1823] px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-white shadow-sm flex items-center gap-1.5">
              <span>⭐</span>
              <span>{{ __('Recommended For You') }}</span>
            </span>
            <span
              v-if="recommendedPackage.item_code === 'CV-TOKEN-SCALE'"
              class="text-[11px] font-bold text-emerald-800 bg-emerald-100 border border-emerald-300 px-2.5 py-0.5 rounded-full"
            >
              {{ __('Best Value · Save 16.7%') }}
            </span>
            <span
              v-else-if="recommendedPackage.item_code === 'CV-TOKEN-GROWTH'"
              class="text-[11px] font-bold text-emerald-800 bg-emerald-100 border border-emerald-300 px-2.5 py-0.5 rounded-full"
            >
              {{ __('Save 8.3% vs Starter') }}
            </span>
          </div>

          <div class="mt-4">
            <h4 class="text-xl font-bold tracking-tight text-ink-gray-9">
              {{ recommendedPackage.display_name }} ({{ recommendedPackage.tokens?.toLocaleString() }} {{ __('Tokens') }})
            </h4>
            <p class="text-xs text-ink-gray-7 mt-1">
              {{ recommendedPackage.coverage_summary || recommendedPackage.description }}
            </p>
          </div>

          <div class="mt-4 flex items-baseline gap-2">
            <span class="text-3xl font-extrabold text-ink-gray-9 font-mono">
              {{ money(recommendedPackage.price_ex_vat ?? recommendedPackage.price, recommendedPackage.currency) }}
            </span>
            <span class="text-xs text-ink-gray-6 font-medium">
              {{ __('excl. VAT / month') }}
            </span>
          </div>
          <p v-if="recommendedPackage.gross_total" class="text-[11px] text-ink-gray-7 font-medium mt-0.5">
            {{ recommendedPackage.vat_label || 'VAT' }} {{ money(recommendedPackage.vat_amount, recommendedPackage.currency) }} ·
            <strong class="text-ink-gray-9">{{ __('Total') }} {{ money(recommendedPackage.gross_total, recommendedPackage.currency) }}</strong>
          </p>

          <!-- Key Metrics Badges -->
          <div class="mt-4 grid grid-cols-2 gap-2 text-xs">
            <div class="rounded-xl border border-[#f0d6d8] bg-white/90 p-2.5 shadow-xs">
              <span class="text-[10px] font-semibold text-ink-gray-6 uppercase block">{{ __('Estimated Runway') }}</span>
              <p class="mt-0.5 text-sm font-bold text-[#bc1823] font-mono">
                ~{{ recommendedPackage.runwayDays }} {{ __('days') }}
                <span class="text-[11px] text-ink-gray-6 font-normal">({{ recommendedPackage.runwayMonths }} {{ __('mo') }})</span>
              </p>
            </div>
            <div class="rounded-xl border border-[#f0d6d8] bg-white/90 p-2.5 shadow-xs">
              <span class="text-[10px] font-semibold text-ink-gray-6 uppercase block">{{ __('Cost / Patient') }}</span>
              <p class="mt-0.5 text-sm font-bold text-emerald-800 font-mono">
                {{ money(recommendedPackage.costPerEncounter, recommendedPackage.currency) }}
              </p>
            </div>
          </div>

          <!-- Select Action Button -->
          <div class="mt-5">
            <button
              type="button"
              class="w-full flex items-center justify-center gap-2 py-3 px-4 rounded-xl text-xs font-bold text-white transition-all shadow-md"
              :class="selectedPackageCode === recommendedPackage.item_code
                ? 'bg-emerald-700 hover:bg-emerald-800'
                : 'bg-[#bc1823] hover:bg-[#a3141d] active:scale-[0.99]'"
              @click="selectPackage(recommendedPackage)"
            >
              <span>{{ selectedPackageCode === recommendedPackage.item_code ? '✓' : '👉' }}</span>
              <span>
                {{
                  selectedPackageCode === recommendedPackage.item_code
                    ? __('Plan Selected for Facility')
                    : context === 'portal'
                      ? `${__('Order')} ${recommendedPackage.display_name} (${recommendedPackage.tokens?.toLocaleString()} Tokens)`
                      : `${__('Select')} ${recommendedPackage.display_name} (${recommendedPackage.tokens?.toLocaleString()} Tokens)`
                }}
              </span>
            </button>
          </div>
        </div>

        <!-- Runway Comparison across available packages -->
        <div v-if="evaluatedPackages.length > 1" class="rounded-xl border border-outline-gray-2 bg-white p-4 shadow-sm">
          <p class="text-[11px] font-bold uppercase tracking-wider text-ink-gray-7 mb-2.5">
            {{ __('Package Runway Comparison at Your Volume') }}
          </p>
          <div class="space-y-2">
            <div
              v-for="pkg in evaluatedPackages"
              :key="pkg.item_code"
              class="flex items-center justify-between p-2 rounded-lg border text-xs transition-colors cursor-pointer"
              :class="selectedPackageCode === pkg.item_code
                ? 'border-[#bc1823] bg-[#fdf2f3]'
                : 'border-outline-gray-2 hover:border-[#f0d6d8] hover:bg-surface-gray-1'"
              @click="selectPackage(pkg)"
            >
              <div>
                <span class="font-bold text-ink-gray-9">{{ pkg.display_name }}</span>
                <span class="text-ink-gray-5 ml-1 font-mono">({{ pkg.tokens?.toLocaleString() }} 🪙)</span>
              </div>
              <div class="flex items-center gap-3">
                <span class="font-mono text-ink-gray-7">
                  ~<strong>{{ pkg.runwayDays }}</strong> {{ __('days') }}
                </span>
                <span
                  class="size-4 rounded-full border flex items-center justify-center text-[10px]"
                  :class="selectedPackageCode === pkg.item_code
                    ? 'border-[#bc1823] bg-[#bc1823] text-white font-bold'
                    : 'border-outline-gray-3 text-transparent'"
                >
                  ✓
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
