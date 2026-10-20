import frappeUIPreset from 'frappe-ui/tailwind'
import colors from 'tailwindcss/colors'

export default {
  presets: [frappeUIPreset],
  content: [
    './index.html',
    './src/**/*.{vue,js,ts,jsx,tsx}',
    './node_modules/frappe-ui/src/**/*.{vue,js,ts,jsx,tsx}',
    '../node_modules/frappe-ui/src/**/*.{vue,js,ts,jsx,tsx}',
    './node_modules/frappe-ui/frappe/**/*.{vue,js,ts,jsx,tsx}',
    '../node_modules/frappe-ui/frappe/**/*.{vue,js,ts,jsx,tsx}',
    // linked @framework/ui source (apps/frappe/ui/src) — scan so its utility and
    // arbitrary-variant classes (e.g. Notifications TabButtons overrides) are generated
    '../../frappe/ui/src/**/*.{vue,js,ts,jsx,tsx}',
  ],
  safelist: [{ pattern: /!(text|bg)-/, variants: ['hover', 'active'] }],
  theme: {
    extend: {
      colors: {
        emerald: colors.emerald,
        rose: colors.rose,
        slate: colors.slate,
        amber: colors.amber,
        // CX Portal token palette — maps 1:1 to the --cx-* CSS variables in
        // src/index.css (light + dark). This is the only color namespace the
        // portal templates may use (plus raw emerald/amber/rose saturated
        // fills where Safaricom/semantic brand green or status accents are
        // intentional).
        cx: {
          bg: 'var(--cx-bg)',
          surface: 'var(--cx-surface)',
          well: 'var(--cx-well)',
          band: 'var(--cx-band)',
          overlay: 'var(--cx-overlay)',
          border: 'var(--cx-border)',
          'border-soft': 'var(--cx-border-soft)',
          ink: 'var(--cx-ink)',
          'ink-2': 'var(--cx-ink-2)',
          'ink-3': 'var(--cx-ink-3)',
          'ink-4': 'var(--cx-ink-4)',
          contrast: 'var(--cx-contrast)',
          'ink-hover': 'var(--cx-ink-hover)',
          brand: 'var(--cx-brand)',
          'brand-strong': 'var(--cx-brand-strong)',
          'brand-soft': 'var(--cx-brand-soft)',
          'brand-soft-border': 'var(--cx-brand-soft-border)',
          'brand-ink': 'var(--cx-brand-ink)',
          success: 'var(--cx-success)',
          'success-soft': 'var(--cx-success-soft)',
          'success-ink': 'var(--cx-success-ink)',
          'success-border': 'var(--cx-success-border)',
          warning: 'var(--cx-warning)',
          'warning-soft': 'var(--cx-warning-soft)',
          'warning-ink': 'var(--cx-warning-ink)',
          'warning-border': 'var(--cx-warning-border)',
          danger: 'var(--cx-danger)',
          'danger-soft': 'var(--cx-danger-soft)',
          'danger-ink': 'var(--cx-danger-ink)',
          'danger-border': 'var(--cx-danger-border)',
        },
      },
      borderRadius: {
        'cx-sm': 'var(--cx-r-sm)',
        cx: 'var(--cx-r-lg)',
      },
      boxShadow: {
        cx: 'var(--cx-shadow-subtle)',
        'cx-raised': 'var(--cx-shadow-raised)',
      },
    },
  },
  plugins: [],
}
