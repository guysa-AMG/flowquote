"""SQLite database connection and schema management.

Rules (PLAN.md §3, §9):
- SQLite in WAL mode.
- business_id on every table for multi-tenant readiness.
- Sent quote versions are immutable.
- Everything audited.
"""
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Generator
from app.config import settings

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS business (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'ZAR',
    vat_rate_bp INTEGER NOT NULL DEFAULT 1500,
    locale TEXT NOT NULL DEFAULT 'en-ZA',
    audio_retention INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS price_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id TEXT NOT NULL,
    sku TEXT NOT NULL,
    name TEXT NOT NULL,
    unit TEXT NOT NULL,
    price_cents INTEGER NOT NULL,
    category TEXT NOT NULL,
    attrs_json TEXT DEFAULT '{}',
    active INTEGER NOT NULL DEFAULT 1,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (business_id) REFERENCES business (id)
);

CREATE TABLE IF NOT EXISTS alias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id TEXT NOT NULL,
    phrase TEXT NOT NULL,
    price_item_id INTEGER NOT NULL,
    source TEXT NOT NULL CHECK(source IN ('seed', 'learned')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (business_id) REFERENCES business (id),
    FOREIGN KEY (price_item_id) REFERENCES price_item (id)
);

CREATE TABLE IF NOT EXISTS memo (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    quote_id TEXT,
    kind TEXT NOT NULL CHECK(kind IN ('quote', 'variation')),
    audio_hash TEXT,
    status TEXT NOT NULL DEFAULT 'uploaded',
    transcript TEXT,
    extraction_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    audio_deleted_at TIMESTAMP,
    FOREIGN KEY (business_id) REFERENCES business (id)
);

CREATE TABLE IF NOT EXISTS job (
    id TEXT PRIMARY KEY,
    memo_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('queued', 'processing', 'completed', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (memo_id) REFERENCES memo (id)
);

CREATE TABLE IF NOT EXISTS quote (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    number TEXT NOT NULL,
    customer_name TEXT,
    site_address TEXT,
    status TEXT NOT NULL CHECK(status IN ('draft', 'sent', 'accepted')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (business_id) REFERENCES business (id)
);

CREATE TABLE IF NOT EXISTS quote_version (
    id TEXT PRIMARY KEY,
    quote_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    subtotal_cents INTEGER NOT NULL,
    vat_cents INTEGER NOT NULL,
    total_cents INTEGER NOT NULL,
    sent_at TIMESTAMP,
    FOREIGN KEY (quote_id) REFERENCES quote (id)
);

CREATE TABLE IF NOT EXISTS variation (
    id TEXT PRIMARY KEY,
    quote_id TEXT NOT NULL,
    based_on_version INTEGER NOT NULL,
    number TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected')),
    approved_by_name TEXT,
    approved_at TIMESTAMP,
    FOREIGN KEY (quote_id) REFERENCES quote (id)
);

CREATE TABLE IF NOT EXISTS quote_line (
    id TEXT PRIMARY KEY,
    version_id TEXT NOT NULL,
    variation_id TEXT,
    kind TEXT NOT NULL,
    spoken TEXT NOT NULL,
    price_item_id INTEGER,
    quantity_milli INTEGER NOT NULL,
    unit TEXT,
    unit_price_cents INTEGER NOT NULL,
    match_outcome TEXT NOT NULL,
    match_score REAL NOT NULL,
    resolved_by TEXT NOT NULL CHECK(resolved_by IN ('auto', 'user')),
    note TEXT,
    FOREIGN KEY (version_id) REFERENCES quote_version (id),
    FOREIGN KEY (variation_id) REFERENCES variation (id),
    FOREIGN KEY (price_item_id) REFERENCES price_item (id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    business_id TEXT NOT NULL,
    entity TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    event TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    actor TEXT NOT NULL,
    FOREIGN KEY (business_id) REFERENCES business (id)
);

CREATE INDEX IF NOT EXISTS idx_price_item_biz ON price_item(business_id);
CREATE INDEX IF NOT EXISTS idx_alias_phrase ON alias(phrase);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity, entity_id);
"""

def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = db_path or settings.database_path
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

@contextmanager
def get_db(db_path: str | Path | None = None) -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db(db_path: str | Path | None = None) -> None:
    with get_db(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        # Seed default business if none exists
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM business WHERE id = 'biz_default'")
        if not cursor.fetchone():
            cursor.execute(
                """INSERT INTO business (id, name, currency, vat_rate_bp, locale)
                   VALUES ('biz_default', 'Default Plumbing Co', ?, ?, 'en-ZA')""",
                (settings.default_currency, settings.default_vat_rate_bp),
            )
