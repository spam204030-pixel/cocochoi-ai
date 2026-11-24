"""문서 검사: 설계서 v4.0·프롬프트에 필수 항목이 있는지 확인한다 (기능 검사가 아님)."""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _v4(name: str, end: str) -> str:
    text = (ROOT / "docs" / name).read_text(encoding="utf-8")
    assert end in text
    return text.split(end)[0]


DESIGN = _v4("DESIGN.md", "## 0. 프로젝트 정의")
PROMPTS = _v4("PROMPTS.md", "## 0. 이 문서 사용법")

DESIGN_REQUIRED = [
    "/공장",
    "자동 업로드",
    "노출 보장",
    "전체 복사",
    "대가성 문구",
    "링크 종류",
    "일반 글 형식",
    "SRT",
    "편집 지시표",
    "구매 전환 가능성",
    "연결 정확도",
    "무료 처리 구분표",
    "7편 이상",
]
PLATFORM_FIELDS = [
    "seo_title", "description", "keywords", "hashtags", "video_tags", "pinned_comment",  # 유튜브
    "hook_first_line", "caption", "cta",  # 인스타
    "hook_text",  # 틱톡
    "search_title",  # 네이버 클립
    "longtail_title", "body_markdown", "subheadings", "tags",  # 블로그
]


@pytest.mark.parametrize("word", DESIGN_REQUIRED)
def test_design_v4_has_required_item(word):
    assert word in DESIGN


@pytest.mark.parametrize("field", PLATFORM_FIELDS)
def test_prompts_v4_has_platform_field(field):
    assert field in PROMPTS


def test_prompts_ban_guarantee_phrases():
    assert "노출 보장" in PROMPTS and "보장 표현" in PROMPTS


def test_prompts_json_examples_are_valid():
    blocks = re.findall(r"```json\n(.*?)```", PROMPTS, re.S)
    assert blocks
    for block in blocks:
        json.loads(block)


def test_test_plan_exists_with_all_scenarios():
    plan = (ROOT / "docs" / "TEST_PLAN.md").read_text(encoding="utf-8")
    for n in range(25):
        assert f"T-{n:02d}" in plan
