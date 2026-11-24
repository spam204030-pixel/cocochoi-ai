"""장면 대표 사진·화질 측정 (작업 1-3)."""

import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import Database
from app.core.models import Asset, FootageSegment
from app.media.frames import labels, measure_segments

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg 필요")


def make(path, parts):
    """parts = [(lavfi 소스, 필터), ...] 2초씩 이어 붙인 세로 영상."""
    args, n = [], len(parts)
    for src, _ in parts:
        args += ["-f", "lavfi", "-i", f"{src}=s=360x640:r=30:d=2"]
    chains = [f"[{i}:v]{flt or 'null'}[v{i}]" for i, (_, flt) in enumerate(parts)]
    concat = "".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[v]"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            *args,
            "-filter_complex",
            ";".join([*chains, concat]),
            "-map",
            "[v]",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )
    return path


@pytest.fixture
def measured(tmp_path):
    video = make(
        tmp_path / "v.mp4",
        [("testsrc2", None), ("testsrc2", "boxblur=12"), ("testsrc2", "eq=brightness=-0.8")],
    )
    db = Database(tmp_path / "t.db")
    db.init()
    with db.session_factory() as s:
        asset = Asset(kind="footage", path="v.mp4", original_name="v.mp4", duration=6.0, file_hash="h")
        s.add(asset)
        s.flush()
        for i in range(3):  # 측정 검사이므로 장면 경계는 직접 지정
            s.add(FootageSegment(asset_id=asset.id, idx=i + 1, start=i * 2.0, end=i * 2.0 + 2, duration=2.0))
        s.flush()
        assert measure_segments(s, asset, video, tmp_path) == 3
        assert measure_segments(s, asset, video, tmp_path) == 0  # 다시 해도 중복 측정 없음
        segs = s.scalars(select(FootageSegment).order_by(FootageSegment.idx)).all()
        s.expunge_all()
    return segs, tmp_path, asset.id


def test_blurry_and_dark_scenes_score_lower(measured):
    (sharp, blurry, dark), _, _ = measured
    assert blurry.sharpness < sharp.sharpness and blurry.quality < sharp.quality
    assert dark.brightness < sharp.brightness and dark.quality < sharp.quality
    assert "흐림" in labels(blurry) and "어두움" in labels(dark) and labels(sharp) == []


def test_thumbs_and_grid_files(measured):
    segs, storage, asset_id = measured
    assert all((storage / s.thumb_path).is_file() for s in segs)
    assert [p.name for p in (storage / "frames" / str(asset_id)).glob("grid_*.jpg")] == ["grid_01.jpg"]


def test_segment_thumb_route(client, test_app):
    settings = test_app.state.settings
    with test_app.state.db.session_factory() as s:
        asset = Asset(kind="footage", path="v.mp4", original_name="v.mp4", file_hash="h2")
        s.add(asset)
        s.flush()
        seg = FootageSegment(asset_id=asset.id, idx=1, start=0, end=1, duration=1, thumb_path="frames/x.jpg")
        s.add(seg)
        s.commit()
        sid = seg.id
    assert client.get(f"/media/segments/{sid}/thumb").status_code == 404
    (settings.storage_dir / "frames").mkdir(parents=True, exist_ok=True)
    (settings.storage_dir / "frames" / "x.jpg").write_bytes(b"\xff\xd8\xff")
    assert TestClient(test_app).get(f"/media/segments/{sid}/thumb").status_code == 200
