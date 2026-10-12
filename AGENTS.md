# AGENTS.md

Read `PLAN.md` first. §§2, 3, 17 are non-negotiable — stop and ask on conflict. Log uncovered choices in `DECISIONS.md` (one line).

## State
- Pre-scaffold: only `PLAN.md` exists. No code, no `Makefile`/`pyproject`/`package.json`, no git, no CI. Scaffold per `PLAN.md §13` before feature work (`app/`, `web/`, `eval/`, `tests/`, `templates/`, `data/`, `docs/`).
- Planned stack: Python 3.12 + FastAPI + uvicorn, faster-whisper, Ollama (4–8B, temp 0, thinking off), Pydantic v2, RapidFuzz + regex + alias, SQLite WAL + SQLite worker (no Celery/Redis), Jinja2 + WeasyPrint, React + TS + Vite PWA. Leave out LangChain/agents/vector DBs.

## Hard bans
- LLM schema is `spoken/kind/quantity/quantity_vague/unit/refers_to_previous/customer/site` only — never `price/cost/amount/total/currency`. Guard-test it; reject currency symbols (retry once, then flag).
- Money: integer cents / `Decimal`, qty as integer thousandths. `line_total=round_half_up(qty×unit_price)`, `subtotal=sum`, `vat=round_half_up(subtotal×vat_rate_bp/10000)`. Snapshot `unit_price_cents` on line. VAT/currency config-only. Never floats.
- No network calls in pipeline (ASR→extract→match→price→PDF); no CDN — bundle + precache all fonts/assets. Synthetic data only; gitignore audio/DBs; raw audio deleted by default; never invent metrics — use `TODO(measure)`.
- Sent quotes immutable → new `quote_version`; variations link to version; every decision in `audit_log`. Keep `business_id` on all tables; PIN/token auth from start.
- No new dep without `DEPENDENCIES.md` entry (license + reason). State licenses honestly (open-source vs open-weight); verify GSAP / React Bits / model weights upstream.

## Commands (planned, not yet scaffolded)
- `docker compose up` (`app` + `ollama`) runs everything; FastAPI serves Vite build. `make test` / `make eval` / `make demo` per `PLAN.md §§6,12,15`.
- CI per PR: unit + no-network (`pytest-socket`) + schema-guard + matcher eval on typed phrases (no audio). Full audio eval locally only.

## Matching
- Two stages: regex attribute parse (eliminate conflicts) → RapidFuzz + alias table (e.g. `geezer→geyser`). Outcomes: `confident` (single survivor >`MIN_SCORE` + margin >`MIN_MARGIN`), `ambiguous`, `no-match` — never guess. `MIN_*` in config, tuned on `confident-wrong rate` (~0 target). Tests-first for `match.py`/`pricing.py`; cover traps in `PLAN.md §8` (15/22mm, 1.5/2.5mm², vague qty, labour-vs-part, `same as Smith job`→flag, off-list).

## UI
- Write `docs/design-plan.md` + self-review before UI code. Two surfaces: `/showcase` (GSAP+Lenis+React Bits, one hero pipe-run + one pinned explainer) vs `/app` PWA (quiet, <300ms feedback only, no Lenis, ~200KB gzip, 48px targets, AA, `tabular-nums`). Naming single-source: `app/config.py:APP_NAME` + `web/src/brand.ts`. React Bits: copy-paste used comps only. Lenis showcase-only + `data-lenis-prevent`; `gsap.matchMedia` reduced-motion everywhere; self-host fonts via `@fontsource`.

## Gotchas
- Mic needs HTTPS/`localhost`; offline demo = phone+laptop on hotspot with no upstream; iOS PWA must be installed or storage evicted; test iPhone MP4/AAC + Chrome WebM/Opus (ffmpeg→16kHz mono); WeasyPrint needs Pango in Dockerfile; `initial_prompt` ~224-token cap (common items) + `hotwords` for rare; IndexedDB queue must show "N waiting"; scrub PII in Sentry `before_send`.
