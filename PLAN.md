# PLAN.md: Voice-to-Quote for plumbers (working title: TalkQuote)

> **For the coding agent (Copilot):** read this whole file before writing code. It is the source of truth for scope, architecture, hackathon context, and design direction. Sections 2 and 3 are non-negotiable. If a task conflicts with them, stop and ask. Add a one-line note to `DECISIONS.md` whenever you make a choice this file does not cover.
>
> **Suggested wiring:** save this file as `PLAN.md` in the repo root, and add a short `AGENTS.md` (and/or `.github/copilot-instructions.md`, depending on which your Copilot client reads) that says: "Read PLAN.md first. Follow sections 2, 3, and 17."

---

## 1. Project snapshot

| Item | Value |
|---|---|
| One-liner | A plumber records a voice memo on site. Open models turn it into line items, **code** prices them from the plumber's own price list, and the plumber approves a PDF quote. Mid-job extras become priced **variation orders**, so unpaid work gets caught. |
| Target user | Independent plumbers and 2-5 person plumbing outfits who do quotes at night after a full day on site |
| Pain | Evenings lost to paperwork, plus extras done for free because writing them up is a hassle |
| Positioning (be honest) | Quoting apps with voice features already exist. This one is offline-capable, uses *their* price list, flags uncertainty instead of guessing, and captures variations. Never claim to be first. |
| Challenge | Hacktoberfest Open-Source AI Challenge, Week 2: **Side Hustle** (opened 2026-10-12) |
| Submission | DEV post using the challenge template. Tags: `devchallenge`, `hf26challenge` |
| Deadline | TBD: check the challenge page and write it here |
| Solo or team | TBD |
| Working title | **TalkQuote** (see section 14 for naming) |

### Project facts to fill in (agent: do not guess these, ask or leave TBD)

| Fact | Value |
|---|---|
| Pilot plumber(s) | TBD |
| Currency, VAT rate, units (mm/inch) | TBD (must be config, never constants) |
| Memo language(s) and accents | TBD |
| Demo hardware (CPU model, RAM, GPU?) | TBD |
| Real memos allowed for eval? | TBD |
| Domain claimed (.tech)? | TBD |

---

## 2. Core design principle (non-negotiable)

**The model extracts. Code prices. A human approves.**

1. The LLM output schema contains **only what was said**: item words, quantity, unit, kind. It has **no price, amount, cost, total, or currency field**. A model-made price error is impossible by construction. This is the headline claim of the project.
2. All money is computed in code with integer cents and a documented rounding rule (section 8).
3. Every line is one of three outcomes: **confident** (auto-filled), **ambiguous** (plumber picks from a short list), or **no match** (flagged, never guessed).
4. Nothing becomes a sent quote until the plumber approves it on the review screen.
5. The worst failure is a **confident wrong match**. It is the headline safety metric. Prefer a flag over a wrong guess every time.

## 3. Hard constraints (non-negotiable)

- **No network calls in the runtime pipeline** (ASR, extraction, matching, pricing, PDF). Add a test that runs the full pipeline with sockets disabled (e.g. `pytest-socket`). The "unplug the network" demo must be literally true.
- **No CDN assets.** Fonts, scripts, and icons are bundled and precached by the service worker.
- **No real customer data in the repo.** Synthetic or approved-and-anonymized only. `.gitignore` raw audio and local databases.
- **Raw audio is deleted after processing by default.** Keep transcripts and the audit log. Make retention a setting.
- **Money:** integer cents (or `Decimal`), never floats. VAT rate and currency are config.
- **Quotes are immutable once sent.** Edits create a new version. Variation orders link to a specific quote version.
- **Every decision is logged** (section 9, `audit_log`): transcript, raw extraction JSON, match outcome per line, every manual change, approvals.
- **Do not invent numbers.** README, post drafts, and docs report only what the eval harness or pilot measured. Use `TODO(measure)` placeholders.
- **State licenses honestly.** Say "open-source" only for OSI-licensed pieces and "open-weight" for models with custom terms. Maintain `DEPENDENCIES.md` with the license of every dependency and model, and verify against the upstream page, since licenses change.

---

## 4. Hackathon context

### 4.1 Prompt in brief
Build something with open-weight models or open-source AI at its core that someone would actually pay for. The open pieces must be what makes the project work. The post must say where the open approach beat a closed one (offline, privacy, cost, fine-tuning, no lock-in). Bonus points for landing a first user and reporting honestly on whether they paid.

