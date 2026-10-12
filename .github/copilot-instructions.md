# GitHub Copilot Instructions

Read `PLAN.md` first. §§2, 3, 17 are non-negotiable — stop and ask on conflict. Log uncovered choices in `DECISIONS.md` (one line).

Key constraints to enforce in every suggestion:
- LLM schema: only `spoken/kind/quantity/quantity_vague/unit/refers_to_previous/customer/site` — never `price/cost/amount/total/currency`
- Money: integer cents / `Decimal`, qty as integer thousandths, `round_half_up` everywhere, VAT/currency config-only
- No network in pipeline (ASR→extract→match→price→PDF); no CDN; synthetic data only; gitignore audio/DBs
- Matcher 3 outcomes: `confident` (single survivor >MIN_SCORE + margin >MIN_MARGIN), `ambiguous`, `no-match` — never guess
- Sent quotes immutable → new `quote_version`; variations link to version; every decision in `audit_log`
- Tests-first for `match.py`/`pricing.py`; cover traps in `PLAN.md §8`
- No new dep without `DEPENDENCIES.md` entry (license + reason)

Stack: Python 3.12/FastAPI/uvicorn, faster-whisper, Ollama (4–8B, temp 0), Pydantic v2, RapidFuzz+regex+alias, SQLite WAL+worker, Jinja2+WeasyPrint, React+TS+Vite PWA.