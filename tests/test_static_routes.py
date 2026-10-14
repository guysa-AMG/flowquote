from fastapi.testclient import TestClient

from app import main


def test_fastapi_serves_pwa_and_client_routes(tmp_path, monkeypatch):
    static_dir = tmp_path / "static"
    assets_dir = static_dir / "assets"
    assets_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("<html>TalkQuote</html>", encoding="utf-8")
    (assets_dir / "app.js").write_text("const app = true;", encoding="utf-8")
    monkeypatch.setattr(main, "WEB_BUILD_DIR", static_dir)
    client = TestClient(main.app)

    root = client.get("/")
    deep_link = client.get("/showcase/sample")
    asset = client.get("/assets/app.js")
    missing_api = client.get("/api/unknown")

    assert root.status_code == 200
    assert root.text == "<html>TalkQuote</html>"
    assert deep_link.status_code == 200
    assert deep_link.text == root.text
    assert asset.status_code == 200
    assert asset.text == "const app = true;"
    assert missing_api.status_code == 404


def test_fastapi_returns_404_when_pwa_asset_is_missing(tmp_path, monkeypatch):
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html>TalkQuote</html>", encoding="utf-8")
    monkeypatch.setattr(main, "WEB_BUILD_DIR", static_dir)
    client = TestClient(main.app)

    response = client.get("/assets/missing.js")

    assert response.status_code == 404
