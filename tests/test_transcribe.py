"""중국어 받아쓰기 (작업 A). 실제 모델 대신 정해진 문장으로 장면 나눔·건너뛰기를 확인한다."""

import json

import pytest
from sqlalchemy import select

from app.core.db import Database
from app.core.models import Asset, FootageSegment
from app.media.transcribe import choose_model, transcribe_asset

LINES = [
    (0.2, 1.5, "我真的不知道"),
    (2.1, 3.0, "冬天脚很冷"),
    (3.2, 3.9, "膝盖也暖"),
    (5.5, 6.2, "推荐给妈妈"),
]


@pytest.fixture
def setup(tmp_path):
    db = Database(tmp_path / "t.db")
    db.init()
    s = db.session_factory()
    asset = Asset(kind="footage", path="v.mp4", original_name="v.mp4", file_hash="h", has_audio=True)
    s.add(asset)
    s.flush()
    for i, (a, b) in enumerate([(0, 2), (2, 4), (4, 6)], 1):
        s.add(FootageSegment(asset_id=asset.id, idx=i, start=a, end=b, duration=b - a))
    s.flush()
    yield s, asset, tmp_path
    s.close()


def texts(s, asset):
    rows = s.scalars(
        select(FootageSegment).where(FootageSegment.asset_id == asset.id).order_by(FootageSegment.idx)
    )
    return [r.transcript_zh for r in rows]


def test_lines_go_to_their_scenes(setup):
    s, asset, storage = setup
    calls = []
    fake = lambda path, model: calls.append(model) or LINES  # noqa: E731
    assert transcribe_asset(s, asset, storage / "v.mp4", storage, "base", fake) == 4
    assert texts(s, asset) == ["我真的不知道", "冬天脚很冷 膝盖也暖", "推荐给妈妈"]
    saved = json.loads((storage / "frames" / str(asset.id) / "transcript.json").read_text("utf-8"))
    assert saved["model"] == "base" and len(saved["lines"]) == 4
    assert transcribe_asset(s, asset, storage / "v.mp4", storage, "base", fake) is None  # 다시 안 함
    assert calls == ["base"]


def test_skips_silent_video_and_off_setting(setup):
    s, asset, storage = setup
    boom = lambda path, model: pytest.fail("호출되면 안 됨")  # noqa: E731
    assert transcribe_asset(s, asset, storage / "v.mp4", storage, "off", boom) is None
    asset.has_audio = False
    assert transcribe_asset(s, asset, storage / "v.mp4", storage, "small", boom) is None
    assert texts(s, asset) == [None, None, None]


def test_choose_model():
    assert choose_model("tiny") == "tiny"
    assert choose_model("auto") in ("small", "base")


def test_model_download_failure_is_korean_error(monkeypatch, tmp_path):
    import faster_whisper

    from app.core.errors import AppError
    from app.media import transcribe

    def broken(*a, **k):
        raise OSError("network")

    monkeypatch.setattr(faster_whisper, "WhisperModel", broken)
    transcribe._models.clear()
    with pytest.raises(AppError) as err:
        transcribe.whisper_transcribe(tmp_path / "v.mp4", "tiny")
    assert "인터넷" in err.value.detail
