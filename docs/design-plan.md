# docs/design-plan.md

## Design Plan: TalkQuote Field App & Showcase

### 1. Palette (6 named hex values)
- **Galvanised (`#D5DADE`)** — Borders, dividers, panels
- **Cold-line blue (`#1C57F2`)** — Primary actions, active states, pipe stroke
- **Hot-line red (`#D93A2B`)** — Flags / no-match destructive alerts
- **Hi-vis yellow (`#FFD60A`)** — Ambiguous flags (paired with dark slate text)
- **Teflon (`#F6F8F9`)** — Page background (high contrast under sunlight)
- **Slate ink (`#14222E`)** — Primary text and headers

### 2. Typography
- **Display:** Bricolage Grotesque (self-hosted via `@fontsource`)
- **Body / Mono:** Instrument Sans + `font-variant-numeric: tabular-nums` for all prices and quantities.

### 3. Surfaces & Layout
- **Showcase (`/showcase`):** Editorial, expressive. GSAP waveform draws itself as a pipe run, dropping line items at 90° elbows.
- **Field App (`/app`):** Quiet, high contrast, <300ms feedback, 48px touch targets, AA contrast. No Lenis in field app.
