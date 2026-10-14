from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_login_returns_token():
    response = client.post("/api/auth/login", json={"pin": "1234"})
    assert response.status_code == 200
    payload = response.json()
    assert "token" in payload
    assert payload["token"]


def test_protected_memo_route_requires_token():
    response = client.post("/api/memos", files={"file": ("memo.txt", b"15mm copper elbow")})
    assert response.status_code == 401


def test_protected_memo_route_accepts_valid_token():
    login = client.post("/api/auth/login", json={"pin": "1234"})
    token = login.json()["token"]
    response = client.post(
        "/api/memos",
        files={"file": ("memo.txt", b"15mm copper elbow")},
        data={"kind": "quote"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["memo_id"].startswith("memo_")
    assert payload["job_id"].startswith("job_")
    assert payload["status"] == "queued"
