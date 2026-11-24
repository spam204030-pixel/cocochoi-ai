"""Phase 0 통합 시나리오 (설계서 0-11): 대표가 화면에서 하는 순서 그대로.

제품 등록 → 사진 3장·영상 2개 업로드 → 콘텐츠 만들기 → 시험 실행(일시정지·재개 포함) → 검수 대기 → 현황판
"""

import re
import subprocess

import pytest

from app.media.probe import check_ffmpeg
from app.pipeline.worker import wait_until_idle

FFMPEG = check_ffmpeg()
pytestmark = pytest.mark.skipif(not FFMPEG.installed, reason="이 컴퓨터에 FFmpeg가 없음")


def _make(path, *args):
    subprocess.run([FFMPEG.ffmpeg_path, "-y", "-v", "error", *args, str(path)], check=True)
    return path.read_bytes()


def test_phase0_full_scenario(client, test_app, tmp_path):
    worker = test_app.state.worker

    # 1. 처음 화면: 안내 + 빈 현황판
    home = client.get("/").text
    assert "콘텐츠 제작 현황" in home and "제품 등록" in home

    # 2. 제품 등록 (화면 입력)
    res = client.post(
        "/products/new",
        data={
            "name": "겨울 기모 니삭스",
            "price": "19,800",
            "features": "무릎 위까지 오는 길이\n두꺼운 짜임",
        },
        follow_redirects=False,
    )
    product_id = int(re.search(r"/products/(\d+)", res.headers["location"]).group(1))

    # 3. 사진 3장 + 영상 2개 업로드 (영상 소재 1, 직접 촬영 1)
    photos = [
        (
            "files",
            (
                f"제품{i}.jpg",
                _make(
                    tmp_path / f"p{i}.jpg", "-f", "lavfi", "-i", f"color=c={c}:s=600x800", "-frames:v", "1"
                ),
                "image/jpeg",
            ),
        )
        for i, c in enumerate(("white", "gray", "beige"), 1)
    ]
    video = lambda name, color, sec: _make(  # noqa: E731
        tmp_path / name, "-f", "lavfi", "-i", f"color=c={color}:s=360x640:r=30:d={sec}",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={sec}", "-shortest",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
    )  # fmt: skip
    client.post(f"/products/{product_id}/upload", files=photos)
    client.post(
        f"/products/{product_id}/upload",
        files=[("files", ("샤오홍슈 소재.mp4", video("a.mp4", "red", 3), "video/mp4"))],
        data={
            "video_kind": "footage",
            "source_url": "https://www.xiaohongshu.com/x",
            "source_memo": "니삭스 착용",
        },
    )
    client.post(
        f"/products/{product_id}/upload",
        files=[("files", ("내 촬영.mp4", video("b.mp4", "blue", 2), "video/mp4"))],
        data={"video_kind": "own_clip"},
    )
    assets = client.get(f"/api/products/{product_id}/assets").json()
    kinds = sorted(a["kind"] for a in assets)
    assert kinds == ["footage", "own_clip", "product_photo", "product_photo", "product_photo"]
    assert next(a for a in assets if a["kind"] == "footage")["source_url"] == "https://www.xiaohongshu.com/x"
    page = client.get(f"/products/{product_id}").text
    assert '사진·영상 <span class="muted">(5개)' in page

    # 4. 콘텐츠 만들기 (화면 입력, 소재 전부)
    res = client.post(
        "/projects/new",
        data={"product_id": product_id, "title": "니삭스 쇼츠 1편", "target_length": "20", "style_preset": "FAST_SHOPPING",
              "narration_mode": "tts", "ad_mode": "affiliate", "platforms": ["youtube", "instagram", "naver_blog"],
              "budget_limit": "3000", "asset_ids": [a["id"] for a in assets]},
        follow_redirects=False,
    )  # fmt: skip
    project_id = int(re.search(r"/projects/(\d+)", res.headers["location"]).group(1))
    assert "니삭스 쇼츠 1편" in client.get("/").text.split("<strong>신규</strong>")[1].split("</section>")[0]

    # 5. 시험 실행 → 2단계 후 일시정지 → 현황판 '제작 중' → 재개 → 완료
    client.post(f"/projects/{project_id}/run/start")
    client.post(f"/projects/{project_id}/run/start")  # 두 번 눌러도
    assert client.get(f"/api/projects/{project_id}/pipeline").json()["status"] == "running"
    worker.run_once()
    worker.run_once()
    client.post(f"/projects/{project_id}/run/pause")
    wait_until_idle(worker)
    state = client.get(f"/api/projects/{project_id}/pipeline").json()
    assert state["status"] == "paused" and state["done_count"] == 2
    assert (
        "니삭스 쇼츠 1편" in client.get("/").text.split("<strong>제작 중</strong>")[1].split("</section>")[0]
    )

    client.post(f"/projects/{project_id}/run/resume")
    wait_until_idle(worker)
    state = client.get(f"/api/projects/{project_id}/pipeline").json()
    assert state["status"] == "waiting_user" and state["done_count"] == 8
    assert state["ai_calls"] == 7 and state["ai_cost"] == 0
    assert all(s["version"] == 1 for s in state["steps"])  # 일시정지·재개로 다시 한 단계 없음

    # 6. 현황판 '검수 대기' + 상세 화면
    board = client.get("/").text.split("<strong>검수 대기</strong>")[1].split("</section>")[0]
    assert "⚠ 니삭스 쇼츠 1편" in board
    detail = client.get(f"/projects/{project_id}").text
    assert "대표님 확인" in detail and "AI 사용 7회 · 비용 0원" in detail

    # 7. 쓰인 제품·파일은 지울 수 없음 (데이터 보호)
    assert client.delete(f"/api/products/{product_id}").json()["error"]["code"] == "PRODUCT_IN_USE"
    assert client.delete(f"/api/assets/{assets[0]['id']}").json()["error"]["code"] == "ASSET_IN_USE"

    # 8. 상태 확인
    checks = client.get("/api/health").json()["checks"]
    assert checks["storage"] == "정상" and checks["db"] == "정상" and checks["ffmpeg"].startswith("정상")