### 4.2 Judging criteria (in order of weight)
1. **Writing quality** (weighted most heavily): vivid, honest, specific, with measured numbers
2. Relevance to the prompt and theme
3. Creativity
4. Technical execution
5. Use of partner technology (optional)

**Prize:** $250 USD + DEV++ membership. Partner categories are extra.

### 4.3 Submission template headings (the post must use these)
`What I Built` · `Demo` · `Code` · `How I Built It` · `Why Does Open Innovation Matter?` · `My Agent Session` (optional, judges like it) · `My First User` (optional, bonus) · `Prize Categories`

For team submissions, one member publishes and credits teammates by DEV username in the body.

### 4.4 Partner prize categories: decisions

| Category | Prize | Decision | Plan |
|---|---|---|---|
| **Gemma** | $200 | **Enter** | Use a Gemma model as one of the extraction LLMs in the comparison table. Check its current license and describe it accurately. |
| **Tinker** (Thinking Machines) | $200 | **Enter, behind a decision gate** | Fine-tune a small model for memo-to-JSON extraction and show a clear gain in latency or cost vs. a baseline. **Gate: run the untuned baseline on day 3. If schema-constrained decoding already gives near-perfect extraction, drop Tinker.** Also confirm trained weights can be exported and run locally. |
| **GitHub Copilot** | $100 | **Enter** | The project is built with Copilot. Keep evidence: agent sessions, PR reviews, and a GitHub Actions workflow that runs tests and the matcher eval. |
| **Entire** | $100 | **Enter** | Share agent sessions in the post. Capture sessions from day 1. |
| **Sentry** (Agent Tracing) | $100 | **Enter** | Trace each pipeline stage with latency and token counts. **Scrub customer names and addresses** (`before_send`) or self-host, and say so. |
| **.tech Domain** | $100 | **Enter** | Showcase site and read-only sample-quote demo on the claimed domain. The real product runs locally; label the site as a showcase. |
| Temporal | $100 | Skip (stretch only) | Adds infrastructure to a design that wins by being simple. The SQLite job worker is enough. |
| Render / DigitalOcean | $200 | Skip | Hosting the core demo there would undercut the offline claim. A hosted comparison run is the most to consider. |
| Backboard | $100 | Skip | Sending data to a hosted API conflicts with the local story. Synthetic memos only, if ever. |
| ElevenLabs | $100 | Skip | Cloud transcription contradicts "nothing leaves the machine". Narration for the demo video is the only harmless use. |
| Mastra, MongoDB, Tiger Data, TabPFN, SerpApi, Arduino | n/a | Skip | The pipeline is fixed and SQLite is enough. No fit. |

Only list categories in the post that were **genuinely used**.

---

## 5. Architecture

```
Phone (React PWA)                        Local server (laptop / mini-PC / van box)
┌───────────────────┐   audio upload    ┌──────────────────────────────────────────┐
│ Record screen     │ ───────────────►  │ FastAPI                                  │
│ IndexedDB queue   │                   │  ├─ ffmpeg → 16 kHz mono WAV             │
│ Review & resolve  │ ◄───── status ─── │  ├─ faster-whisper (hotwords from list)  │
│ PDF share         │                   │  ├─ Ollama LLM (JSON schema, temp 0)     │
└───────────────────┘                   │  ├─ matcher (attributes + RapidFuzz)     │
                                        │  ├─ pricing (integer cents, VAT)         │
                                        │  ├─ PDF (Jinja2 + WeasyPrint)            │
                                        │  └─ SQLite (price list, quotes, audit)   │
                                        └──────────────────────────────────────────┘
```

### Where inference runs (decision)
**Option A with Option C's queue.** Models run on a local server. The phone is a thin client that records, queues, displays, and shares. If the server is unreachable, recordings queue in IndexedDB and sync when back in range. State this honestly in the post: "no internet required" is true; "works anywhere with no connection to anything" is not. On-device inference (whisper.cpp / llama.cpp on the phone) is roadmap only.

### Deployment tiers
Demo on a laptop; real use on a mini-PC in the van or shop; hosted GPU box as a later option (loses the offline claim, keeps open-model control and cost). Ship as `docker compose up` with services `app` and `ollama`.

### Pipeline per memo
`upload → job queued → normalize audio → transcribe → extract JSON → validate against schema → match each line → persist draft lines with outcomes → plumber reviews → approve → totals + PDF → audit`

---

## 6. Tech stack

