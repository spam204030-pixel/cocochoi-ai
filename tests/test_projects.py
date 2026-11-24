import subprocess

import pytest

from app.core.models import Project
from app.media.probe import check_ffmpeg

FFMPEG = check_ffmpeg()
pytestmark = pytest.mark.skipif(not FFMPEG.installed, reason="이 컴퓨터에 FFmpeg가 없음")


def _make(path, *args):
    subprocess.run([FFMPEG.ffmpeg_path, "-y", "-v", "error", *args, str(path)], check=True)
    return path.read_bytes()


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    d = tmp_path_factory.mktemp("proj")
    return {
        "photo": _make(d / "p.jpg", "-f", "lavfi", "-i", "color=c=white:s=400x500", "-frames:v", "1"),
        "photo2": _make(d / "q.jpg", "-f", "lavfi", "-i", "color=c=gray:s=400x500", "-frames:v", "1"),
        "video": _make(
            d / "v.mp4",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=360x640:r=30:d=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
        ),
    }


@pytest.fixture
def product(client, media):
    """제품 + 사진 1장 + 영상 1개."""
    pid = client.post("/api/products", json={"name": "겨울 니삭스"}).json()["id"]
    files = [
        ("files", ("사진.jpg", media["photo"], "image/jpeg")),
        ("files", ("영상.mp4", media["video"], "video/mp4")),
    ]
    results = client.post(f"/api/products/{pid}/assets", files=files).json()["results"]
    return {"id": pid, "photo": results[0]["asset_id"], "video": results[1]["asset_id"]}


def test_create_with_defaults(client, product):
    res = client.post(
        "/api/projects", json={"product_id": product["id"], "asset_ids": [product["photo"], product["video"]]}
    )
    assert res.status_code == 201
    p = res.json()
    assert p["title"] == "겨울 니삭스"  # 제목을 비우면 제품명
    assert p["target_length"] == 20 and p["style_preset"] == "auto" and p["narration_mode"] == "tts"
    assert p["platforms"] == ["youtube", "instagram", "tiktok", "naver_clip", "naver_blog"]
    assert p["board_status"] == "신규" and p["status"] == "ready"
    assert p["quality_threshold"] == 80 and p["max_fix_rounds"] == 2
    assert p["asset_ids"] == sorted([product["photo"], product["video"]])


def test_photo_is_required(client, product):
    res = client.post("/api/projects", json={"product_id": product["id"], "asset_ids": [product["video"]]})
    assert res.json()["error"]["code"] == "PROJECT_NEEDS_PHOTO"
    res = client.post("/api/projects", json={"product_id": product["id"], "asset_ids": []})
    assert res.json()["error"]["code"] == "PROJECT_NEEDS_PHOTO"


def test_cannot_use_other_products_assets(client, product, media):
    other = client.post("/api/products", json={"name": "다른 제품"}).json()["id"]
    res = client.post("/api/projects", json={"product_id": other, "asset_ids": [product["photo"]]})
    assert res.status_code == 422


@pytest.mark.parametrize(
    "bad",
    [{"target_length": 25}, {"style_preset": "NOPE"}, {"platforms": []}, {"platforms": ["facebook"]},
     {"narration_mode": "x"}, {"ad_mode": "x"}, {"budget_limit": -1}],
)  # fmt: skip
def test_invalid_settings_rejected(client, product, bad):
    body = {"product_id": product["id"], "asset_ids": [product["photo"]], **bad}
    assert client.post("/api/projects", json=body).status_code == 422


def test_update_settings_and_assets(client, product, media):
    pid = client.post(
        "/api/projects", json={"product_id": product["id"], "asset_ids": [product["photo"], product["video"]]}
    ).json()["id"]
    res = client.patch(
        f"/api/projects/{pid}",
        json={
            "target_length": 30,
            "style_preset": "FAST_SHOPPING",
            "platforms": ["youtube", "instagram"],
            "asset_ids": [product["photo"]],
        },
    )
    p = res.json()
    assert p["target_length"] == 30 and p["style_preset"] == "FAST_SHOPPING"
    assert p["platforms"] == ["youtube", "instagram"] and p["asset_ids"] == [product["photo"]]
    # 프로젝트에서 뺀 영상 파일은 그대로 남아 있음
    assert any(
        a["id"] == product["video"] for a in client.get(f"/api/products/{product['id']}/assets").json()
    )


