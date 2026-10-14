"""SQLite database connection and schema management.

Rules (PLAN.md §3, §9):
- SQLite in WAL mode.
- business_id on every table for multi-tenant readiness.
- Sent quote versions are immutable.
- Everything audited.
"""
import csv
import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

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

CREATE TABLE IF NOT EXISTS auth_pin_setting (
    business_id TEXT PRIMARY KEY,
    pin_hash TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (business_id) REFERENCES business (id)
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
    customer_name TEXT,
    site_address TEXT,
    based_on_version INTEGER,
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
    business_id TEXT NOT NULL,
    quote_id TEXT NOT NULL,
    memo_id TEXT NOT NULL,
    based_on_version INTEGER NOT NULL,
    number TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected')),
    approved_by_name TEXT,
    approved_at TIMESTAMP,
    subtotal_cents INTEGER NOT NULL DEFAULT 0,
    vat_cents INTEGER NOT NULL DEFAULT 0,
    total_cents INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (business_id) REFERENCES business (id),
    FOREIGN KEY (quote_id) REFERENCES quote (id),
    FOREIGN KEY (memo_id) REFERENCES memo (id)
);

CREATE TABLE IF NOT EXISTS variation_line (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    variation_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    spoken TEXT NOT NULL,
    price_item_id INTEGER,
    quantity_milli INTEGER NOT NULL,
    unit TEXT,
    unit_price_cents INTEGER NOT NULL,
    match_outcome TEXT NOT NULL,
    match_score REAL NOT NULL DEFAULT 0,
    note TEXT,
    FOREIGN KEY (business_id) REFERENCES business (id),
    FOREIGN KEY (variation_id) REFERENCES variation (id),
    FOREIGN KEY (price_item_id) REFERENCES price_item (id)
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
        _migrate_variation_schema(conn)
        _migrate_memo_metadata(conn)
        # Seed default business if none exists
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM business WHERE id = 'biz_default'")
        if not cursor.fetchone():
            cursor.execute(
                """INSERT INTO business (id, name, currency, vat_rate_bp, locale)
                   VALUES ('biz_default', 'Default Plumbing Co', ?, ?, 'en-ZA')""",
                (settings.default_currency, settings.default_vat_rate_bp),
            )
        seed_default_price_items(conn, business_id="biz_default")
        seed_default_aliases(conn, business_id="biz_default")


def _migrate_variation_schema(conn: sqlite3.Connection) -> None:
    """Add Day 4 variation fields to databases created by earlier versions."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(variation)").fetchall()}
    additions = {
        "business_id": "TEXT REFERENCES business(id)",
        "memo_id": "TEXT REFERENCES memo(id)",
        "subtotal_cents": "INTEGER NOT NULL DEFAULT 0",
        "vat_cents": "INTEGER NOT NULL DEFAULT 0",
        "total_cents": "INTEGER NOT NULL DEFAULT 0",
    }
    for name, definition in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE variation ADD COLUMN {name} {definition}")


def _migrate_memo_metadata(conn: sqlite3.Connection) -> None:
    """Add client and variation context to memos created by earlier versions."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(memo)").fetchall()}
    additions = {
        "customer_name": "TEXT",
        "site_address": "TEXT",
        "based_on_version": "INTEGER",
    }
    for name, definition in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE memo ADD COLUMN {name} {definition}")