### Backend
| Layer | Choice | Notes |
|---|---|---|
| Language / API | Python 3.12, FastAPI, uvicorn | |
| Speech-to-text | faster-whisper (`large-v3-turbo`, or `small` on weak CPUs) | Use `initial_prompt` (about 224-token cap) for common items, `hotwords` for rarer terms, VAD filter on |
| Extraction LLM | 4B-8B model via Ollama, 4-bit, **temperature 0, thinking off** | Use Ollama structured outputs with the Pydantic JSON schema. Compare a Qwen3-class and a Gemma-class model; verify current versions and licenses on the model cards |
| Schema | Pydantic v2 | One schema for LLM output format and validation |
| Matching | SQLite + RapidFuzz + regex attribute parser + alias table | Embeddings only if eval shows lexical matching missing synonyms |
| Money | integer cents / `Decimal` | |
| PDF | Jinja2 + WeasyPrint | Needs Pango system libs: pin in Dockerfile |
| Storage | SQLite (WAL mode) | Single file, works offline |
| Jobs | SQLite-backed worker loop | No Celery, no Redis |
| Tracing | `sentry-sdk` spans per stage | Scrub PII |
| Tooling | uv, ffmpeg, pytest, ruff, Makefile | `make eval`, `make test`, `make demo` |

Leave out: LangChain, agent frameworks, vector databases. The pipeline is a fixed sequence of plain functions.

### Frontend (updated: React + Vite)
| Layer | Choice | Notes |
|---|---|---|
| Framework | React + TypeScript + Vite | Built output is served by FastAPI, so one `docker compose up` runs everything |
| PWA | `vite-plugin-pwa` (Workbox) | Precache **all** assets including fonts and animation libs |
| Offline queue | IndexedDB (e.g. `idb`) | Visible "3 memos waiting to sync" state. Never lose a recording silently |
| Recording | `MediaRecorder`, Screen Wake Lock, visible timer | Mic needs HTTPS or localhost |
| Sharing | Web Share API for the PDF | Lets the plumber send via WhatsApp or email |
| Styling | Tailwind + design tokens as CSS variables | React Bits ships Tailwind variants |
| Animation | **GSAP** (+ ScrollTrigger), **Lenis**, selected **React Bits** components | Rules in section 11 |
| Data fetching | TanStack Query | Polling or SSE for job status |

Desktop: the same web app, responsive. No Tauri or Electron. The price-list editor, alias manager, and quote history are better on a big screen, so make those pages responsive too.

---

## 7. The extraction schema

```python
# app/extract.py: the LLM may only say what was said. There is NO price field.
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field

class SpokenLine(BaseModel):
    spoken: str = Field(description="The item exactly as the plumber said it")
    kind: Literal["part", "labour", "callout", "other"]
    quantity: Decimal | None = Field(None, description="Numeric quantity if stated")
    quantity_vague: bool = Field(False, description="True for 'a couple', 'a few', 'some'")
    unit: str | None = None          # each, m, hours, ...
    refers_to_previous: str | None = None   # e.g. "the Smith job"

class Extraction(BaseModel):
    lines: list[SpokenLine]
    customer_name: str | None = None
    site_address: str | None = None
```

**Schema guard test (required):** assert the generated JSON schema contains no property whose name includes `price`, `cost`, `amount`, `total`, or `currency`, and that any model output containing a currency symbol in a value is rejected and retried once, then flagged.

Prompt rules: say only what was said, do not infer items not mentioned, do not guess quantities, mark vague quantities with `quantity_vague`, never add prices.

---

## 8. Matcher and pricing spec

### Matching, two stages
1. **Attribute parsing in code.** Regexes extract size (mm/inch), material (copper, PEX, PVC...), type (elbow, tee, coupler...), rating, thread, and similar from both the spoken phrase and each price-list entry. A candidate that **conflicts** with an attribute the plumber stated is eliminated.
2. **Ranking.** RapidFuzz scores the survivors, with an **alias table** for trade slang and recurring Whisper errors (e.g. "geezer" to geyser).

### Outcomes
| Outcome | Rule |
|---|---|
| **Confident** | Exactly one survivor, score above `MIN_SCORE`, and margin over runner-up above `MIN_MARGIN` |
| **Ambiguous** | Several survivors, **or** an unstated attribute that differs among survivors (e.g. "copper elbow" with both 15 mm and 22 mm in the list). The plumber picks from a short list |
| **No match** | Nothing above `MIN_SCORE`. Flagged, never guessed |

`MIN_SCORE` and `MIN_MARGIN` live in config and are tuned against the **confident-wrong rate** on the eval set, not by feel. Also check **unit compatibility** (labour in hours must not match a part sold per metre).

