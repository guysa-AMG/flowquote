import pytest
from fastapi.testclient import TestClient

from app.auth import ACTIVE_TOKENS
from app.config import settings
from app.db import get_db, init_db
from app.main import app

client = TestClient(app)


@pytest.fixture
def authenticated_api(tmp_path, monkeypatch):
    db_path = tmp_path / "frontend-api.sqlite"
    monkeypatch.setattr(settings, "database_path", str(db_path))
    monkeypatch.setattr(settings, "auth_pin", "1234")
    ACTIVE_TOKENS.clear()
    init_db(db_path)
    login = client.post("/api/auth/login", json={"pin": "1234"})
    assert login.status_code == 200
    return {"db_path": db_path, "headers": {"Authorization": f"Bearer {login.json()['token']}"}}


def test_pin_change_is_authenticated_persisted_and_audited(authenticated_api):
    headers = authenticated_api["headers"]

    response = client.post(
        "/api/auth/pin",
        json={"current_pin": "1234", "new_pin": "2580"},
        headers=headers,
    )

    assert response.status_code == 200
    assert client.post("/api/auth/login", json={"pin": "1234"}).status_code == 401
    assert client.post("/api/auth/login", json={"pin": "2580"}).status_code == 200
    with get_db(authenticated_api["db_path"]) as conn:
        event = conn.execute(
            "SELECT event FROM audit_log WHERE entity = 'auth' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        stored_hash = conn.execute(
            "SELECT pin_hash FROM auth_pin_setting WHERE business_id = 'biz_default'"
        ).fetchone()["pin_hash"]
    assert event["event"] == "pin_changed"
    assert stored_hash != "2580"
    assert stored_hash.startswith("pbkdf2_sha256$")


def test_pin_change_rejects_incorrect_current_pin(authenticated_api):
    response = client.post(
        "/api/auth/pin",
        json={"current_pin": "0000", "new_pin": "2580"},
        headers=authenticated_api["headers"],
    )

    assert response.status_code == 401
    assert client.post("/api/auth/login", json={"pin": "1234"}).status_code == 200


def test_login_requires_a_configured_bootstrap_pin(authenticated_api, monkeypatch):
    monkeypatch.setattr(settings, "auth_pin", "")
    response = client.post("/api/auth/login", json={"pin": "1234"})

    assert response.status_code == 503


def test_price_list_api_lists_and_imports_integer_cent_items(authenticated_api):
    headers = authenticated_api["headers"]
    initial = client.get("/api/pricelist", headers=headers)
    assert initial.status_code == 200

    response = client.post(
        "/api/pricelist/import",
        files={
            "file": (
                "items.csv",
                b'sku,name,unit,price_cents,category,attrs_json\n'
                b'CUSTOM-1,Test washer,each,1250,fittings,"{""size_mm"":15}"\n',
                "text/csv",
            )
        },
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == {"imported": 1}
    items = client.get("/api/pricelist", headers=headers).json()
    item = next(row for row in items if row["sku"] == "CUSTOM-1")
    assert item["price_cents"] == 1250
    assert item["attrs"] == {"size_mm": 15}


def test_quote_history_returns_latest_version_total(authenticated_api):
    db_path = authenticated_api["db_path"]
    with get_db(db_path) as conn:
        conn.execute(
            """INSERT INTO quote (id, business_id, number, customer_name, site_address, status)
               VALUES ('history_q', 'biz_default', 'Q-HISTORY', 'Synthetic Client',
                       '1 Sample Road', 'draft')"""
        )
        conn.execute(
            """INSERT INTO quote_version
               (id, quote_id, version, subtotal_cents, vat_cents, total_cents)
               VALUES ('history_v1', 'history_q', 1, 1000, 150, 1150)"""
        )
        conn.execute(
            """INSERT INTO quote_version
               (id, quote_id, version, subtotal_cents, vat_cents, total_cents)
               VALUES ('history_v2', 'history_q', 2, 1200, 180, 1380)"""
        )

    response = client.get("/api/quotes", headers=authenticated_api["headers"])

    assert response.status_code == 200
    quote = next(row for row in response.json() if row["id"] == "history_q")
    assert quote["customer_name"] == "Synthetic Client"
    assert quote["site_address"] == "1 Sample Road"
    assert quote["total_cents"] == 1380
    assert quote["currency"] == "ZAR"


def test_memo_upload_persists_customer_and_variation_context(authenticated_api):
    headers = authenticated_api["headers"]
    with get_db(authenticated_api["db_path"]) as conn:
        conn.execute(
            """INSERT INTO quote (id, business_id, number, status)
               VALUES ('variation_q', 'biz_default', 'Q-VAR', 'sent')"""
        )
        conn.execute(
            """INSERT INTO quote_version
               (id, quote_id, version, subtotal_cents, vat_cents, total_cents, sent_at)
               VALUES ('variation_v1', 'variation_q', 1, 1000, 150, 1150, CURRENT_TIMESTAMP)"""
        )

    quote_response = client.post(
        "/api/memos",
        data={"kind": "quote", "customer_name": "  Test Client ", "site_address": "  2 Road "},
        files={"file": ("memo.txt", b"15mm copper elbow")},
        headers=headers,
    )
    assert quote_response.status_code == 200
    with get_db(authenticated_api["db_path"]) as conn:
        quote_memo = conn.execute(
            "SELECT customer_name, site_address FROM memo WHERE id = ?",
            (quote_response.json()["memo_id"],),
        ).fetchone()
    assert quote_memo["customer_name"] == "Test Client"
    assert quote_memo["site_address"] == "2 Road"

    variation_response = client.post(
        "/api/memos",
        data={
            "kind": "variation",
            "quote_id": "variation_q",
            "based_on_version": "1",
        },
        files={"file": ("variation.txt", b"add one 15mm elbow")},
        headers=headers,
    )
    assert variation_response.status_code == 200
    with get_db(authenticated_api["db_path"]) as conn:
        variation_memo = conn.execute(
            "SELECT quote_id, kind, based_on_version FROM memo WHERE id = ?",
            (variation_response.json()["memo_id"],),
        ).fetchone()
    assert variation_memo["quote_id"] == "variation_q"
    assert variation_memo["kind"] == "variation"
    assert variation_memo["based_on_version"] == 1
