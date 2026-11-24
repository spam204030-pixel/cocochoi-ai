"""스킬 /기획 도구: 장면 준비(prepare)와 검사·파일 생성(finish)."""

import csv
import json
import shutil

import pytest

from app.cli.finish import finish, seconds
from app.cli.prepare import prepare
from tests.test_analysis import good
from tests.test_scenes import make_video

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg 필요")


@pytest.fixture
def out(tmp_path):
    src = tmp_path / "inputs" / "발열양말"
    src.mkdir(parents=True)
    (src / "상품정보.txt").write_text(
        "상품명: 발열양말\n특징: 충전식\n링크: https://link.coupang.com/x", "utf-8"
    )
    make_video(src / "v.mp4", [("red", 2.0), ("blue", 2.0)])
    return prepare(src, tmp_path / "out")


def script(ids):
    return {
        "hooks": ["발 시린 분?", "겨울 출근길", "양말 하나로", "엄마 선물", "무릎까지"],
        "plans": [
            {
                "title": "출근길 고민",
                "story": "상황→고민→발견→증거→행동",
                "hook": "발 시린 분?",
                "score": 88,
                "reason": "공감",
            },
            {
                "title": "제품 소개",
                "story": "기능 나열",
                "hook": "충전식",
                "score": 60,
                "reason": "단순 소개",
            },
        ],
        "selected": 1,
        "selected_reason": "공감이 큼",
        "lines": [
            {
                "no": 1,
                "role": "hook",
                "narration": "겨울만 되면 발이 시리죠?",
                "subtitle": "발 시린 분?",
                "scene_ids": ids[:1],
                "proof": "무릎까지 옴",
            },
            {
                "no": 2,
                "role": "proof",
                "narration": "무릎 위까지 올라와요",
                "subtitle": "무릎까지",
                "scene_ids": ids[1:],
                "proof": "무릎까지 옴",
            },
            {
                "no": 3,
                "role": "cta",
                "narration": "정보는 댓글로 보내드릴게요",
                "subtitle": "댓글 주세요",
                "scene_ids": ids,
                "proof": "착용",
            },
        ],
    }


def write(out, name, data):
    (out / name).write_text(json.dumps(data, ensure_ascii=False), "utf-8")


def test_prepare_makes_scenes_photos_and_grid(out):
    data = json.loads((out / "장면.json").read_text("utf-8"))
    scenes = data["영상"][0]["장면"]
    assert "충전식" in data["상품정보"] and len(scenes) == 2 and [s["id"] for s in scenes] == [1, 2]
    assert all((out / "_자료" / "영상1" / f"seg_00{i}.jpg").is_file() for i in (1, 2))
    assert data["영상"][0]["격자"][0].endswith("grid_01.jpg")


def test_finish_creates_files_with_code_timing(out):
    write(out, "분석.json", good([1, 2]))
    write(out, "대본.json", script([1, 2]))
    (out / "캡션.md").write_text("이 포스팅은 쿠팡 파트너스 활동의 일환으로, ...\n## 유튜브 쇼츠", "utf-8")
    assert finish(out) == []
    srt = (out / "자막.srt").read_text("utf-8")
    assert srt.startswith("1\n00:00:00,000 --> ") and "댓글 주세요" in srt
    rows = list(csv.reader((out / "편집지시표.csv").open(encoding="utf-8-sig")))
    assert rows[0][0] == "순서" and len(rows) == 4 and "v.mp4" in rows[1][3]
    assert abs(float(rows[1][2]) - seconds("겨울만 되면 발이 시리죠?")) < 0.05
    assert "✅ 선정" in (out / "기획.md").read_text("utf-8")
    assert "`입력`" in (out / "분석.md").read_text("utf-8")


def test_finish_rejects_wrong_scene_and_four_hooks(out):
    write(out, "분석.json", good([1, 2]))
    bad = script([1, 2])
    bad["lines"][0]["scene_ids"] = [99]
    write(out, "대본.json", bad)
    with pytest.raises(SystemExit, match="없는 장면 번호"):
        finish(out)
    bad = script([1, 2])
    bad["hooks"] = bad["hooks"][:4]
    write(out, "대본.json", bad)
    with pytest.raises(SystemExit, match="대본.json 형식 오류"):
        finish(out)


def test_caption_warnings(out):
    write(out, "분석.json", good([1, 2]))
    write(out, "대본.json", script([1, 2]))
    (out / "캡션.md").write_text("## 유튜브 쇼츠\n노출 보장!", "utf-8")
    warnings = finish(out)
    assert any("노출 보장" in w for w in warnings) and any("쿠팡" in w for w in warnings)