### Known traps (write tests for each)
- 15 mm vs 22 mm copper; 1.5 mm² vs 2.5 mm² cable (plausible-looking near-duplicates)
- "A couple of elbows" (vague quantity: flag the quantity, not the item)
- "Two hours" (labour vs. a part)
- "Same as the Smith job" (`refers_to_previous` becomes a flag until history lookup exists)
- Whisper mangling brand names and trade vocabulary
- Items in the memo that are not in the price list

### Pricing rules
- `unit_price_cents` is **snapshotted onto the line** when the quote is created, so later price-list edits do not change old quotes.
- Quantities are stored as integer thousandths (supports 1.5 hours).
- `line_total = round_half_up(quantity × unit_price)` per line. `subtotal = sum(lines)`. `vat = round_half_up(subtotal × vat_rate_bp / 10000)`. Document this rule in the PDF footer and the README.
- Price correctness on matched lines is **100% by construction**. State it plainly and test it.

---

## 9. Data model (SQLite)

| Table | Key columns |
|---|---|
| `business` | id, name, currency, vat_rate_bp, locale, audio_retention |
| `price_item` | id, business_id, sku, name, unit, price_cents, category, attrs_json, active, updated_at |
| `alias` | id, business_id, phrase, price_item_id, source (`seed`, `learned`), created_at |
| `memo` | id, business_id, quote_id?, kind (`quote`, `variation`), audio_hash, status, transcript, extraction_json, created_at, audio_deleted_at |
| `job` | id, memo_id, state, attempts, error, updated_at |
| `quote` | id, business_id, number, customer_name, site_address, status (`draft`, `sent`, `accepted`), created_at |
| `quote_version` | id, quote_id, version, subtotal_cents, vat_cents, total_cents, sent_at |
| `quote_line` | id, version_id, variation_id?, kind, spoken, price_item_id?, quantity_milli, unit, unit_price_cents, match_outcome, match_score, resolved_by (`auto`, `user`), note |
| `variation` | id, quote_id, based_on_version, number, status, approved_by_name, approved_at |
| `audit_log` | id, ts, business_id, entity, entity_id, event, payload_json, actor |

Keep `business_id` on every table so multi-user is not a rewrite. One tenant is fine for now. Access: PIN or token login from the start, since the server is reachable on a local network.

---

## 10. API (FastAPI)

| Endpoint | Purpose |
|---|---|
| `POST /api/auth/login` | PIN to token |
| `POST /api/memos` | Upload audio (multipart), optional `quote_id`, `kind`. Returns `memo_id`, `job_id` |
| `GET /api/jobs/{id}` (and `/events` SSE) | Pipeline status |
| `GET /api/memos/{id}` | Transcript, lines with outcomes and candidates |
| `PATCH /api/quotes/{id}/lines/{line_id}` | Resolve a flag or edit a line (audited) |
| `POST /api/quotes/{id}/send` | Finalize a version, generate PDF |
| `GET /api/quotes/{id}/pdf` | Download PDF |
| `POST /api/quotes/{id}/variations` | Create a variation from a memo |
| `POST /api/variations/{id}/approve` | Record typed name and timestamp |
| `POST /api/pricelist/import` | CSV with column-mapping preview |
| `GET/POST/DELETE /api/aliases` | Manage aliases |
| `GET /api/audit?quote_id=` | Decision trail |
| `GET /api/system` | Models loaded, offline status, version |
| `GET /healthz` | Liveness |

---

## 11. UI and design direction

> **Agent process (required):** before building any UI, write a short design plan in `docs/design-plan.md` (palette as 4-6 named hex values, type roles, a layout concept with ASCII wireframes, and principles). Then review it against this brief. If any part reads like a generic default you would produce for any quoting app, revise it and note what you changed. Only then write code.

### 11.1 Goal
The UI must stand out in a screenshot grid of hackathon entries, **without** slowing down a plumber with wet hands in a dim van. So: a distinctive **showcase site** with a bold orchestrated moment, and a **field app** that is calm, fast, and legible. Spend the boldness in one place.

### 11.2 Two surfaces

| Surface | Audience | Personality | Motion |
|---|---|---|---|
| **Showcase site** (`/showcase`, deployed to the .tech domain, no real backend) | Judges, readers, prospective plumbers | Expressive, editorial, memorable | GSAP + Lenis + React Bits, one hero sequence and one scroll-pinned explainer |
| **Field app** (`/app`, PWA, behind PIN) | The plumber | Quiet, high-contrast, large targets | Only motion that **answers an action** (record, line lands, flag resolves, approve) |

