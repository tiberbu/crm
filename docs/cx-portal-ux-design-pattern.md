# CX Portal UX Design Pattern

This pattern guides future customer experience screens for Kenyan health facility owners across the signed-in facility portal, identity onboarding, and network opt-in enrollment. Keep workflows calm, direct, mobile-friendly, and trustworthy. Partner-specific enrollment may retain its light surface and network branding; use the same restrained glass treatment and interaction rules.

## Navigation and page frame

- Keep the global header for page search, account identity, and system context. Do not put workflow actions such as adding a facility or buying tokens in the header.
- Use the sidebar on desktop and the bottom tab bar on mobile for product navigation. Do not repeat navigation destinations in the avatar menu.
- Keep the account menu to account identity, one Account settings destination, and Sign out.
- Give each page one clear heading and one primary task. Place actions beside the content they change.

## Actions and selection

- Name an action for what it actually does. “Find facilities in Registry” must open registry discovery; “Add facility” must open the add/link flow.
- Require a facility choice before an action that changes one facility. Avoid ambiguous global purchases when several facilities are linked.
- Do not show checkboxes, filters, or controls unless their result is available to the user. Keep row actions to the common next step; put secondary tools in facility details.
- Keep search scope honest in its label and placeholder. Search only fields that are actually indexed.
- In the local portfolio and Ctrl+K, search facility names only. Keep MFL, FID, and registration-number lookup inside Health Facility Registry discovery, where the identifier type is explicit.
- Adding a facility must resolve a six-digit Partner ID to its network. An empty Partner ID uses the configured default; show that behavior beside the field before the user submits.
- Open a facility into a dedicated single-facility view. Bring its identity, network, invoices, payment history, orders, and HMIS implementation status together on that page.

## Trust and data meaning

- Show “On file” when an ID is stored. Use “Verified” only when an authoritative verification result exists. Never infer verification from the presence of a value.
- Treat the user profile as the single source of truth for the owner’s National ID. Do not choose an identity from an arbitrary facility deal.
- Mask personal identifiers by default. Documentation and mock data must use masked placeholders, never real National IDs.
- Do not claim token balances predict patient visits without a validated conversion model. Do not label a package “Most Popular” without current, supported evidence.
- Show the source-backed package catalog and avoid feature matrices built from stale hardcoded tiers.

## States and recovery

- Every registry lookup has loading, result, no-result, and error states that stay visible in the page. Explain the next useful action, such as searching by MFL code or reviewing the profile ID.
- Use specific outcomes: “Found 3 facilities,” “No facilities found,” or a clear error. Avoid success styling for an action that only began or for data that is merely present.
- Preserve user input after recoverable errors and provide a direct retry or fallback path.

## Visual and interaction style

- Use a restrained glass surface for app chrome and overlays, over a quiet solid canvas. Keep content panels readable and opaque enough for contrast. Glass is a material treatment, not a reason to blur every card.
- Use a compact type scale, generous spacing around primary tasks, clear hierarchy, and consistent corner radii. Reserve strong color for primary actions, payment, and meaningful status.
- Keep motion short and purposeful. Respect reduced-motion preferences.
- Make dialogs keyboard-usable: labelled title, initial focus, Escape to close, contained Tab focus, and focus restored to the opener.
- Use native controls for selections. A facility card may have a generous click target, but keyboard and assistive technology users must have an actual checkbox or button.
- Use plain language familiar to Kenyan facility owners. Prefer KES, M-Pesa, MFL, and KEPH labels where they help complete the task; explain unfamiliar abbreviations at first use.
- Call provisioning routes through the HIE APISIX gateway using the configured HIE base URL and Bearer JWT. Do not expose setup-host credentials to the browser.
- Show deployment status and progress only from the HMIS setup service. Do not imply a draft setup has been deployed. The current status contract does not report service-unit inventory; display “Not reported” until that contract supplies it.
- On mobile, keep actions reachable, avoid dense filter rows, and ensure tables have a card or responsive alternative.

## Review checklist

Before shipping a new portal workflow, confirm that its action lives beside the affected content, its labels match behavior, every visible control works, sensitive data is masked, statuses are evidence-based, and loading/empty/error states point to a next step. Review the flow at mobile width and with keyboard navigation.
