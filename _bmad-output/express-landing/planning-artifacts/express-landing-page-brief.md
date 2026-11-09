# Tiberbu Express — Landing Page Brief

**Date:** 2026-10-25
**Surface:** public `/` (`crm/www/index.html`, `crm/www/index.py`)
**Panel:** Business Analyst (Mary), UX Designer (Sally), Architect (Winston), QA (Quinn)

## 1. Outcome

A guest who lands on `/` understands two things within one screen and acts on the first:

1. **Onboard yourself and start using the platform.**
2. **Start sending SHA claims today.**

Primary action: **Start onboarding** → `/facility-onboarding`.
Secondary action: **Sign in** → `/login?redirect-to=/cx-portal`.

## 2. Rename

The customer-facing product is now **Tiberbu Express** (was "Tiberbu Customer
Experience"). User-facing copy, page titles, emails and admin labels use the new
name. Routes (`/cx-portal`), Python modules, API names and historic patch labels
keep their implementation names. Field labels created by historic patches are not
rewritten.

## 3. Competitor read (reference only)

The competitor's public page leads with a deadline countdown, a "get started"
button repeated in every section, a three-step onboarding strip, certification
proof and a pricing table.

| Keep the idea | Do differently |
|---|---|
| One goal per screen, the CTA repeated | One clear action, not five competing ones |
| Three steps, plainly named | Steps end in the outcome (a claim sent), not "register" |
| A concrete promise in the hero | No invented deadlines, timers, durations or certifications |
| Proof near the CTA | Proof = what really happens: registry checks, no signing, pay for the package you pick |

## 4. Panel decisions

- **Mary (BA):** The page sells the *result*, not the process. Hero headline is the
  two outcomes, verbatim in spirit. Every claim must be true today: no "30 minutes",
  no certification badge, no fake urgency. "Today" is the only urgency.
- **Sally (UX):** One page, five blocks: nav → hero → three steps → what you need →
  closing CTA. The hero's right side shows the journey as an "express lane" ending in
  a claim marked *Submitted*, so the outcome is visible before any reading.
  Six cards, six steps and two after-cards from the old page are cut.
- **Winston (Architect):** Stay a static Jinja page: no new bundle, no external fonts
  or scripts, brand colours from `apply_brand_context`. The guest/redirect logic and
  `cta_*` context keys stay as they are. Animation is CSS-only and switches off under
  `prefers-reduced-motion`.
- **Quinn (QA):** Gate on: CTA links resolve; one `h1`; no horizontal scroll at
  360px; readable without images; reduced-motion respected; desktop and mobile
  screenshots reviewed; old product name absent from user-facing surfaces; existing
  unit and Python tests green.
- **Open disagreement, recorded:** Mary wanted pricing on the page; Sally and Winston
  kept it off because packages are network-specific and shown inside onboarding.
  The steps block says packages and prices are shown before payment.

## 5. Copy deck

- **Eyebrow:** Self-service onboarding for health facilities
- **H1:** Onboard yourself. Start sending SHA claims today.
- **Lead:** Tiberbu Express takes your facility from registry verification to a working
  HMIS in one guided journey. No sales call, no paperwork to sign.
- **CTA:** Start onboarding · **Secondary:** Already onboarded? Sign in
- **Proof row:** Registry-verified ownership · No signatures needed · Pay only for the
  package you choose
- **Steps — "Three steps to your first claim":**
  1. Verify — confirm your identity and the facilities you own through the national registry.
  2. Choose — pick a token package sized to your claim volume; see the price and VAT before you pay.
  3. Go live — your HMIS is set up and you start sending SHA claims.
- **What you need:** ID number · access to your registered phone or email · a facility
  listed in the national registry.
- **Closing:** Your first SHA claim is one onboarding away. → Start onboarding.
  Invited by a Network? → Continue with Network Opt-In.

## 6. Acceptance criteria

1. `/` for a guest shows "Tiberbu Express" as brand and title, and the H1 above.
2. Primary CTA appears in nav, hero and closing band and links to `/facility-onboarding`.
3. Sign-in links point to `/login?redirect-to=/cx-portal`; staff access link kept in footer.
4. Logged-in users are still redirected (unchanged `index.py` logic).
5. No horizontal scroll at 360px; hero CTA visible above the fold at 390×844 and 1440×900.
6. Animations disabled under `prefers-reduced-motion: reduce`.
7. "Customer Experience" no longer appears in user-facing copy.

---

# Round 2 — features, proof, pricing and contact

**Date:** 2026-10-25 · **Trigger:** maintainer review of the first deployed version.

## Feedback

1. The hero H1 broke the www typography spec (it was 4.6rem, weight 700 and -0.05em tracking).
2. Keep the hero copy, but move the "Your express lane" card further down the page.
3. Add a hero background image showing a laptop, a tablet and a phone running the Tiberbu HIMS, with a bubbles effect. It must be approved before it goes on the page.
4. Show that Tiberbu CareVerse is DHA-certified, with a link to the public DHA registry entry.
5. Lead with features (compliance, security, modern HIMS capability, professional proof), not steps that read like documentation.
6. Add a contact-us mechanism: a form, plus at least two phone numbers.
7. Bring back a read-only pricing preview.
8. Use the Tiberbu logo from the corporate site wherever CareVerse is mentioned.

## Panel decisions

- **Mary (BA):** The DHA certificate is the strongest proof we have, and the competitor's badge was unverifiable. Ours links to the regulator's own registry, so it goes in the hero next to the promise, with the facts the registry shows: full certification, 100% field test (22 of 22 applicable cases) and the expiry date. Every feature claim comes from the public CareVerse product page; nothing is invented. She won the pricing argument from round 1: a read-only preview from the live catalogue, with no buy buttons per card.
- **Sally (UX):** Page order: hero (copy + certificate card) → proof strip → eight feature cards → express lane (moved down, with the "what you need" list folded into one sentence) → pricing → contact → closing CTA. The steps and "three things" blocks are cut because they read like documentation. The lane animation now plays when the lane scrolls into view, not on page load.
- **Winston (Architect):** The page stays static Jinja. Certificate link, ID, expiry, phone numbers, email and hours live in **CRM Opt-In Settings → Landing Page** (site data, not code), and a block hides when its field is empty. Pricing reuses `_catalog_packages()` from onboarding, so there is one source of truth; any catalogue error hides the section instead of breaking the page. Contact posts to a guest, POST-only `crm.api.landing.submit_contact`, which creates a CRM Lead (source Website, Default Lead Owner) with the message saved as an escaped FCRM Note. It is rate-limited to 5 per hour per IP and has a honeypot field.
- **Quinn (QA):** Gates: H1 ≤ 3rem at weight 600 and -0.02em; no element heavier than 600; no uppercase transforms; one h1; no horizontal scroll at 360px; hero CTA above the fold; the lane sits below the hero; the certificate link only renders when configured; contact validation, honeypot, rate limit and HTML escaping covered by tests.
- **Open item, recorded:** the HIMS shows only its sign-in screen to a visitor who isn't logged in, so the background draft shows that screen on all three devices. Screens from inside the app need a demo account. The image is not on the page until it is approved.

## Acceptance criteria (round 2)

1. H1 computes to 48px desktop / 36px mobile, weight 600, letter-spacing -0.02em.
2. The certificate card and the footer link point to the configured DHA registry entry and open in a new tab.
3. The features section covers compliance, security, interoperability, clinical, ERP, analytics, devices and support.
4. The express lane renders below the hero.
5. Pricing shows the enabled catalogue packages, read-only, with prices excluding VAT.
6. A contact message creates a Lead plus a note; invalid input is rejected; the sixth post in an hour gets a 429.
7. Two or more phone numbers render as `tel:` links when configured.

---

# Round 3 — alignment and contact

**Date:** 2026-10-25 · **Trigger:** maintainer review. The first screen did not line up with the sections below it, and the contact section needed work, starting with the contact details.

## Findings (measured with Playwright at 1440px)

- **Hero art:** it bled to the viewport edge, while every section below stopped at the 1160px container.
- **Two-column splits:** the hero, lane and contact sections used three different splits. Their text columns were 532, 552 and 449px wide, and their second columns started at 744, 780 and 669px.
- **Proof strip:** its dividers did not line up with the feature-card columns under it.
- **Headline:** "today." was left alone on its own line.
- **Spec breach:** the page re-declared blue-tinted greys (`#5f676d`, `#3f474d`, `#8b9096`) instead of the shared frappe-ui neutral tokens in `tiberbu-brand.css`.
- **QA found:**
  - The 40px nav and pricing buttons were under the 44px touch target.
  - Button shadows hid the keyboard focus ring.
  - Re-validating a field on blur shifted the layout, so the "Send message" click could miss.
  - Nav anchors landed under the sticky header.

## Panel decisions

- **Sally (UX):**
  - One layout system with tokens: `--container` 1160, `--gutter` 24/16, `--split-gap` 64, `--card-gap` 16, `--stack` 44.
  - The hero, lane and contact sections share one `.split` (two equal columns), so every second column starts on the same line.
  - The strip uses the feature grid's four columns.
  - The hero art is contained to the page width.
  - Headings use `text-wrap: balance`.
- **Mary (BA):** Contact leads with calling: one "Call us" card with both numbers as large rows, each with its own Call button and the office hours. Email comes next, then a sign-in note for existing customers. The form gains a topic so sales can triage, and each step says what happens next. Nothing is promised that we can't keep: no response-time SLA.
- **Winston (Architect):**
  - The topic is validated server-side against a fixed list and stored in the note title. Unknown values fall back to the first topic.
  - Phone numbers stay in CRM Opt-In Settings (site data).
  - The page now aliases the shared stylesheet tokens instead of declaring its own.
- **Quinn (QA):** An automated suite (`qa.cjs`, scratchpad) runs at 360 to 1920px and gates on:
  - Shared left edge, second column and right edge, strip ↔ card columns, and the art inside the container.
  - H1 at 36–48px and weight 600; nothing heavier than 600 and no uppercase.
  - WCAG AA contrast and no tinted greys.
  - 44px touch targets and a visible focus ring on every Tab stop.
  - Anchors and images resolve; no console or network errors.
  - Contact validation, focus management, success state and reduced motion.

## Acceptance criteria (round 3)

1. At ≥ 900px, all section text starts on one left edge, all second columns start on one line, and all content ends on one right edge, including the hero art.
2. Proof-strip dividers align with the feature-card columns.
3. The contact section lists both configured numbers with a Call button each; the form takes a topic and shows inline errors and a success state.
4. The QA suite passes on the dev and test sites.