### 11.3 Design concept: "the job pad"
Ground the design in the trade, not in generic SaaS: duplicate job pads, pipe runs, fittings, tape measures, hi-vis gear.

- **Memorable element (the one bold thing):** the voice memo's **waveform draws itself as a pipe run**. At each pause the pipe makes a clean 90° elbow and **drops a line item onto the pad**. Talk becomes plumbing becomes paperwork. This is the hero on the showcase site and a smaller version of it plays on the field app's processing screen.
- **Principle: quiet when sure, loud when not.** Confident lines are plain. Only exceptions get color. Ambiguous = hi-vis yellow, no match = hot red. Never rely on color alone: pair with an icon and a text label.

### 11.4 Starting tokens (proposal: revise in the design review)
Deliberately avoids the cream-plus-terracotta and black-plus-acid-green defaults.

| Token | Hex | Role |
|---|---|---|
| Galvanised | `#D5DADE` | Borders, panels, dividers |
| Cold-line blue | `#1C57F2` | Primary actions, links, pipe-run stroke |
| Hot-line red | `#D93A2B` | No-match flags, destructive actions |
| Hi-vis yellow | `#FFD60A` | Ambiguous flags (use dark text on it) |
| Teflon | `#F6F8F9` | Page background |
| Slate ink | `#14222E` | Text |

Provide a dark theme via the same tokens, but default to the high-contrast light theme for glare on site.

**Type:** one expressive display family (e.g. Bricolage Grotesque) plus one clearly distinct body family (e.g. Instrument Sans). Both are open (OFL) and must be **self-hosted** (e.g. via `@fontsource`) for offline use. Use `font-variant-numeric: tabular-nums` for all money. Line length under 80 characters. Final choices are the agent's to confirm in the design review.

### 11.5 Screens (field app)

```
RECORD                         REVIEW                          QUOTE
┌──────────────────────┐      ┌──────────────────────────┐    ┌──────────────────────┐
│ Smith, 14 Oak Rd     │      │ "Replaced the geyser     │    │ Quote 0042 · v1      │
│                      │      │  element, two hours..."  │    │ Customer, site       │
│      ◉  (big)        │      │ ──────────────────────── │    │ ──────────────────── │
│   00:23  ~~~~~~~~    │      │ Geyser element 1   R...  │    │ lines (aligned nums) │
│                      │      │ ⚠ Thermostat  pick 1 of 2│    │ Subtotal / VAT       │
│ 3 memos waiting to   │      │ ✕ "ball thing"  no match │    │ Total                │
│ sync                 │      │ [Approve] disabled until │    │ [Share PDF] [Add     │
└──────────────────────┘      │ all flags resolved       │    │  variation]          │
                              └──────────────────────────┘    └──────────────────────┘
```

Other screens: price list (import, edit, aliases), quote history, audit trail per quote, settings (VAT, currency, audio retention, PIN).

### 11.6 Library rules

**GSAP**
- Use `gsap.matchMedia()` so every animation has a `prefers-reduced-motion` alternative (instant state change, no scroll hijack).
- The pipe-run draw can use DrawSVG/MotionPath if available in the free tier, otherwise plain SVG `stroke-dashoffset` driven by GSAP. Check the current GSAP license and plugin availability before relying on either.
- Kill timelines and ScrollTriggers on unmount.

**Lenis**
- **Showcase site only.** Do not use smooth-scroll hijacking in the field app: it fights native scrolling in lists, sheets, and iOS PWAs.
- Standard integration: Lenis scroll event calls `ScrollTrigger.update`, Lenis `raf` runs from `gsap.ticker`, and `gsap.ticker.lagSmoothing(0)`.
- Put `data-lenis-prevent` on inner scrollable regions (tables, code blocks). Destroy the instance on route change. Disable under reduced motion.

**React Bits**
- Copy in **only** the components actually used (it is copy-paste, not a dependency). Check each component's own dependencies: some pull in WebGL or other libs. List what you used in `DEPENDENCIES.md`.
- Good candidates (verify names against the current library): an animated list for line items entering, a count-up for the total, a click-spark for the Approve confirmation, a magnetic effect on the record button, a text-reveal for showcase headlines.
- **Avoid** heavy WebGL or particle backgrounds. They read as generic, drain phone batteries, and hurt the offline-first story.
- **License check before shipping:** I believe React Bits uses MIT with a Commons Clause, which can restrict selling software built substantially on it. Verify on its repo before relying on it in something people pay for. Be ready to replace those pieces with your own GSAP code.

