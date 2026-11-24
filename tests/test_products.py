from app.core.models import Project

# ---------- API ----------


def test_api_create_with_name_only(client):
    res = client.post("/api/products", json={"name": "  겨울 기모 니삭스  "})
    assert res.status_code == 201
    body = res.json()
    assert body["name"] == "겨울 기모 니삭스"
    assert body["price"] is None and body["features"] is None


def test_api_create_requires_name(client):
    res = client.post("/api/products", json={"name": "   "})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_api_rejects_bad_price_and_url(client):
    assert client.post("/api/products", json={"name": "a", "price": -1}).status_code == 422
    assert client.post("/api/products", json={"name": "a", "purchase_url": "coupang.com"}).status_code == 422


def test_api_list_get_update_delete(client):
    pid = client.post(
        "/api/products", json={"name": "카멜 코트", "price": 129000, "category": "아우터"}
    ).json()["id"]
    client.post("/api/products", json={"name": "털 슬리퍼"})

    names = [p["name"] for p in client.get("/api/products").json()]
    assert names == ["털 슬리퍼", "카멜 코트"]  # 최신순
    assert [p["name"] for p in client.get("/api/products", params={"q": "아우터"}).json()] == ["카멜 코트"]

    res = client.patch(
        f"/api/products/{pid}", json={"price": 99000, "features": ["울 혼방", "", " 허리 끈 "]}
    )
    assert res.json()["price"] == 99000
    assert res.json()["features"] == ["울 혼방", "허리 끈"]
    assert res.json()["category"] == "아우터"  # 보내지 않은 칸은 그대로

    assert client.delete(f"/api/products/{pid}").status_code == 204
    assert client.get(f"/api/products/{pid}").status_code == 404


def test_api_missing_product_is_korean_404(client):
    res = client.get("/api/products/999")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"


def test_cannot_delete_product_used_by_project(client, test_app):
    pid = client.post("/api/products", json={"name": "여행 파우치"}).json()["id"]
    with test_app.state.db.session_factory() as s:
        s.add(Project(product_id=pid))
        s.commit()
    res = client.delete(f"/api/products/{pid}")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "PRODUCT_IN_USE"
    assert client.get(f"/api/products/{pid}").status_code == 200


# ---------- 화면 ----------


def test_page_full_flow(client):
    assert "아직 등록된 제품이 없습니다" in client.get("/products").text

    form = client.get("/products/new")
    assert form.status_code == 200 and "제품명" in form.text

    res = client.post(
        "/products/new",
        data={"name": "겨울 니삭스", "price": "19,800원", "features": "무릎 위 길이\n\n- 두꺼운 짜임"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    detail = client.get(res.headers["location"])
    assert "저장했습니다" in detail.text
    assert "19,800원" in detail.text
    assert "두꺼운 짜임" in detail.text

    pid = res.headers["location"].split("/")[2].split("?")[0]
    edit = client.get(f"/products/{pid}/edit")
    assert 'value="19800"' in edit.text

    res = client.post(
        f"/products/{pid}/edit", data={"name": "겨울 니삭스 2종", "price": ""}, follow_redirects=True
    )
    assert "겨울 니삭스 2종" in res.text and "입력 안 함" in res.text  # 비운 가격은 지워짐

    res = client.post(f"/products/{pid}/delete", follow_redirects=True)
    assert "제품을 삭제했습니다" in res.text


def test_page_form_errors_are_korean_and_keep_values(client):
    res = client.post("/products/new", data={"name": "", "price": "abc", "category": "양말"})
    assert res.status_code == 422
    assert "제품명을(를) 입력해 주세요" in res.text
    assert "가격은(는) 0 이상의 숫자" in res.text
    assert 'value="양말"' in res.text  # 입력한 값이 지워지지 않음


def test_page_escapes_html(client):
    client.post("/products/new", data={"name": "<script>alert(1)</script>"})
    page = client.get("/products").text
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


def test_home_links_to_products(client):
    assert 'href="/products"' in client.get("/").text
