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
- **Scale:** Display 32px/28px/24px, Body 16px, Small 14px, Caption 12px
- **Line length:** ≤80 characters

### 3. Design Principles
1. **Quiet when sure, loud when not** — Confident lines are plain. Only exceptions get color. Ambiguous = hi-vis yellow, no-match = hot red. Never rely on color alone: pair with icon + text label.
2. **Ground in the trade** — Visual language from plumbing: duplicate job pads, pipe runs, fittings, tape measures, hi-vis gear. Not generic SaaS.
3. **One bold moment** — Spend expressiveness on the showcase hero (waveform→pipe-run). Field app is calm, fast, legible.
4. **Offline-first reality** — No CDN, all assets precached. Works on a hotspot with no upstream.
5. **Accessibility by default** — WCAG AA, 48px touch targets, visible focus, `prefers-reduced-motion` respected everywhere.

### 4. Layout Concept (ASCII Wireframes)

#### Field App — Record Screen
```
┌─────────────────────────────────────┐
│  TalkQuote          [Settings]      │  ← Header (48px)
├─────────────────────────────────────┤
│                                     │
│   Smith, 14 Oak Rd                  │  ← Customer/site (editable)
│                                     │
│         ◉  RECORDING                │  ← Big record button (80px)
│       00:23  ~~~~~~~~~~             │  ← Live waveform + timer
│                                     │
├─────────────────────────────────────┤
│  ⚠ 3 memos waiting to sync          │  ← Offline queue indicator
└─────────────────────────────────────┘
```

#### Field App — Review Screen
```
┌─────────────────────────────────────┐
│  Review Quote          [Back]       │
├─────────────────────────────────────┤
│ "Replaced the geyser element,       │  ← Transcript snippet
│  two hours, new thermostat..."      │
├─────────────────────────────────────┤
│ ✓ Geyser element 3kW      R 320.00  │  ← Confident (green check)
│ ⚠ Thermostat      pick 1 of 2       │  ← Ambiguous (hi-vis yellow)
│ ✗ "ball thing"     no match         │  ← No-match (hot red)
├─────────────────────────────────────┤
│ Subtotal:            R 1,227.75     │  ← Tabular nums
│ VAT (15%):             R 184.16     │
│ Total:               R 1,411.91     │
├─────────────────────────────────────┤
│ [Approve] disabled until resolved  │  ← Primary action
└─────────────────────────────────────┘
```

#### Field App — Quote PDF Preview
```
┌─────────────────────────────────────┐
│  TalkQuote          QUOTE Q-A1B2C3  │
│  Licensed Plumbing                  │
├─────────────────────────────────────┤
│ Client: Mr Smith                    │
│ Site: 14 Oak Road                   │
├─────────────────────────────────────┤
│ Description              Qty  Total │
│ ─────────────────────────────────── │
│ Geyser element 3kW        1  320.00 │
│ Plumbing Labour (hrs)     2  1,300.00│
│ ─────────────────────────────────── │
│ Subtotal:                    1,620.00│
│ VAT (15%):                      243.00│
│ Total:                       1,863.00│
├─────────────────────────────────────┤
│ [Share PDF]  [Add Variation]        │
└─────────────────────────────────────┘
```

#### Showcase — Hero Sequence (one bold thing)
```
┌─────────────────────────────────────┐
│  Voice becomes plumbing becomes     │  ← Headline (Bricolage Grotesque)
│  paperwork.                         │
├─────────────────────────────────────┤
│                                     │
│   ~~~~~~~~~~~~~~~~~~~~~~~~          │  ← Waveform draws as pipe run
│          │                          │     At each pause: 90° elbow
│    ┌───┘  [Geyser element 3kW]      │     Line item drops onto pad
│    │                                │
│    └─── [2 hours labour]            │
│                                     │
├─────────────────────────────────────┤
│  [Watch Demo]  [Try on .tech]       │
└─────────────────────────────────────┘
```

### 5. Motion Guidelines
- **GSAP:** All animations wrapped in `gsap.matchMedia()` with `prefers-reduced-motion` fallback (instant state change).
- **Lenis:** Showcase ONLY. `data-lenis-prevent` on inner scroll regions. Destroy on route change. Disabled under reduced motion.
- **Field App:** NO Lenis. Only action feedback <300ms (button press, line land, flag resolve, approve).
- **React Bits:** Copy-paste only used components (animated list entry, count-up total, click-spark approve, magnetic record button, text-reveal headlines). No WebGL/particles.
- **Fonts:** Self-hosted via `@fontsource` (Bricolage Grotesque, Instrument Sans). Preloaded in HTML, precached by service worker.

### 6. Component Checklist (Field App)
- [x] Record screen: big button, live waveform, timer, offline queue badge
- [x] Review screen: transcript, line items with outcome badges, resolve flow
- [x] Quote preview: tabular nums, totals, share sheet, sent-version variation flow
- [ ] Price list: import CSV, edit, alias manager
- [ ] Quote history: list, detail, audit trail
- [ ] Settings: VAT, currency, audio retention, PIN change

### 7. Self-Review Against PLAN.md §11
| Requirement | Status | Notes |
|-------------|--------|-------|
| 4-6 named hex palette | ✅ | 6 values, trade-themed names |
| Type roles (display + body/mono) | ✅ | Bricolage + Instrument Sans |
| ASCII wireframes | ✅ | Record, Review, Quote, Showcase hero |
| Design principles | ✅ | 5 principles, trade-grounded |
| Motion budget defined | ✅ | One hero + one pinned; field <300ms |
| Reduced motion respected | ✅ | GSAP matchMedia, Lenis disabled |
| No CDN / self-host fonts | ✅ | @fontsource, precache via SW |
| 48px targets, AA contrast | ✅ | Specified in principles |
| One bold thing (pipe-run) | ✅ | Hero + showcase only |
| React Bits components listed | ✅ | 5 components, no WebGL |

### 8. Changes from Generic Defaults
- **Palette:** Avoided cream+terracotta and black+acid-green. Chose trade-metal names (Galvanised, Cold-line, Hot-line, Hi-vis, Teflon, Slate).
- **Typography:** Bricolage Grotesque (expressive, OFL) + Instrument Sans (technical, tabular-nums) instead of Inter/Roboto.
- **Layout:** Job pad metaphor, not card-based SaaS grid.
- **Motion:** Single orchestrated hero, not "fade-in-up" on every section.
- **Color semantics:** Hi-vis yellow for ambiguous (requires dark text), hot red for no-match — mirrors site safety colors.

### 9. Next Steps
1. Finish price-list editing and alias management screens.
2. Add quote detail and audit-trail views to quote history.
3. Add VAT, currency, and audio-retention settings only with corresponding validated backend APIs.
4. Verify recording on a real phone over HTTPS and rehearse the hotspot/offline demo.