**General**
- Motion budget: no fade-and-slide-up on every section, no hover animation on every card. One orchestrated hero moment and one pinned explainer on the showcase site. In the field app, only action feedback, under about 300 ms.
- Targets (set and measure, do not assume): field-app initial JS around 200 KB gzip or less, Lighthouse PWA checks passing, 48 px minimum touch targets, WCAG AA contrast, visible keyboard focus.
- Test on a real mid-range Android phone and a real iPhone, not only desktop.
- Copy: plain verbs, sentence case, errors say what happened and how to fix it. Button and toast use the same verb ("Approve" then "Approved"). Empty states invite the next action.

---

## 12. Evaluation (reproducible; `make eval`)

**Test set:** 60-100 memos with ground-truth line items. Best source: a real plumber re-telling about 20 past jobs, compared against invoices they actually sent. Fill the rest with your own recordings (noise, accents, mixed-language phrasing). Write `eval/truth.jsonl`. **Never train on the eval set.**

| Metric | Why |
|---|---|
| Item recall and precision | Caught what was said, nothing extra |
| Quantity accuracy | Where most extraction errors hide |
| **Confident-wrong rate** (report with line count) | The safety number, target as close to 0 as possible |
| Flag rate | Too high is annoying, too low hides doubt |
| Price correctness on matched lines | 100% by construction; test and state it |
| End-to-end latency per memo (CPU) | Usability |
| Time to a sendable quote vs. the plumber's current method | The business metric |
| Word error rate, with and without hotword biasing | The open-model advantage, shown as a chart |

**Comparisons (one table):**
- Whisper sizes
- 2-3 open LLMs (Qwen-class, Gemma-class, optionally the fine-tuned small model)
- **Baseline:** LLM-only pricing, where the model produces prices itself. If it makes price errors and this design does not, the data argues for the architecture
- Variation orders: a few scripted mid-job scenarios checked end to end

**CI (GitHub Actions):** run unit tests, the no-network test, the schema guard test, and the matcher eval on typed phrases (no audio needed) on every PR. Full audio eval runs locally via `make eval`.

---

## 13. Repo layout

```
talkquote/
├── PLAN.md  AGENTS.md  DECISIONS.md  DEPENDENCIES.md  README.md
├── docker-compose.yml  Dockerfile  Makefile
├── app/
│   ├── main.py  config.py
│   ├── asr.py  extract.py  match.py  pricing.py  pdf.py  audit.py
│   ├── jobs.py  db.py  auth.py
├── data/
│   └── pricelist.sample.csv        # ~40 plumbing items incl. 15/22 mm near-duplicates
├── templates/  quote.html  variation.html
├── web/                            # React + Vite PWA
│   └── src/  app/ (field app)  showcase/  components/  brand.ts  tokens.css
├── eval/  audio/ (gitignored)  truth.jsonl  run_eval.py
├── tests/  test_match.py  test_pricing.py  test_schema_guard.py  test_no_network.py
├── docs/  design-plan.md  post-draft.md  demo-script.md
└── .github/  workflows/ci.yml  copilot-instructions.md
```

---

## 14. Naming

The name is undecided. Keep it in **one place** so renaming is trivial: `app/config.py` (`APP_NAME`) and `web/src/brand.ts`. Never hardcode it elsewhere.

Candidates to consider (check availability, including the free .tech domain):
- **Rough-in**: a real plumbing term for the first-fix stage; fits "first-pass quote"
- **Jobpad**: matches the job-pad design concept
- **Tallyhand**
- **Quotewise**
- **Bendline**: ties to the pipe-elbow animation
- **TalkQuote**: working title, descriptive but plain

Pick a name that is short, speakable on a phone call, and works as a .tech domain.

---

## 15. Build plan

### Day 0, before coding
- [ ] Create repo, license (permissive), `PLAN.md`, `AGENTS.md`, `DECISIONS.md`, `DEPENDENCIES.md`
- [ ] **Start plumber outreach now** (longest lead time). Ask to use real approved job notes. Ask for a commitment, not a compliment
- [ ] Claim the .tech domain at hacktoberfest.com/my/promos
- [ ] Start saving agent sessions (Entire and/or DevRelay) from the first prompt
- [ ] Test mic over HTTPS (`mkcert` or Caddy) on a real phone, and test the hotspot/offline setup

