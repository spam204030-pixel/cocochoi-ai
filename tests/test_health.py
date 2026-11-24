def test_api_health_returns_ok(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["message"] == "정상"


def test_home_page_shows_status(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "정상" in res.text
    assert "COCOCHOI AI CONTENT FACTORY" in res.text
