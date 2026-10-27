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
    default: 'onboarding', // 'onboarding' | 'portal' | 'landing'
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

const emit = defineEmits(['select-package', 'apply-plan', 'start-onboarding'])

// Defaults from Excel model
const fallbackConfig = {
  monthly_platform_fee: 500,
  bill_value_per_token: 750,
  default_avg_bill: 1500,
  default_operating_days: 24,
  service_points: [
    { id: 'registration', name: 'Patient registration / check-in', tokens: 6, default_frequency: 0.2, applies_to: ['opd', 'ipd'] },
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
const showAdvancedSettings = ref(false)
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
  showAdvancedSettings.value = false
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
  const source = Array.isArray(props.packages) ? props.packages : []
  const list = source.filter(
    (p) => p.item_code !== 'CV-TOKEN-FREE' && Number(p.price_ex_vat ?? p.price ?? 0) > 0,
  ) // Exclude sandbox/trial
  const pool = list.length ? list : source

  return pool.map((pkg) => {
    const tokens = Number(pkg.tokens || pkg.token_quantity) || 0
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

// Suggest the smallest configured package that covers the estimate.
const recommendedPackage = computed(() => {
  if (!evaluatedPackages.value.length) return null
  const demand = totalMonthlyDemand.value
  const byCapacity = [...evaluatedPackages.value].sort((a, b) => a.tokens - b.tokens)
  return byCapacity.find((pkg) => pkg.tokens >= demand) || byCapacity.at(-1)
})

function selectPackage(pkg) {
  if (!pkg) return
  emit('select-package', pkg.item_code)
  emit('apply-plan', pkg)
  if (props.context === 'landing') {
    emit('start-onboarding', pkg)
  }
}

function money(val, currency = 'KES') {
  if (val == null || isNaN(val)) return '—'
  return `${currency} ${Number(val).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
}
</script>

<template>
  <section
    class="rounded-3xl border border-[#f0d6d8]/80 bg-white p-5 sm:p-7 shadow-[0_10px_30px_rgb(188,24,35,0.03)] text-ink-gray-9 transition-all"
    data-testid="token-calculator"
  >
    <!-- Header -->
    <div class="flex flex-wrap items-center justify-between gap-3 border-b border-outline-gray-2/80 pb-4 sm:pb-5">
      <div>
        <div class="inline-flex items-center gap-1.5 rounded-full border border-[#f0d6d8] bg-[#fdf2f3] px-2.5 py-0.5 text-xs font-semibold text-[#bc1823]">
          <span class="size-1.5 rounded-full bg-[#bc1823]"></span>
          <span>{{ __('Interactive Token Sizing Calculator') }}</span>
        </div>
        <h3 class="mt-2 text-xl sm:text-2xl font-bold tracking-tight text-ink-gray-9">
          {{ facilityName ? `${facilityName}: ${__('Token Demand & Plan Sizing')}` : __('Estimate Your Facility Token Needs') }}
        </h3>
        <p class="mt-1 text-xs sm:text-sm text-ink-gray-6">
          {{ __('Estimate token use from your monthly patient volume and services. This is a guide; you will see available packages and current prices before submitting.') }}
        </p>
      </div>

      <button
        type="button"
        class="inline-flex items-center gap-1.5 rounded-xl border border-outline-gray-3 bg-white px-3 py-1.5 text-xs font-semibold text-ink-gray-6 hover:bg-surface-gray-1 hover:text-[#bc1823] transition-colors"
        @click="resetDefaults"
      >
        <span>↺</span>
        <span>{{ __('Reset to defaults') }}</span>
      </button>
    </div>

    <!-- Step 1: Practice Profile & Volume Controls -->
    <div class="mt-6 space-y-4">
      <!-- Clinic Presets -->
      <div>
        <div class="flex items-center justify-between mb-2">
          <label class="text-xs font-bold uppercase tracking-wider text-ink-gray-7">
            {{ __('1. Choose Clinic Profile') }}
          </label>
          <span class="text-xs text-ink-gray-5">
            {{ __('Select a preset or customize below') }}
          </span>
        </div>
        <div class="grid gap-3 sm:grid-cols-3">
          <button
            v-for="preset in activeConfig.presets"
            :key="preset.id"
            type="button"
            class="flex flex-col text-left rounded-2xl p-3.5 sm:p-4 border transition-all text-xs"
            :class="activePreset === preset.id
              ? 'border-[#bc1823] bg-[#fdf2f3]/70 ring-2 ring-[#bc1823]/20 shadow-xs'
              : 'border-outline-gray-2 bg-white hover:border-[#f0d6d8] hover:bg-[#fffafa]'"
            @click="applyPreset(preset)"
          >
            <div class="flex items-center justify-between w-full">
              <span class="font-bold text-ink-gray-9 text-sm">{{ preset.label }}</span>
              <span
                v-if="activePreset === preset.id"
                class="size-2 rounded-full bg-[#bc1823]"
              ></span>
            </div>
            <span class="mt-1 text-ink-gray-6 text-xs leading-relaxed">{{ preset.description }}</span>
            <span class="mt-2.5 font-mono text-[11px] text-[#bc1823] font-semibold">
              ~{{ preset.daily_patients }} {{ __('pts/day') }} · {{ preset.facility_type.toUpperCase() }}
            </span>
          </button>
        </div>
      </div>

      <!-- Daily Patients Slider Card -->
      <div class="rounded-2xl border border-outline-gray-2 bg-surface-gray-1/30 p-4 sm:p-5">
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <label class="text-xs font-bold uppercase tracking-wider text-ink-gray-8 block">
              {{ __('2. Average Daily Patient Encounters') }}
            </label>
            <p class="text-xs text-ink-gray-6 mt-0.5">
              {{ __('Unique patients seen per operating day') }}
            </p>
          </div>
          <div class="flex items-center gap-2">
            <button
              type="button"
              class="flex size-8 items-center justify-center rounded-xl border border-outline-gray-3 bg-white text-base font-bold text-ink-gray-7 hover:bg-surface-gray-2 active:bg-surface-gray-3 transition-colors shadow-2xs"
              :disabled="dailyPatients <= 1"
              @click="dailyPatients = Math.max(1, dailyPatients - 1); activePreset = ''"
              aria-label="Decrease daily patients"
            >
              −
            </button>
            <input
              v-model.number="dailyPatients"
              type="number"
              min="1"
              max="250"
              class="w-18 rounded-xl border border-outline-gray-3 bg-white px-2 py-1.5 text-center font-mono text-base font-bold text-ink-gray-9 shadow-2xs focus:border-[#bc1823] focus:outline-none focus:ring-2 focus:ring-[#bc1823]/10"
              @input="activePreset = ''"
            />
            <button
              type="button"
              class="flex size-8 items-center justify-center rounded-xl border border-outline-gray-3 bg-white text-base font-bold text-ink-gray-7 hover:bg-surface-gray-2 active:bg-surface-gray-3 transition-colors shadow-2xs"
              @click="dailyPatients = Number(dailyPatients || 0) + 1; activePreset = ''"
              aria-label="Increase daily patients"
            >
              +
            </button>
            <span class="text-xs font-semibold text-ink-gray-6 ml-1">{{ __('pts / day') }}</span>
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
          <div class="flex justify-between text-[11px] font-mono text-ink-gray-5 mt-1.5">
            <span>1</span>
            <span>10</span>
            <span>25</span>
            <span>50</span>
            <span>75</span>
            <span>100+</span>
          </div>
        </div>

        <div class="mt-3.5 flex items-center justify-between border-t border-outline-gray-2/70 pt-2.5 text-xs text-ink-gray-7">
          <span class="font-medium">{{ __('Projected Monthly Encounters') }}:</span>
          <span class="font-bold text-ink-gray-9 font-mono">
            ~{{ monthlyEncounters.toLocaleString() }} {{ __('encounters') }}
            <span class="text-ink-gray-5 font-normal">({{ operatingDays }} {{ __('operating days') }})</span>
          </span>
        </div>
      </div>
    </div>

    <!-- Step 2: Clear Outcome Cockpit (Demand & Recommendation Hero) -->
    <div class="mt-6 grid gap-5 lg:grid-cols-12 items-stretch">
      <!-- Projected Demand Card (Left) -->
      <div class="lg:col-span-5 rounded-2xl border border-outline-gray-2 bg-white p-5 flex flex-col justify-between shadow-2xs">
        <div>
          <div class="flex items-center justify-between gap-2">
            <span class="text-xs font-bold uppercase tracking-wider text-[#bc1823] bg-[#fdf2f3] px-2.5 py-0.5 rounded-full border border-[#f0d6d8]">
              {{ __('Estimated monthly token needs') }}
            </span>
            <span class="text-xs font-mono text-ink-gray-6 font-semibold">
              ~{{ (totalMonthlyDemand / operatingDays).toFixed(0) }} {{ __('tokens/day') }}
            </span>
          </div>

          <div class="mt-4">
            <p class="text-4xl sm:text-5xl font-black tracking-tight text-ink-gray-9 font-mono">
              {{ totalMonthlyDemand.toLocaleString() }}
            </p>
            <p class="text-xs font-semibold text-[#bc1823] flex items-center gap-1 mt-1">
              <span>🪙</span>
              <span>{{ __('Care Tokens / month needed') }}</span>
            </p>
          </div>
        </div>

        <!-- Formula Breakdown -->
        <div class="mt-5 rounded-xl bg-surface-gray-1 p-3.5 text-xs space-y-2 border border-outline-gray-2/70 text-ink-gray-7">
          <div class="flex justify-between">
            <span>{{ __('Patient usage') }} ({{ monthlyEncounters }} × {{ totalTokensPerPatient.toFixed(1) }}):</span>
            <strong class="font-mono text-ink-gray-9">{{ monthlyPatientTokens.toLocaleString() }} 🪙</strong>
          </div>
          <div class="flex justify-between">
            <span>{{ __('Monthly platform access fee') }}:</span>
            <strong class="font-mono text-ink-gray-9">{{ platformFee }} 🪙</strong>
          </div>
          <div class="border-t border-outline-gray-2 pt-2 flex justify-between font-bold text-ink-gray-9">
            <span>{{ __('Total monthly requirement') }}:</span>
            <span class="font-mono text-[#bc1823]">{{ totalMonthlyDemand.toLocaleString() }} 🪙</span>
          </div>
        </div>
      </div>

      <!-- Recommended Plan Hero Card (Right) -->
      <div
        v-if="recommendedPackage"
        class="lg:col-span-7 rounded-2xl border-2 border-[#bc1823] bg-gradient-to-br from-[#fff7f8] via-white to-[#fff0f2] p-5 sm:p-6 shadow-sm flex flex-col justify-between relative overflow-hidden"
        data-testid="recommended-package-card"
      >
        <div>
          <div class="flex items-center justify-between gap-2 flex-wrap">
            <span class="rounded-full bg-[#bc1823] px-3 py-1 text-xs font-bold uppercase tracking-wider text-white shadow-xs flex items-center gap-1.5">
              <span>⭐</span>
              <span>{{ __('Suggested package for this estimate') }}</span>
            </span>
          </div>

          <div class="mt-4 flex flex-col sm:flex-row sm:items-baseline justify-between gap-2">
            <div>
              <h4 class="text-xl sm:text-2xl font-bold tracking-tight text-ink-gray-9">
                {{ recommendedPackage.display_name }} ({{ recommendedPackage.tokens?.toLocaleString() }} {{ __('Tokens') }})
              </h4>
              <p class="text-xs text-ink-gray-6 mt-1">
                {{ recommendedPackage.coverage_summary || recommendedPackage.description }}
              </p>
            </div>
            <div class="text-left sm:text-right shrink-0">
              <span class="text-2xl sm:text-3xl font-black text-ink-gray-9 font-mono">
                {{ money(recommendedPackage.price_ex_vat ?? recommendedPackage.price, recommendedPackage.currency) }}
              </span>
              <span class="text-xs text-ink-gray-5 font-medium block">
                {{ __('excl. VAT') }}
              </span>
            </div>
          </div>

          <!-- Key Metrics Badges -->
          <div class="mt-4 grid grid-cols-2 gap-3 text-xs">
            <div class="rounded-xl border border-[#f0d6d8] bg-white p-3 shadow-2xs">
              <span class="text-[11px] font-semibold text-ink-gray-6 uppercase block">{{ __('Estimated Runway') }}</span>
              <p class="mt-1 text-base font-bold text-[#bc1823] font-mono">
                ~{{ recommendedPackage.runwayDays }} {{ __('days') }}
                <span class="text-xs text-ink-gray-5 font-normal">({{ recommendedPackage.runwayMonths }} {{ __('mo') }})</span>
              </p>
            </div>
            <div class="rounded-xl border border-[#f0d6d8] bg-white p-3 shadow-2xs">
              <span class="text-[11px] font-semibold text-ink-gray-6 uppercase block">{{ __('Cost / Patient') }}</span>
              <p class="mt-1 text-base font-bold text-emerald-800 font-mono">
                {{ money(recommendedPackage.costPerEncounter, recommendedPackage.currency) }}
              </p>
            </div>
          </div>
        </div>

        <!-- Primary Action CTA -->
        <div class="mt-5 pt-3 border-t border-[#f0d6d8]/80">
          <button
            type="button"
            class="w-full min-h-12 flex items-center justify-center gap-2 py-3.5 px-5 rounded-xl text-sm font-bold text-white transition-all shadow-sm"
            :class="selectedPackageCode === recommendedPackage.item_code
              ? 'bg-emerald-700 hover:bg-emerald-800'
              : 'bg-[#bc1823] hover:bg-[#a3141d] active:scale-[0.99]'"
            @click="selectPackage(recommendedPackage)"
          >
            <span>{{ context === 'landing' ? '🚀' : selectedPackageCode === recommendedPackage.item_code ? '✓' : '👉' }}</span>
            <span>
              {{
                context === 'landing'
                  ? `${__('Start onboarding with')} ${recommendedPackage.display_name} (${recommendedPackage.tokens?.toLocaleString()} Tokens) →`
                  : selectedPackageCode === recommendedPackage.item_code
                    ? __('Plan Selected for Facility')
                    : context === 'portal'
                      ? `${__('Order')} ${recommendedPackage.display_name} (${recommendedPackage.tokens?.toLocaleString()} Tokens)`
                      : `${__('Select')} ${recommendedPackage.display_name} (${recommendedPackage.tokens?.toLocaleString()} Tokens)`
              }}
            </span>
          </button>

          <!-- Landing Context Secondary Link -->
          <div v-if="context === 'landing'" class="text-center pt-2">
            <button
              type="button"
              class="text-xs font-semibold text-[#bc1823] hover:text-[#a3141d] hover:underline inline-flex items-center gap-1"
              @click="selectPackage(recommendedPackage)"
            >
              <span>{{ __('Or start onboarding directly') }}</span>
              <span>→</span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Step 3: Package Comparison Matrix (All tiers at a glance) -->
    <div v-if="evaluatedPackages.length > 1" class="mt-6">
      <div class="flex items-center justify-between mb-2.5">
        <label class="text-xs font-bold uppercase tracking-wider text-ink-gray-7">
          {{ __('3. Package Runway Comparison at Your Volume') }}
        </label>
        <span class="text-xs text-ink-gray-5">
          {{ __('Click any plan to select it') }}
        </span>
      </div>
      <div class="grid gap-3 sm:grid-cols-3">
        <div
          v-for="pkg in evaluatedPackages"
          :key="pkg.item_code"
          class="flex flex-col justify-between p-3.5 sm:p-4 rounded-2xl border text-xs transition-all cursor-pointer"
          :class="selectedPackageCode === pkg.item_code
            ? 'border-[#bc1823] bg-[#fdf2f3] ring-2 ring-[#bc1823]/20 shadow-xs'
            : 'border-outline-gray-2 bg-white hover:border-[#f0d6d8] hover:bg-surface-gray-1'"
          @click="selectPackage(pkg)"
        >
          <div>
            <div class="flex items-center justify-between">
              <span class="font-bold text-sm text-ink-gray-9">{{ pkg.display_name }}</span>
              <span class="font-mono text-xs text-[#bc1823] font-bold">{{ pkg.tokens?.toLocaleString() }} 🪙</span>
            </div>
            <p class="text-xs text-ink-gray-6 mt-1 font-mono">
              {{ money(pkg.price_ex_vat ?? pkg.price, pkg.currency) }} <span class="text-[10px] text-ink-gray-5">excl. VAT</span>
            </p>
          </div>
          <div class="mt-3.5 pt-2.5 border-t border-outline-gray-1 flex items-center justify-between text-xs">
            <span class="text-ink-gray-7">
              {{ __('Runway') }}: <strong class="font-mono text-ink-gray-9">~{{ pkg.runwayDays }}d</strong> ({{ pkg.runwayMonths }} mo)
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

    <!-- Step 4: Collapsible Clinical Fine-Tuning Drawer (Spacious Progressive Disclosure) -->
    <div class="mt-6 rounded-2xl border border-outline-gray-2 bg-surface-gray-1/30 overflow-hidden">
      <button
        type="button"
        class="w-full flex items-center justify-between p-4 text-left text-xs font-semibold text-ink-gray-8 hover:bg-surface-gray-1 transition-colors"
        @click="showAdvancedSettings = !showAdvancedSettings"
      >
        <div class="flex items-center gap-2.5">
          <span class="text-base">⚙️</span>
          <span class="font-bold text-sm">{{ __('Fine-tune Clinical Assumptions & Mix') }}</span>
          <span class="rounded-full bg-surface-gray-2 border border-outline-gray-2 px-2.5 py-0.5 text-xs text-ink-gray-6 font-mono hidden md:inline">
            {{ facilityType.toUpperCase() }} · {{ operatingDays }} days · KES {{ avgBill }} avg bill
          </span>
        </div>
        <div class="flex items-center gap-1.5 text-xs text-ink-gray-6 font-semibold">
          <span>{{ showAdvancedSettings ? __('Hide details') : __('Customize assumptions') }}</span>
          <span class="font-mono text-xs">{{ showAdvancedSettings ? '▲' : '▼' }}</span>
        </div>
      </button>

      <!-- Expandable Clinical Settings Drawer -->
      <div v-show="showAdvancedSettings" class="border-t border-outline-gray-2 p-5 bg-white space-y-5">
        <!-- 3-Column Control Grid for Scope, Avg Bill, and Operating Days -->
        <div class="grid gap-4 md:grid-cols-3">
          <!-- Scope Toggle -->
          <div class="space-y-1.5">
            <label class="block text-xs font-bold uppercase tracking-wider text-ink-gray-7">
              {{ __('Clinical Scope & Departments') }}
            </label>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-1.5 rounded-xl bg-surface-gray-2 p-1 border border-outline-gray-2">
              <button
                type="button"
                class="flex items-center justify-center gap-1 rounded-lg py-2 text-xs font-semibold transition-all"
                :class="facilityType === 'opd'
                  ? 'bg-white text-[#bc1823] shadow-xs'
                  : 'text-ink-gray-7 hover:text-ink-gray-9'"
                @click="facilityType = 'opd'; activePreset = ''"
              >
                <span>🩺</span>
                <span>{{ __('Outpatient Only (OPD)') }}</span>
              </button>
              <button
                type="button"
                class="flex items-center justify-center gap-1 rounded-lg py-2 text-xs font-semibold transition-all"
                :class="facilityType === 'ipd'
                  ? 'bg-white text-[#bc1823] shadow-xs'
                  : 'text-ink-gray-7 hover:text-ink-gray-9'"
                @click="facilityType = 'ipd'; activePreset = ''"
              >
                <span>🏥</span>
                <span>{{ __('OPD + IPD') }}</span>
              </button>
            </div>
            <p class="text-[11px] text-ink-gray-5 leading-tight">
              {{ facilityType === 'opd' ? __('Exempt from inpatient admission and surgical procedure deductions.') : __('Full coverage for inpatient admissions and surgical procedures.') }}
            </p>
          </div>

          <!-- Average Patient Bill -->
          <div class="space-y-1.5">
            <label class="block text-xs font-bold uppercase tracking-wider text-ink-gray-7">
              {{ __('Average Patient Bill') }}
            </label>
            <div class="relative">
              <span class="absolute left-3 top-2 text-xs font-bold text-ink-gray-5">KES</span>
              <input
                v-model.number="avgBill"
                type="number"
                min="0"
                step="250"
                class="w-full rounded-xl border border-outline-gray-3 bg-surface-gray-1 pl-12 pr-3 py-2 font-mono text-base sm:text-sm font-bold text-ink-gray-9 focus:border-[#bc1823] focus:outline-none focus:ring-2 focus:ring-[#bc1823]/10"
                @input="activePreset = ''"
              />
            </div>
            <p class="text-[11px] text-ink-gray-5 font-mono">
              = {{ billTokensPerPatient }} tokens / patient bill (1 per KES 750)
            </p>
          </div>

          <!-- Operating Days / Month -->
          <div class="space-y-1.5">
            <label class="block text-xs font-bold uppercase tracking-wider text-ink-gray-7">
              {{ __('Operating Days / Month') }}
            </label>
            <div class="flex items-center gap-1.5">
              <button
                v-for="days in [20, 24, 26, 30]"
                :key="days"
                type="button"
                class="flex-1 rounded-xl py-2 text-xs font-semibold transition-all font-mono"
                :class="operatingDays === days
                  ? 'bg-[#bc1823] text-white shadow-xs'
                  : 'bg-surface-gray-2 text-ink-gray-7 hover:bg-surface-gray-3'"
                @click="operatingDays = days"
              >
                {{ days }}d
              </button>
            </div>
            <p class="text-[11px] text-ink-gray-5">
              {{ operatingDays === 24 ? __('Standard 6-day work weeks') : operatingDays === 30 ? __('24/7 continuous operations') : `${operatingDays} days open` }}
            </p>
          </div>
        </div>

        <!-- Diagnostic & Clinical Services Frequency Sliders -->
        <div class="border-t border-outline-gray-2 pt-4">
          <div class="flex items-center justify-between mb-3">
            <div>
              <h5 class="text-xs font-bold uppercase tracking-wider text-ink-gray-8">
                {{ __('Diagnostic & Clinical Service Frequencies') }}
              </h5>
              <p class="text-xs text-ink-gray-5 mt-0.5">
                {{ __('Percentage of patient encounters utilizing each clinical service point') }}
              </p>
            </div>
            <span class="rounded-full bg-surface-gray-2 border border-outline-gray-2 px-3 py-1 text-xs font-mono font-bold text-ink-gray-8">
              {{ serviceTokensPerPatient.toFixed(1) }} {{ __('tokens/pt') }}
            </span>
          </div>

          <div class="grid gap-3 sm:grid-cols-2">
            <div
              v-for="sp in eligibleServicePoints"
              :key="sp.id"
              class="flex items-center justify-between gap-3 p-3 rounded-xl border bg-surface-gray-1/30 text-xs"
              :class="sp.isApplicable ? 'border-outline-gray-2' : 'border-outline-gray-2/60 bg-surface-gray-2/60 opacity-60'"
            >
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-1.5 flex-wrap">
                  <span class="font-semibold text-ink-gray-9">{{ sp.name }}</span>
                  <span class="font-mono text-[11px] text-amber-800 bg-amber-50 border border-amber-200 px-1.5 py-0.2 rounded font-bold shrink-0">
                    {{ sp.tokens }} 🪙
                  </span>
                  <span
                    v-if="!sp.isApplicable"
                    class="text-[10px] font-bold uppercase tracking-wider text-emerald-700 bg-emerald-50 px-1.5 py-0.2 rounded border border-emerald-200 shrink-0"
                  >
                    {{ __('Exempt for OPD') }}
                  </span>
                </div>
              </div>

              <div v-if="sp.isApplicable" class="flex items-center gap-2 shrink-0">
                <input
                  v-model.number="serviceFrequencies[sp.id]"
                  type="range"
                  min="0"
                  max="100"
                  step="5"
                  class="w-24 sm:w-28 accent-[#bc1823] cursor-pointer"
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
  </section>
</template>