### Day 1: matcher first (testable with typed phrases, no audio)
- [ ] `pricelist.sample.csv` (about 40 items with 15/22 mm traps) and import
- [ ] `match.py` with attribute parser, aliases, three outcomes, and tests for every known trap
- [ ] `pricing.py` with integer-cent rules and tests, `audit.py`
- [ ] Tune `MIN_SCORE` / `MIN_MARGIN` against typed phrases

### Day 2: extraction and PDF
- [ ] Pydantic schema, schema guard test, Ollama structured-output call
- [ ] End-to-end CLI: typed text to extraction to match to PDF
- [ ] `quote.html` template and WeasyPrint output, Dockerfile, `docker compose up`
- [ ] No-network test passing

### Day 3: audio, API, app shell
- [ ] ffmpeg normalize, faster-whisper with hotwords, job worker, API endpoints
- [ ] React shell: PIN login, record screen, IndexedDB queue, offline indicator
- [ ] **Tinker gate:** run the untuned baseline now. Decide go or drop
- [ ] Design plan written and reviewed (`docs/design-plan.md`)

### Day 4: review flow and variations
- [ ] Review screen with flag resolution, quote preview, Web Share PDF
- [ ] Variation orders: memo, priced lines, linked PDF, typed-name approval, audit entry
- [ ] Learn-from-corrections: resolving a flag can save an **alias** (never a price)
- [ ] Record the eval memos, write `truth.jsonl`, add Sentry spans

### Day 5: measure and fix
- [ ] Run `make eval`: baselines, model comparison, hotword on/off
- [ ] Fix what the confident-wrong cases reveal
- [ ] Showcase site: hero pipe-run sequence, pinned explainer, sample read-only quote
- [ ] Optional: Tinker fine-tune if the gate said go

### Day 6: pilot and polish
- [ ] Put it in a real plumber's hands (shadow mode: they compare to their normal method)
- [ ] Record: quotes sent, corrections per quote, variations captured, time saved, price they would accept, whether they keep it on
- [ ] Rehearse the offline demo on hotspot. Record the demo video with the network visibly unplugged

### Day 7: write
- [ ] Post draft to final. Lead with the "model never outputs a price" decision, then the eval table, then the pilot
- [ ] Screenshots, eval chart, architecture diagram, session embeds
- [ ] Verify licenses in `DEPENDENCIES.md`, then publish

### If behind, cut in this order
**P0 (never cut):** matcher, pricing, extraction, PDF, review screen, eval harness, offline demo.
**P1:** variation orders, Gemma/Qwen comparison, Sentry, showcase site.
**P2:** Tinker fine-tune, learn-from-corrections, fancy motion.
**P3 (roadmap only):** everything in section 16.

---

## 16. Possible later features (to strengthen the entry, ranked)

| Feature | Value to the entry | Effort | Notes |
|---|---|---|---|
| **Learn-from-corrections** (bounded aliases) | High | Low | A resolved flag saves an alias, never a price. Measure the drop in flags with a chronological held-out replay |
| **Data-plate photo reader** | High (great demo) | Medium | A vision model reads the geyser's model and serial number to disambiguate parts. Strong because it attacks the hardest problem with a second signal |
| **"Same as the Smith job"** history lookup | Medium-High | Medium | Index past quotes so references resolve instead of flagging |
| **Supplier till-slip scan + margin alert** | High (money story) | Medium | OCR or vision updates costs, and warns "15 mm copper is up 12%, margin on open quotes shrank". Moves the pitch from saved time to protected margin |
| **Fine-tuned small extractor** (Tinker) | High if the gate passes | Medium | A tuned 1B-4B model matching an untuned 8B on CPU is a clear latency and cost win |
| **Hands-free read-back** | Medium | Low-Med | Local TTS reads parsed lines aloud so the plumber can confirm without looking |
| **Voice price-list edits** | Medium | Low | "22 mm copper elbow is now eighteen" updates the list, with confirmation |
| **Customer approval link** | Medium | High | Public quote page with an Accept button. Needs hosting or a tunnel, which conflicts with the offline claim, so keep it optional |
| **Invoice conversion, deposits, payment status** | Medium | Medium | Turns quotes into the full admin loop |
| **Accounting CSV export** | Low-Med | Low | Xero/QuickBooks-style import files |
| **Other trade packs** (HVAC, solar, electrical) | Medium | Low | Price list plus alias set plus eval pack. Shows the approach generalizes |
| **Multilingual / code-switched memos** | Medium | Medium | A real advantage of controllable open ASR. Needs an eval set per language |
| **On-device inference** | High wow, high risk | High | whisper.cpp WASM or React Native with on-device bindings. Keep a server fallback so a demo cannot fail |
| **Whisper fine-tune on trade vocabulary** | Medium | High | Only if hotword biasing leaves meaningful word-error-rate gaps |