def seed_default_price_items(conn: sqlite3.Connection, business_id: str = "biz_default") -> None:
    """Populate the default business with the sample price list if it is empty."""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM price_item WHERE business_id = ?", (business_id,))
    if cursor.fetchone()[0] > 0:
        return

    csv_path = Path(__file__).resolve().parent.parent / "data" / "pricelist.sample.csv"
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            attrs_json = row.get("attrs_json") or "{}"
            try:
                parsed_attrs = json.loads(attrs_json)
            except json.JSONDecodeError:
                parsed_attrs = {}
            cursor.execute(
                """
                INSERT INTO price_item (business_id, sku, name, unit, price_cents,
                   category, attrs_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    business_id,
                    row["sku"],
                    row["name"],
                    row["unit"],
                    int(row["price_cents"]),
                    row["category"],
                    json.dumps(parsed_attrs),
                ),
            )


def seed_default_aliases(conn: sqlite3.Connection, business_id: str = "biz_default") -> None:
    """Populate default aliases for trade slang and common speech-to-text slips.

    Only multi-word phrases are included to avoid substring matching issues.
    Single words like "labour", "hours", "element", "cable" are handled by
    the fuzzy matcher directly.
    """
    cursor = conn.cursor()
    cursor.execute(
        """DELETE FROM alias
           WHERE business_id = ? AND source = 'seed'
             AND phrase IN ('hour', 'hours', 'labour', 'labor')""",
        (business_id,),
    )
    cursor.execute("SELECT COUNT(*) FROM alias WHERE business_id = ?", (business_id,))
    if cursor.fetchone()[0] > 0:
        return

    # Map: alias phrase -> target SKU
    # Only multi-word phrases to avoid substring matching issues
    aliases = [
        # Trade slang / speech-to-text slips (multi-word)
        ("geezer", "GEY-ELM-3KW"),           # "geezer" -> geyser element (short but unique)
        ("geyser element", "GEY-ELM-3KW"),
        ("geyser element 3kw", "GEY-ELM-3KW"),
        ("geyser element 4kw", "GEY-ELM-4KW"),
        ("flanged element", "GEY-ELM-FLG"),
        ("thermostat vkf", "GEY-THM-VKF"),
        ("thermostat tsr", "GEY-THM-T10"),
        ("tp valve", "GEY-TPV-22"),
        ("temperature pressure valve", "GEY-TPV-22"),
        ("ball valve", "BRS-15-BV"),
        ("gate valve", "BRS-15-BV"),
        ("check valve", "BRS-15-CV"),
        ("pressure valve", "PRV-400-15"),
        ("waste trap", "PVC-40-TRP"),
        ("soil pipe", "PVC-110-BND"),
        ("ptfe tape", "CON-PTFE-TP"),
        ("solvent cement", "CON-SOLV-CME"),
        ("twin and earth", "CBL-1.5-TW"),
        ("isolator switch", "ISOL-30A-SW"),
        ("safety valve", "GEY-TPV-22"),
        ("drain cock", "GEY-DRN-CK"),
        ("vacuum breaker", "GEY-VAC-15"),
        # Labour variants (multi-word)
        ("standard labour", "LBR-PLM-STD"),
        ("standard labor", "LBR-PLM-STD"),
        ("after hours labour", "LBR-PLM-AFT"),
        ("after hours labor", "LBR-PLM-AFT"),
        ("overtime labour", "LBR-PLM-AFT"),
        ("overtime labor", "LBR-PLM-AFT"),
        ("overtime", "LBR-PLM-AFT"),
        # Callout variants (multi-word)
        ("callout fee", "FEE-CALLOUT"),
        ("call out fee", "FEE-CALLOUT"),
        ("diagnostic fee", "FEE-CALLOUT"),
        ("trip fee", "FEE-CALLOUT"),
        ("site visit", "FEE-CALLOUT"),
        # Copper fittings (with size)
        ("15mm copper elbow", "COP-15-ELB"),
        ("15mm copper tee", "COP-15-TEE"),
        ("15mm copper coupler", "COP-15-CPL"),
        ("15mm copper pipe", "COP-15-PIP"),
        ("22mm copper elbow", "COP-22-ELB"),
        ("22mm copper tee", "COP-22-TEE"),
        ("22mm copper coupler", "COP-22-CPL"),
        ("22mm copper pipe", "COP-22-PIP"),
        # PEX fittings (with size)
        ("15mm pex elbow", "PEX-15-ELB"),
        ("15mm pex tee", "PEX-15-TEE"),
        ("15mm pex coupler", "PEX-15-CPL"),
        ("15mm pex pipe", "PEX-15-PIP"),
        # Brass fittings (with size)
        ("15mm brass valve", "BRS-15-BV"),
        ("15mm brass check valve", "BRS-15-CV"),
        # Geyser parts (specific)
        ("geyser element 3kw", "GEY-ELM-3KW"),
        ("geyser element 4kw", "GEY-ELM-4KW"),
        # Single-word trade slang (single-pass matching prevents substring explosion).
        # Generic labour/time words stay out: they collide with quantities and rates.
        ("geezer", "GEY-ELM-3KW"),
        ("callout", "FEE-CALLOUT"),
        ("trap", "PVC-40-TRP"),
        ("tape", "CON-PTFE-TP"),
        ("glue", "CON-SOLV-CME"),
        ("cable", "CBL-1.5-TW"),
        ("switch", "ISOL-30A-SW"),
        ("element", "GEY-ELM-3KW"),
        ("anode", "GEY-ANODE-S"),
    ]

    # Build SKU -> id map
    cursor.execute("SELECT id, sku FROM price_item WHERE business_id = ?", (business_id,))
    sku_to_id = {row["sku"]: row["id"] for row in cursor.fetchall()}

    for phrase, target_sku in aliases:
        if target_sku in sku_to_id:
            cursor.execute(
                """INSERT INTO alias (business_id, phrase, price_item_id, source)
                   VALUES (?, ?, ?, 'seed')""",
                (business_id, phrase.lower(), sku_to_id[target_sku]),
            )


def fetch_price_items(conn: sqlite3.Connection, business_id: str = "biz_default") -> list[dict]:
    """Load active price items for the given business."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, sku, name, unit, price_cents, category, attrs_json
        FROM price_item WHERE business_id = ? AND active = 1
        ORDER BY name ASC
        """,
        (business_id,),
    )
    rows = cursor.fetchall()
    result: list[dict] = []
    for row in rows:
        attrs = json.loads(row["attrs_json"] or "{}")
        result.append({
            "id": row["id"],
            "sku": row["sku"],
            "name": row["name"],
            "unit": row["unit"],
            "price_cents": row["price_cents"],
            "category": row["category"],
            "attrs": attrs,
        })
    return result


def fetch_alias_map(conn: sqlite3.Connection, business_id: str = "biz_default") -> dict[str, str]:
    """Map configured aliases to canonical names for the matching pipeline."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT a.phrase, p.name
        FROM alias a
        JOIN price_item p ON p.id = a.price_item_id AND p.business_id = a.business_id
        WHERE a.business_id = ? AND p.active = 1
        ORDER BY a.id
        """,
        (business_id,),
    )
    return {row["phrase"]: row["name"] for row in cursor.fetchall()}
