/**
 * Return a small, human-readable signing context for internal audit review.
 *
 * The server remains the source of truth for the public IP. This browser
 * context is deliberately coarse (browser, platform, viewport, timezone) and
 * is not a device fingerprint.
 */
export function collectSigningDeviceInfo() {
  if (typeof window === 'undefined') return {}

  const nav = window.navigator ?? {}
  const screen = window.screen ?? {}
  const userAgent = nav.userAgent ?? ''
  const brands = nav.userAgentData?.brands ?? []
  const browserBrand = brands.find(
    ({ brand }) => brand && !/not a brand|chromium/i.test(brand),
  )?.brand
  const browser =
    browserBrand ||
    userAgent.match(/Edg|Firefox|OPR|Opera|Chrome|Safari|MSIE|Trident/i)?.[0] ||
    ''
  const platform =
    nav.userAgentData?.platform ||
    nav.platform ||
    (/iPhone|iPad|iPod/i.test(userAgent)
      ? 'iOS'
      : /Android/i.test(userAgent)
        ? 'Android'
        : /Mac/i.test(userAgent)
          ? 'macOS'
          : /Win/i.test(userAgent)
            ? 'Windows'
            : /Linux/i.test(userAgent)
              ? 'Linux'
              : '')
  const viewport =
    screen.width && screen.height ? `${screen.width}×${screen.height}` : ''
  let timezone = ''
  try {
    timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || ''
  } catch {
    // Some hardened browsers deny timezone access; the rest of the context is
    // still useful and signing should never fail because of audit enrichment.
  }

  return {
    device: [browser, platform, viewport, timezone]
      .filter(Boolean)
      .join(' · ')
      .slice(0, 140),
    user_agent: userAgent,
  }
}