---

## 17. Agent working rules

1. **Tests first** for `match.py` and `pricing.py`. Every known trap in section 8 gets a test before the code that handles it.
2. **Small commits and PRs**, each referencing a checklist item in section 15. Keep PRs reviewable.
3. **No new dependency** without adding it to `DEPENDENCIES.md` with its license and a one-line reason.
4. **Never add a network call** to the runtime pipeline. Never add a CDN link.
5. **Never put a price, amount, or currency field in the LLM schema.**
6. **Never use floats for money.**
7. **Ask before** changing sections 2 or 3, adding a feature from section 16, or choosing between two reasonable architectures. Log the answer in `DECISIONS.md`.
8. **No invented data.** No fabricated metrics, user quotes, or benchmark results in any file. Use `TODO(measure)`.
9. **Synthetic data only** in the repo. Audio and databases are gitignored.
10. **Trace and log as you build**, not at the end: Sentry spans per stage and an audit entry for every decision.
11. **Respect reduced motion** and the offline requirement in every UI change.
12. After each milestone, update the checkboxes in this file.

---

## 18. Demo script (about 90 seconds)

1. Open the app on a phone. Record a memo ("replaced the geyser element, two hours, new thermostat, call-out fee"). **Unplug the network** (hotspot with no upstream).
2. The pipe-run animation plays as the transcript appears, then line items land. One line is flagged yellow: "Thermostat: 2 matches, pick one."
3. Resolve the flag. The PDF quote appears. Share it via the share sheet.
4. The client asks for an extra. Record a 10-second memo. A variation order appears attached to the quote, with an approval line.
5. Show the audit trail for the quote, then the eval table with the **confident-wrong count**.

---

## 19. Post outline (maps to the DEV template)

- **What I Built:** open with a plumber at 9 pm doing paperwork. One vivid scene. Then one paragraph on who pays and why.
- **Demo:** the video, network visibly unplugged. Link the showcase site on the .tech domain and say it is a showcase.
- **Code:** embed the GitHub repo.
- **How I Built It:** pipeline diagram, the extraction schema, and the "model never outputs a price" decision. Then the matcher's three outcomes.
- **Why Open Innovation Matters:** offline operation, hotword biasing and optional fine-tuning on trade vocabulary, no per-memo fees, data stays on the plumber's machine, swap models with one config line (prove it with the comparison table). Be candid about where open models are weaker.
- **My Agent Session:** embedded or linked sessions.
- **My First User:** pilot behavior, sample size (say n plainly), what they corrected, what they asked for next, and what price they would accept. Remove this section if there is no real user.
- **Prize Categories:** only those genuinely used.
- **Limits:** small pilot, clean price list required, which trades and languages were tested, license caveats.

Writing is weighted most. Prefer one concrete measured before-and-after to any amount of architecture description.

---

## 20. Risks (priority order) and gotchas

**Risks**
1. **Confident-wrong matches.** Mitigation: attribute parsing, thresholds tuned on the metric, flags, and the metric as the headline.
2. **Unproven willingness to pay.** Mitigation: outreach on day 0, ask for commitments, track behavior over opinions.
3. **Scope creep.** One trade, one channel, one price-list format. Everything else is roadmap.
4. **Fancy UI eating the schedule.** The animation is one moment, not a system. Cut P2 first.
5. **License ambiguity** (GSAP, React Bits, model weights). Verify and state honestly.

**Gotchas**
- Mic access needs HTTPS or localhost. Test on a real phone on day 0.
- For the offline demo, phone and laptop share a hotspot or local router with no upstream internet.
- iOS Safari records MP4/AAC and Chrome records WebM/Opus. ffmpeg normalizes both, but test a real iPhone.
- iOS can evict storage for sites not installed to the home screen. Install the PWA before relying on the offline queue.
- WeasyPrint needs Pango system libraries. Pin them in the Dockerfile.
- Benchmark an 8B model on CPU early. Drop to 4B if end-to-end time exceeds about 10 seconds.
- `initial_prompt` is limited to roughly 224 tokens. Put common items there and rarer terms in `hotwords`.
- Reasoning-style models can spend tokens "thinking". Turn thinking off for extraction.
- Lenis and inner scroll regions: use `data-lenis-prevent`, and keep Lenis off the field app.
- Trace data can contain customer names. Scrub before sending to Sentry.
- A messy price list degrades matching. The import step needs column mapping and a validation report.
