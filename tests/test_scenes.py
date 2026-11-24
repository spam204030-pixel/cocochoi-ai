"""장면 나누기 (작업 1-2): 컷 위치를 아는 시험 영상으로 ±0.3초 확인."""

import shutil
import subprocess

import pytest
from sqlalchemy import select

from app.core.db import Database
from app.core.models import Asset, FootageSegment
from app.media.scenes import detect_scenes, segment_asset

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg 필요")


def make_video(path, colors_secs):
    """색이 바뀌는 세로 영상. colors_secs = [("red", 2.0), ...]"""
    inputs, n = [], len(colors_secs)
    for color, sec in colors_secs:
        inputs += ["-f", "lavfi", "-i", f"color=c={color}:s=360x640:r=30:d={sec}"]
    concat = "".join(f"[{i}:v]" for i in range(n)) + f"concat=n={n}:v=1:a=0[v]"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            *inputs,
            "-filter_complex",
            concat,
            "-map",
            "[v]",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )
    return path


def test_cuts_found_within_tolerance(tmp_path):
    video = make_video(tmp_path / "cuts.mp4", [("red", 2.0), ("blue", 2.5), ("green", 1.5)])
    spans = detect_scenes(video, 6.0)
    assert len(spans) == 3
    for (start, _), expected in zip(spans[1:], (2.0, 4.5), strict=True):
        assert abs(start - expected) <= 0.3
    assert spans[0][0] == 0 and abs(spans[-1][1] - 6.0) <= 0.1


def test_short_flash_is_merged(tmp_path):
    video = make_video(tmp_path / "flash.mp4", [("red", 2.0), ("white", 0.2), ("blue", 2.0)])
    spans = detect_scenes(video, 4.2)
    assert all(e - s >= 0.5 for s, e in spans) and len(spans) == 2


def test_no_cut_gives_one_scene(tmp_path):
    video = make_video(tmp_path / "one.mp4", [("gray", 3.0)])
    assert detect_scenes(video, 3.0) == [(0.0, 3.0)]


def test_segments_saved_once(tmp_path):
    db = Database(tmp_path / "t.db")
    db.init()
    video = make_video(tmp_path / "save.mp4", [("red", 1.5), ("blue", 1.5)])
    with db.session_factory() as s:
        asset = Asset(kind="footage", path="x.mp4", original_name="x.mp4", duration=3.0, file_hash="h1")
        s.add(asset)
        s.flush()
        assert segment_asset(s, asset, video) == 2
        assert segment_asset(s, asset, video) == 2  # 다시 해도 중복 없음
        rows = s.scalars(select(FootageSegment).where(FootageSegment.asset_id == asset.id)).all()
        assert [r.idx for r in rows] == [1, 2] and abs(rows[1].start - 1.5) <= 0.3
