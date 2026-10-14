# DECISIONS.md

One line per choice not covered by PLAN.md. Format: `YYYY-MM-DD: <decision> — <reason>`.
2026-10-14: Remove generic seeded hour/labour aliases and flag labour with no stated rate — prevents ordinary time units from steering selection to a price tier.
2026-10-14: Day 4 tracing logs only local stage durations without transcript/customer fields; remote Sentry export is deferred because pipeline network access is prohibited.
2026-10-14: Require a private TALKQUOTE_AUTH_PIN for bootstrap and persist later PIN changes as salted PBKDF2 hashes — avoids a published default credential and keeps changes effective across restarts.
