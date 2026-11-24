import subprocess

import pytest
from fastapi.testclient import TestClient

from app.core.models import Asset, Project, ProjectAsset
from app.main import create_app
from app.media.probe import check_ffmpeg

FFMPEG = check_ffmpeg()
pytestmark = pytest.mark.skipif(not FFMPEG.installed, reason="이 컴퓨터에 FFmpeg가 없음")


def _make(path, *args):
    subprocess.run([FFMPEG.ffmpeg_path, "-y", "-v", "error", *args, str(path)], check=True)
    return path.read_bytes()


@pytest.fixture(scope="module")
def files(tmp_path_factory):
    d = tmp_path_factory.mktemp("upload")
    return {
        "video": _make(
            d / "v.mp4",
            "-f", "lavfi", "-i", "color=c=red:s=360x640:r=30:d=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        ),
        "photo": _make(d / "p.jpg", "-f", "lavfi", "-i", "color=c=white:s=800x1000", "-frames:v", "1"),
        "photo2": _make(d / "p2.png", "-f", "lavfi", "-i", "color=c=green:s=400x400", "-frames:v", "1"),
    }  # fmt: skip


@pytest.fixture
def pid(client):
    return client.post("/api/products", json={"name": "겨울 니삭스"}).json()["id"]


def _upload(client, pid, items, **form):
    return client.post(f"/api/products/{pid}/assets", files=[("files", it) for it in items], data=form)


def test_upload_photo_and_video_saves_info_and_thumbnails(client, pid, files, tmp_settings):
    res = _upload(
        client,
        pid,
        [("세로 영상.mp4", files["video"], "video/mp4"), ("제품 사진.jpg", files["photo"], "image/jpeg")],
        source_url="https://www.xiaohongshu.com/abc",
        source_memo="참고 영상",
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok_count"] == 2

    assets = {a["original_name"]: a for a in client.get(f"/api/products/{pid}/assets").json()}
    video, photo = assets["세로 영상.mp4"], assets["제품 사진.jpg"]
    assert video["kind"] == "footage" and (video["width"], video["height"]) == (360, 640)
    assert video["duration"] == pytest.approx(2.0, abs=0.1) and video["has_audio"] is True
    assert photo["kind"] == "product_photo" and photo["duration"] is None
    assert video["source_url"] == "https://www.xiaohongshu.com/abc" and video["source_memo"] == "참고 영상"

    # 디스크: storage/assets/<id>/original.mp4 + thumb.jpg (영문 이름)
    folder = tmp_settings.assets_dir / str(video["id"])
    assert (folder / "original.mp4").is_file() and (folder / "thumb.jpg").is_file()
    assert client.get(video["thumb_url"]).headers["content-type"] == "image/jpeg"
    assert client.get(video["file_url"]).status_code == 200
    assert not any(tmp_settings.tmp_dir.iterdir())  # 임시 파일이 남지 않음


def test_own_clip_kind(client, pid, files):
    _upload(client, pid, [("내 촬영.mp4", files["video"], "video/mp4")], video_kind="own_clip")
    assert client.get(f"/api/products/{pid}/assets").json()[0]["kind"] == "own_clip"


def test_duplicate_file_is_rejected_but_others_continue(client, pid, files):
    _upload(client, pid, [("a.jpg", files["photo"], "image/jpeg")])
    res = _upload(
        client, pid, [("같은사진.jpg", files["photo"], "image/jpeg"), ("b.png", files["photo2"], "image/png")]
    )
    results = res.json()["results"]
    assert results[0]["ok"] is False and "이미 올린 파일" in results[0]["message"]
    assert results[0]["existing_asset_id"] is not None
    assert results[1]["ok"] is True
    assert len(client.get(f"/api/products/{pid}/assets").json()) == 2


def test_unsupported_and_broken_files(client, pid, tmp_settings):
    res = _upload(
        client, pid, [("문서.pdf", b"%PDF", "application/pdf"), ("깨짐.mp4", b"not a video", "video/mp4")]
    )
    r1, r2 = res.json()["results"]
    assert r1["ok"] is False and "올릴 수 없는 파일 형식" in r1["message"]
    assert r2["ok"] is False and "읽을 수 없습니다" in r2["message"]
    assert client.get(f"/api/products/{pid}/assets").json() == []
    assert not any(tmp_settings.tmp_dir.iterdir())
    assert not any(tmp_settings.assets_dir.iterdir())  # 실패한 파일은 저장되지 않음


def test_file_too_large(tmp_settings, files):
    tmp_settings.max_upload_mb = 0  # 0MB 제한 → 모든 파일 초과
    client = TestClient(create_app(tmp_settings))
    pid = client.post("/api/products", json={"name": "x"}).json()["id"]
    r = _upload(client, pid, [("a.jpg", files["photo"], "image/jpeg")]).json()["results"][0]
    assert r["ok"] is False and "너무 큽니다" in r["message"]


def test_update_source_and_delete(client, pid, files, tmp_settings):
    aid = _upload(client, pid, [("a.jpg", files["photo"], "image/jpeg")]).json()["results"][0]["asset_id"]
    res = client.patch(f"/api/assets/{aid}", json={"source_url": " https://x.com/1 ", "source_memo": ""})
    assert res.json()["source_url"] == "https://x.com/1" and res.json()["source_memo"] is None

    assert client.delete(f"/api/assets/{aid}").status_code == 204
    assert not (tmp_settings.assets_dir / str(aid)).exists()
    assert client.get(f"/media/{aid}/thumb").status_code == 404


def test_asset_used_in_project_cannot_be_deleted(client, test_app, pid, files):
    aid = _upload(client, pid, [("a.jpg", files["photo"], "image/jpeg")]).json()["results"][0]["asset_id"]
    with test_app.state.db.session_factory() as s:
        project = Project(product_id=pid)
        s.add(project)
        s.flush()
        s.add(ProjectAsset(project_id=project.id, asset_id=aid))
        s.commit()
    assert client.delete(f"/api/assets/{aid}").json()["error"]["code"] == "ASSET_IN_USE"
    with test_app.state.db.session_factory() as s:
        assert s.get(Asset, aid) is not None


def test_upload_to_missing_product(client, files):
    assert _upload(client, 999, [("a.jpg", files["photo"], "image/jpeg")]).status_code == 404


def test_page_upload_flow(client, pid, files):
    page = client.get(f"/products/{pid}")
    assert "사진·영상을 끌어다 놓거나" in page.text

    res = client.post(
        f"/products/{pid}/upload",
        files=[("files", ("니삭스.mp4", files["video"], "video/mp4"))],
        data={"video_kind": "footage"},
        follow_redirects=True,
    )
    assert "1개 파일을 올렸습니다" in res.text
    assert "니삭스.mp4" in res.text and "360×640" in res.text and "2.0초" in res.text

    aid = client.get(f"/api/products/{pid}/assets").json()[0]["id"]
    res = client.post(
        f"/assets/{aid}/source",
        data={"source_url": "https://xhs.com/9", "source_memo": "메모"},
        follow_redirects=True,
    )
    assert 'value="https://xhs.com/9"' in res.text
    res = client.post(f"/assets/{aid}/delete", follow_redirects=True)
    assert "파일을 삭제했습니다" in res.text
