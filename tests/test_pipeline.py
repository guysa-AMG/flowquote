import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from app.config import settings
from app.db import get_db, init_db
from app.extract import Extraction, SpokenLine
from app.jobs import build_quote_lines_from_extraction, process_job


def test_process_job_persists_quote_version(tmp_path):
    db_path = tmp_path / "pipeline.sqlite"
    settings.database_path = str(db_path)
    init_db(db_path)

    memo_id = "memo_test_1"
    job_id = "job_test_1"
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO memo
               (id, business_id, kind, status, transcript, customer_name, site_address)
               VALUES (?, 'biz_default', 'quote', 'queued', ?, 'Manual Client', '3 Sample Road')""",
            (memo_id, "15mm copper elbow and two hours labour"),
        )
        cursor.execute(
            "INSERT INTO job (id, memo_id, state) VALUES (?, ?, 'queued')",
            (job_id, memo_id),
        )

    # Mock the LLM extraction to return a known Extraction
    mock_extraction = Extraction(
        lines=[
            SpokenLine(spoken="15mm copper elbow", kind="part", quantity=Decimal("1"), unit="each"),
            SpokenLine(spoken="two hours labour", kind="labour", quantity=Decimal("2"), unit="hours"),
        ],
        customer_name=None,
        site_address=None,
    )

    with patch("app.jobs.extract_with_llm", new_callable=AsyncMock) as mock_extract:
        mock_extract.return_value = mock_extraction
        result = asyncio.run(process_job(job_id))

    assert result["quote_id"].startswith("quote_")
    assert result["total_cents"] > 0

    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM quote_line WHERE version_id IN (SELECT id FROM quote_version WHERE quote_id = ?)", (result["quote_id"],))
        count = cursor.fetchone()[0]
        assert count >= 2
        cursor.execute("SELECT transcript, status FROM memo WHERE id = ?", (memo_id,))
        memo = cursor.fetchone()
        assert memo["status"] == "completed"
        assert "15mm copper elbow" in memo["transcript"]
        quote = cursor.execute(
            "SELECT customer_name, site_address FROM quote WHERE id = ?",
            (result["quote_id"],),
        ).fetchone()
        assert quote["customer_name"] == "Manual Client"
        assert quote["site_address"] == "3 Sample Road"


def test_ambiguous_line_is_not_priced_until_human_resolution(tmp_path, monkeypatch):
    db_path = tmp_path / "ambiguous-pricing.sqlite"
    monkeypatch.setattr(settings, "database_path", str(db_path))
    init_db(db_path)
    extraction = Extraction(
        lines=[
            SpokenLine(
                spoken="two hours labour",
                kind="labour",
                quantity=Decimal("2"),
                unit="hours",
            )
        ],
        customer_name=None,
        site_address=None,
    )

    _, quote_lines = build_quote_lines_from_extraction(extraction)

    assert quote_lines[0]["match_outcome"] == "ambiguous"
    assert quote_lines[0]["price_item_id"] is None
    assert quote_lines[0]["unit_price_cents"] == 0
    assert quote_lines[0]["line_total_cents"] == 0


def test_vague_quantity_is_not_defaulted_or_priced(tmp_path, monkeypatch):
    db_path = tmp_path / "vague-pricing.sqlite"
    monkeypatch.setattr(settings, "database_path", str(db_path))
    init_db(db_path)
    extraction = Extraction(
        lines=[
            SpokenLine(
                spoken="some 15mm copper elbows",
                kind="part",
                quantity=Decimal("3"),
                quantity_vague=True,
                unit="each",
            )
        ],
        customer_name=None,
        site_address=None,
    )

    _, quote_lines = build_quote_lines_from_extraction(extraction)

    assert quote_lines[0]["match_outcome"] == "ambiguous"
    assert quote_lines[0]["quantity_milli"] == 0
    assert quote_lines[0]["price_item_id"] is None
    assert quote_lines[0]["unit_price_cents"] == 0
    assert quote_lines[0]["line_total_cents"] == 0


def test_variation_memo_is_extracted_without_creating_a_new_quote(tmp_path, monkeypatch):
    db_path = tmp_path / "variation-pipeline.sqlite"
    monkeypatch.setattr(settings, "database_path", str(db_path))
    init_db(db_path)
    with get_db(db_path) as conn:
        conn.execute(
            "INSERT INTO quote (id, business_id, number, status) "
            "VALUES ('base_quote', 'biz_default', 'Q-BASE', 'sent')"
        )
        conn.execute(
            """INSERT INTO quote_version
               (id, quote_id, version, subtotal_cents, vat_cents, total_cents, sent_at)
               VALUES ('base_version', 'base_quote', 1, 1000, 150, 1150, CURRENT_TIMESTAMP)"""
        )
        conn.execute(
            """INSERT INTO memo
               (id, business_id, quote_id, kind, status, transcript, based_on_version)
               VALUES ('variation_memo', 'biz_default', 'base_quote', 'variation',
                       'queued', 'add one elbow', 1)"""
        )
        conn.execute(
            "INSERT INTO job (id, memo_id, state) VALUES ('variation_job', 'variation_memo', 'queued')"
        )

    extraction = Extraction(
        lines=[
            SpokenLine(
                spoken="15mm copper elbow",
                kind="part",
                quantity=Decimal("1"),
                unit="each",
            )
        ]
    )
    with patch("app.jobs.extract_with_llm", new_callable=AsyncMock) as mock_extract:
        mock_extract.return_value = extraction
        result = asyncio.run(process_job("variation_job"))

    assert result == {
        "memo_id": "variation_memo",
        "quote_id": "base_quote",
        "kind": "variation",
    }
    with get_db(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM quote").fetchone()[0] == 1
        memo = conn.execute(
            "SELECT status, extraction_json FROM memo WHERE id = 'variation_memo'"
        ).fetchone()
        assert memo["status"] == "completed"
        assert "15mm copper elbow" in memo["extraction_json"]