def test_cannot_edit_after_production_started(client, test_app, product):
    pid = client.post(
        "/api/projects", json={"product_id": product["id"], "asset_ids": [product["photo"]]}
    ).json()["id"]
    with test_app.state.db.session_factory() as s:
        s.get(Project, pid).status = "running"
        s.commit()
    assert (
        client.patch(f"/api/projects/{pid}", json={"target_length": 15}).json()["error"]["code"]
        == "PROJECT_LOCKED"
    )


def test_product_with_project_cannot_be_deleted(client, product):
    client.post("/api/projects", json={"product_id": product["id"], "asset_ids": [product["photo"]]})
    assert client.delete(f"/api/products/{product['id']}").json()["error"]["code"] == "PRODUCT_IN_USE"
    assert client.delete(f"/api/assets/{product['photo']}").json()["error"]["code"] == "ASSET_IN_USE"


def test_page_flow(client, product):
    assert "아직 만든 콘텐츠가 없습니다" in client.get("/projects").text
    assert "이 제품으로 콘텐츠 만들기" in client.get(f"/products/{product['id']}").text

    form = client.get(f"/projects/new?product_id={product['id']}")
    assert "사용할 소재" in form.text and form.text.count('name="asset_ids"') == 2

    res = client.post(
        "/projects/new",
        data={"product_id": product["id"], "title": "니삭스 쇼츠 1편", "target_length": "15", "style_preset": "FAST_SHOPPING",
              "platforms": ["youtube", "naver_blog"], "narration_mode": "own_voice", "ad_mode": "affiliate",
              "budget_limit": "3,000원", "asset_ids": [product["photo"]]},
        follow_redirects=True,
    )  # fmt: skip
    assert "저장했습니다" in res.text
    for text in (
        "니삭스 쇼츠 1편",
        "15초",
        "FAST_SHOPPING",
        "내 목소리 녹음",
        "유튜브 쇼츠, 네이버 블로그",
        "제휴",
        "3,000원",
    ):
        assert text in res.text
    assert "니삭스 쇼츠 1편" in client.get("/projects").text


def test_page_form_errors(client, product):
    res = client.post(
        "/projects/new",
        data={"product_id": product["id"], "target_length": "20", "style_preset": "auto",
              "narration_mode": "tts", "ad_mode": "none", "asset_ids": [product["video"]]},
    )  # fmt: skip
    assert res.status_code == 422
    assert "플랫폼을 하나 이상 골라 주세요" in res.text

    res = client.post(
        "/projects/new",
        data={"product_id": product["id"], "target_length": "20", "style_preset": "auto", "narration_mode": "tts",
              "ad_mode": "none", "platforms": ["youtube"], "asset_ids": [product["video"]]},
    )  # fmt: skip
    assert res.status_code == 422
    assert "제품 사진이 1장 이상 필요합니다" in res.text


def test_page_edit(client, product):
    pid = client.post(
        "/api/projects", json={"product_id": product["id"], "asset_ids": [product["photo"]]}
    ).json()["id"]
    assert "콘텐츠 설정 수정" in client.get(f"/projects/{pid}/edit").text
    res = client.post(
        f"/projects/{pid}/edit",
        data={"title": "", "target_length": "30", "style_preset": "PREMIUM_FASHION", "narration_mode": "tts",
              "ad_mode": "none", "platforms": ["tiktok"], "asset_ids": [product["photo"], product["video"]]},
        follow_redirects=True,
    )  # fmt: skip
    assert "30초" in res.text and "PREMIUM_FASHION" in res.text and "틱톡" in res.text
    assert "겨울 니삭스" in res.text  # 제목 비우면 제품명


def test_missing_project_404(client):
    assert client.get("/api/projects/999").status_code == 404
    assert "찾는 페이지나 자료가 없습니다" in client.get("/projects/999").text
