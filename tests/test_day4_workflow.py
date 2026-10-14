import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.auth import ACTIVE_TOKENS
from app.config import settings
from app.db import fetch_alias_map, get_db, init_db
from app.main import app

client = TestClient(app)


@pytest.fixture
def workflow_context(tmp_path, monkeypatch):
    db_path = tmp_path / "day4.sqlite"
    monkeypatch.setattr(settings, "database_path", str(db_path))
    monkeypatch.setattr(settings, "debug", False)
    ACTIVE_TOKENS.clear()
    init_db(db_path)

    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO price_item
               (business_id, sku, name, unit, price_cents, category, attrs_json)
               VALUES ('biz_default', 'COP-15-ELB', '15mm Copper Elbow', 'each',
                       1850, 'fittings', '{}')"""
        )
        cursor.execute(
            """INSERT INTO price_item
               (business_id, sku, name, unit, price_cents, category, attrs_json)
               VALUES ('biz_default', 'COP-22-ELB', '22mm Copper Elbow', 'each',
                       2950, 'fittings', '{}')"""
        )
        cursor.execute("SELECT id, price_cents FROM price_item WHERE sku = 'COP-15-ELB'")
        item = cursor.fetchone()
        quote_id = "quote_day4"
        version_id = "qv_day4_1"
        line_id = "line_day4_1"
        cursor.execute(
            """INSERT INTO quote (id, business_id, number, status)
               VALUES (?, 'biz_default', 'Q-DAY4', 'draft')""",
            (quote_id,),
        )
        cursor.execute(
            """INSERT INTO quote_version
               (id, quote_id, version, subtotal_cents, vat_cents, total_cents)
               VALUES (?, ?, 1, ?, ?, ?)""",
            (version_id, quote_id, item["price_cents"], 278, item["price_cents"] + 278),
        )
        cursor.execute(
            """INSERT INTO quote_line
               (id, version_id, kind, spoken, price_item_id, quantity_milli, unit,
                unit_price_cents, match_outcome, match_score, resolved_by, note)
               VALUES (?, ?, 'part', 'copper elbow', ?, 1000, 'each', ?, 'ambiguous', 82,
                       'auto', 'Pick a size')""",
            (line_id, version_id, item["id"], item["price_cents"]),
        )
        cursor.execute(
            """INSERT INTO memo (id, business_id, quote_id, kind, status, transcript,
                                 extraction_json)
               VALUES ('memo_variation', 'biz_default', ?, 'variation', 'completed',
                       'Add another 15mm copper elbow', ?)""",
            (
                quote_id,
                json.dumps(
                    {
                        "lines": [
                            {
                                "spoken": "15mm copper elbow",
                                "kind": "part",
                                "quantity": 1,
                                "unit": "each",
                            }
                        ]
                    }
                ),
            ),
        )

    login = client.post("/api/auth/login", json={"pin": settings.auth_pin})
    assert login.status_code == 200
    return {
        "db_path": db_path,
        "headers": {"Authorization": f"Bearer {login.json()['token']}"},
        "quote_id": quote_id,
        "version_id": version_id,
        "line_id": line_id,
        "item_id": item["id"],
        "price_cents": item["price_cents"],
    }


def test_review_edit_recalculates_totals_and_audits(workflow_context):
    context = workflow_context
    response = client.patch(
        f"/api/quotes/{context['quote_id']}/lines/{context['line_id']}",
        json={"price_item_id": context["item_id"], "quantity_milli": 2000},
        headers=context["headers"],
    )
    assert response.status_code == 200
    assert response.json()["subtotal_cents"] == context["price_cents"] * 2
    assert response.json()["vat_cents"] == 555
    assert response.json()["total_cents"] == 4255

    with get_db(context["db_path"]) as conn:
        line = conn.execute(
            "SELECT quantity_milli, unit_price_cents, match_outcome, match_score, resolved_by "
            "FROM quote_line WHERE id = ?",
            (context["line_id"],),
        ).fetchone()
        assert tuple(line) == (2000, context["price_cents"], "confident", 100.0, "user")
        events = conn.execute(
            "SELECT event, payload_json FROM audit_log WHERE entity = 'quote_line' "
            "AND entity_id = ?",
            (context["line_id"],),
        ).fetchall()
        assert any(row["event"] == "user_override" for row in events)
    audit = client.get(
        "/api/audit",
        params={"quote_id": context["quote_id"]},
        headers=context["headers"],
    )
    assert audit.status_code == 200
    assert any(
        event["entity"] == "quote_line" and event["event"] == "user_override"
        for event in audit.json()
    )


def test_review_can_fetch_short_candidate_list(workflow_context):
    context = workflow_context
    response = client.get(
        f"/api/quotes/{context['quote_id']}/lines/{context['line_id']}/candidates",
        headers=context["headers"],
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["outcome"] == "ambiguous"
    assert {candidate["sku"] for candidate in payload["candidates"]} == {
        "COP-15-ELB",
        "COP-22-ELB",
    }


def test_review_of_sent_quote_creates_new_immutable_version(workflow_context):
    context = workflow_context
    with get_db(context["db_path"]) as conn:
        conn.execute(
            "UPDATE quote SET status = 'sent' WHERE id = ?",
            (context["quote_id"],),
        )
        conn.execute(
            "UPDATE quote_version SET sent_at = CURRENT_TIMESTAMP WHERE id = ?",
            (context["version_id"],),
        )

    response = client.patch(
        f"/api/quotes/{context['quote_id']}/lines/{context['line_id']}",
        json={"quantity_milli": 2000},
        headers=context["headers"],
    )
    assert response.status_code == 200
    assert response.json()["version"] == 2

    with get_db(context["db_path"]) as conn:
        old_line = conn.execute(
            "SELECT quantity_milli FROM quote_line WHERE id = ?",
            (context["line_id"],),
        ).fetchone()
        versions = conn.execute(
            "SELECT version, sent_at FROM quote_version WHERE quote_id = ? ORDER BY version",
            (context["quote_id"],),
        ).fetchall()
        assert old_line["quantity_milli"] == 1000
        assert versions[0]["sent_at"] is not None
        assert [version["version"] for version in versions] == [1, 2]


def test_variation_is_linked_priced_and_approved_with_audit(workflow_context):
    context = workflow_context
    with get_db(context["db_path"]) as conn:
        conn.execute(
            "UPDATE quote SET status = 'sent' WHERE id = ?",
            (context["quote_id"],),
        )
        conn.execute(
            "UPDATE quote_version SET sent_at = CURRENT_TIMESTAMP WHERE id = ?",
            (context["version_id"],),
        )
    create = client.post(
        f"/api/quotes/{context['quote_id']}/variations",
        json={
            "memo_id": "memo_variation",
            "based_on_version": 1,
            "lines": [
                {
                    "spoken": "15mm copper elbow",
                    "kind": "part",
                    "price_item_id": context["item_id"],
                    "quantity_milli": 1000,
                }
            ],
        },
        headers=context["headers"],
    )
    assert create.status_code == 201
    variation_id = create.json()["variation_id"]
    assert create.json()["subtotal_cents"] == context["price_cents"]
    assert create.json()["vat_cents"] == 278
    assert create.json()["total_cents"] == 2128

    approve = client.post(
        f"/api/variations/{variation_id}/approve",
        json={"approver_name": "Sam Plumber"},
        headers=context["headers"],
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"
    details = client.get(
        f"/api/variations/{variation_id}",
        headers=context["headers"],
    )
    assert details.status_code == 200
    assert details.json()["variation"]["memo_id"] == "memo_variation"
    pdf = client.get(
        f"/api/variations/{variation_id}/pdf",
        headers=context["headers"],
    )
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")

    with get_db(context["db_path"]) as conn:
        variation = conn.execute(
            "SELECT business_id, based_on_version, status, approved_by_name, approved_at "
            "FROM variation WHERE id = ?",
            (variation_id,),
        ).fetchone()
        line = conn.execute(
            "SELECT unit_price_cents, quantity_milli FROM variation_line WHERE variation_id = ?",
            (variation_id,),
        ).fetchone()
        assert variation["business_id"] == "biz_default"
        assert variation["based_on_version"] == 1
        assert variation["status"] == "approved"
        assert variation["approved_by_name"] == "Sam Plumber"
        assert variation["approved_at"]
        assert line["unit_price_cents"] == context["price_cents"]
        assert line["quantity_milli"] == 1000
        audit_events = conn.execute(
            "SELECT event FROM audit_log WHERE entity = 'variation' AND entity_id = ?",
            (variation_id,),
        ).fetchall()
        assert {row["event"] for row in audit_events} >= {"created", "approved"}


def test_learn_from_correction_saves_alias_without_changing_price(workflow_context):
    context = workflow_context
    original_price = context["price_cents"]
    response = client.patch(
        f"/api/quotes/{context['quote_id']}/lines/{context['line_id']}",
        json={
            "price_item_id": context["item_id"],
            "quantity_milli": 1000,
            "alias_phrase": "my copper bend",
        },
        headers=context["headers"],
    )
    assert response.status_code == 200

    with get_db(context["db_path"]) as conn:
        alias = conn.execute(
            "SELECT business_id, phrase, price_item_id, source FROM alias WHERE phrase = ?",
            ("my copper bend",),
        ).fetchone()
        item = conn.execute(
            "SELECT price_cents FROM price_item WHERE id = ?",
            (context["item_id"],),
        ).fetchone()
        aliases = fetch_alias_map(conn)
        assert tuple(alias) == ("biz_default", "my copper bend", context["item_id"], "learned")
        assert aliases["my copper bend"] == "15mm Copper Elbow"
        assert item["price_cents"] == original_price
        conn.execute(
            "UPDATE quote_line SET spoken = 'my copper bend' WHERE id = ?",
            (context["line_id"],),
        )

    candidates = client.get(
        f"/api/quotes/{context['quote_id']}/lines/{context['line_id']}/candidates",
        headers=context["headers"],
    )
    assert candidates.status_code == 200
    assert candidates.json()["outcome"] == "confident"
    assert candidates.json()["candidates"][0]["price_item_id"] == context["item_id"]


def test_corrections_cannot_supply_money_or_redirect_existing_alias(workflow_context):
    context = workflow_context
    money = client.patch(
        f"/api/quotes/{context['quote_id']}/lines/{context['line_id']}",
        json={"unit_price_cents": 1},
        headers=context["headers"],
    )
    assert money.status_code == 422

    with get_db(context["db_path"]) as conn:
        conn.execute(
            """INSERT INTO price_item
               (business_id, sku, name, unit, price_cents, category, attrs_json)
               VALUES ('biz_default', 'COP-22-ELB', '22mm Copper Elbow', 'each',
                       2950, 'fittings', '{}')"""
        )
        other_item = conn.execute("SELECT id FROM price_item WHERE sku = 'COP-22-ELB'").fetchone()[
            "id"
        ]
        conn.execute(
            """INSERT INTO alias (business_id, phrase, price_item_id, source)
               VALUES ('biz_default', 'my copper bend', ?, 'learned')""",
            (context["item_id"],),
        )

    redirect = client.patch(
        f"/api/quotes/{context['quote_id']}/lines/{context['line_id']}",
        json={
            "price_item_id": other_item,
            "alias_phrase": "my copper bend",
        },
        headers=context["headers"],
    )
    assert redirect.status_code == 409


def test_review_cannot_select_another_business_price_item(workflow_context):
    context = workflow_context
    with get_db(context["db_path"]) as conn:
        conn.execute(
            """INSERT INTO business
               (id, name, currency, vat_rate_bp, locale)
               VALUES ('biz_other', 'Other Business', 'GBP', 2000, 'en-GB')"""
        )
        conn.execute(
            """INSERT INTO price_item
               (business_id, sku, name, unit, price_cents, category, attrs_json)
               VALUES ('biz_other', 'OTHER-ELB', '15mm Copper Elbow', 'each',
                       9999, 'fittings', '{}')"""
        )
        other_item_id = conn.execute(
            "SELECT id FROM price_item WHERE sku = 'OTHER-ELB'"
        ).fetchone()["id"]

    response = client.patch(
        f"/api/quotes/{context['quote_id']}/lines/{context['line_id']}",
        json={"price_item_id": other_item_id},
        headers=context["headers"],
    )
    assert response.status_code == 422


def test_review_rejects_labour_item_for_part_line(workflow_context):
    context = workflow_context
    with get_db(context["db_path"]) as conn:
        conn.execute(
            """INSERT INTO price_item
               (business_id, sku, name, unit, price_cents, category, attrs_json)
               VALUES ('biz_default', 'LABOUR-1H', 'Plumbing Labour', 'hours',
                       65000, 'labour', '{}')"""
        )
        labour_item_id = conn.execute(
            "SELECT id FROM price_item WHERE sku = 'LABOUR-1H'"
        ).fetchone()["id"]

    response = client.patch(
        f"/api/quotes/{context['quote_id']}/lines/{context['line_id']}",
        json={"price_item_id": labour_item_id},
        headers=context["headers"],
    )
    assert response.status_code == 422


def test_alias_can_be_reviewed_and_removed_with_audit(workflow_context):
    context = workflow_context
    created = client.post(
        "/api/aliases",
        json={"phrase": "odd elbow name", "price_item_id": context["item_id"]},
        headers=context["headers"],
    )
    assert created.status_code == 201
    alias_id = created.json()["id"]
    listed = client.get("/api/aliases", headers=context["headers"])
    assert any(alias["id"] == alias_id for alias in listed.json())

    deleted = client.delete(f"/api/aliases/{alias_id}", headers=context["headers"])
    assert deleted.status_code == 200
    with get_db(context["db_path"]) as conn:
        events = conn.execute(
            "SELECT event FROM audit_log WHERE entity = 'alias' AND entity_id = ?",
            (str(alias_id),),
        ).fetchall()
    assert {row["event"] for row in events} == {"saved", "deleted"}


def test_variation_requires_quote_memo_and_rejects_currency(workflow_context):
    context = workflow_context
    response = client.post(
        f"/api/quotes/{context['quote_id']}/variations",
        json={
            "memo_id": "memo_variation",
            "based_on_version": 1,
            "lines": [
                {
                    "spoken": "15mm elbow R20",
                    "kind": "part",
                    "price_item_id": context["item_id"],
                    "quantity_milli": 1000,
                }
            ],
        },
        headers=context["headers"],
    )
    assert response.status_code == 422


def test_existing_variation_table_is_migrated(tmp_path):
    db_path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE variation (
                id TEXT PRIMARY KEY,
                quote_id TEXT NOT NULL,
                based_on_version INTEGER NOT NULL,
                number TEXT NOT NULL,
                status TEXT NOT NULL,
                approved_by_name TEXT,
                approved_at TIMESTAMP
            )"""
        )
        conn.execute(
            """INSERT INTO variation
               (id, quote_id, based_on_version, number, status)
               VALUES ('legacy', 'q1', 1, 'Q1-V1', 'pending')"""
        )

    init_db(db_path)
    with get_db(db_path) as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(variation)").fetchall()}
        legacy = conn.execute(
            "SELECT id, subtotal_cents, total_cents FROM variation WHERE id = 'legacy'"
        ).fetchone()
    assert {"business_id", "memo_id", "subtotal_cents", "vat_cents", "total_cents"} <= columns
    assert tuple(legacy) == ("legacy", 0, 0)
