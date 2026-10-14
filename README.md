# TalkQuote (working title)

Voice-to-quote for plumbers. Record a memo on site → open models extract line items → code prices from your price list → you approve a PDF quote. Mid-job extras become variation orders.

## Principles (from PLAN.md §§2,3)

- **Model extracts. Code prices. Human approves.** LLM schema has no price/cost/amount/total/currency fields.
- **No network in runtime pipeline.** Offline-first, no CDN, bundle everything.
- **Money = integer cents / Decimal.** Never floats. VAT/currency config-only.
- **Immutable sent quotes.** Edits → new version. Variations link to version. Every decision in audit log.
- **Matcher outcomes:** confident / ambiguous / no-match — never guess. Confident-wrong rate is the safety metric.

## Quickstart (once scaffolded)

Set a private four-digit PIN before starting the server. For Compose, put
`TALKQUOTE_AUTH_PIN=<your-private-four-digit-PIN>` in an untracked `.env` file.
Do not commit that file. The PIN is not shown by the login screen; it can be
changed from Settings after sign-in.

```bash
docker compose up   # app + ollama; FastAPI serves Vite build
make test           # unit + no-network + schema-guard + matcher eval (typed phrases)
make eval           # full audio eval (local only)
make demo           # demo helpers
```

## Project docs

- `PLAN.md` — full spec (read first)
- `AGENTS.md` — agent constraints (this repo)
- `DECISIONS.md` — one-line decision log
- `DEPENDENCIES.md` — license + reason per dep
- `docs/design-plan.md` — UI design review (write before UI code)

## License

TBD (permissive, per PLAN.md §15 Day 0).