from app.core.errors import ERRORS, ErrorCode


def test_every_error_code_has_korean_message():
    for code in ErrorCode:
        info = ERRORS[code]
        assert info.message and info.action
        assert any("가" <= ch <= "힣" for ch in info.message)


def test_unknown_page_shows_korean_error_screen(client):
    res = client.get("/없는페이지")
    assert res.status_code == 404
    assert "text/html" in res.headers["content-type"]
    assert "찾는 페이지나 자료가 없습니다" in res.text
    assert "처음 화면으로" in res.text


def test_unknown_api_returns_json_error(client):
    res = client.get("/api/없는주소")
    assert res.status_code == 404
    err = res.json()["error"]
    assert err["code"] == "NOT_FOUND"
    assert err["message"] and err["action"]


def test_app_error_uses_its_code_and_message(client):
    res = client.get("/api/_test/app-error")
    assert res.status_code == 400
    err = res.json()["error"]
    assert err["code"] == "AI_KEY_MISSING"
    assert "AI 사용 키" in err["message"]
    assert err["error_id"]


def test_validation_error_is_korean(client):
    res = client.get("/api/_test/number", params={"n": "숫자아님"})
    assert res.status_code == 422
    err = res.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert "n" in err["detail"]


def test_unexpected_error_hides_details_and_gives_error_id(client):
    res = client.get("/api/_test/crash")
    assert res.status_code == 500
    err = res.json()["error"]
    assert err["code"] == "INTERNAL_ERROR"
    assert err["error_id"]
    assert "RuntimeError" not in res.text  # 내부 원인은 화면에 노출하지 않음


def test_unexpected_error_on_page_shows_korean_screen(client):
    res = client.get("/_test/crash")
    assert res.status_code == 500
    assert "예상하지 못한 문제" in res.text
    assert "오류 번호" in res.text


def test_health_reports_checks(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["checks"]["storage"] == "정상"
    assert body["checks"]["ai_key"].startswith("없음")
