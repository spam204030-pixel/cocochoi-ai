"""콘텐츠 프로젝트(콘텐츠 1편) 설정 값과 입력 형식 (설계서 화면 ②, 4-5 스타일 프리셋)."""

from pydantic import BaseModel, Field, field_validator

LENGTHS = (15, 20, 30)

# 설계서 4-5. 세부 수치(컷 길이·자막·BGM 등)는 Phase 3에서 config/presets.yaml 로 연결
PRESETS: dict[str, str] = {
    "auto": "자동 추천 (기획안에 맞춰 AI가 고름)",
    "PREMIUM_FASHION": "고급스러운 편집, 느린 컷",
    "FAST_SHOPPING": "빠른 컷, 강한 훅, 제품 중심",
    "INFORMATION": "정보 전달, 읽기 쉬운 자막",
    "EMOTIONAL": "감성 나레이션, 분위기 중심",
    "PRODUCT_REVIEW": "장단점·상세 설명",
    "TREND_SHORTS": "빠른 템포, 트렌드형",
    "FASHION_LOOKBOOK": "룩별 전환, 음악 중심",
    "BEFORE_AFTER": "전후 비교 구조",
    "PROBLEM_SOLUTION": "문제 제기 후 해결",
    "STORYTELLING": "스토리 중심",
}

PLATFORMS: dict[str, str] = {
    "youtube": "유튜브 쇼츠",
    "instagram": "인스타 릴스",
    "tiktok": "틱톡",
    "naver_clip": "네이버 클립",
    "naver_blog": "네이버 블로그",
}

NARRATION_MODES: dict[str, str] = {"tts": "AI 음성", "own_voice": "내 목소리 녹음"}

AD_MODES: dict[str, str] = {
    "none": "표기 없음",
    "ad": "광고 (협찬·자사 상품)",
    "affiliate": "제휴 (쿠팡파트너스 등)",
}

BOARD_STATUSES = ("신규", "제작 중", "검수 대기", "완료")


class ProjectSettings(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    target_length: int = 20
    style_preset: str = "auto"
    platforms: list[str] = Field(default_factory=lambda: list(PLATFORMS))
    narration_mode: str = "tts"
    ad_mode: str = "none"
    auto_mode: bool = False
    budget_limit: int | None = Field(default=None, ge=0, le=1_000_000)

    @field_validator("title", "budget_limit", mode="before")
    @classmethod
    def _blank(cls, value):
        if isinstance(value, str):
            value = value.replace(",", "").replace("원", "").strip()
            return value or None
        return value

    @field_validator("target_length")
    @classmethod
    def _length(cls, value):
        if value not in LENGTHS:
            raise ValueError("영상 길이는 15초, 20초, 30초 중에서 골라 주세요")
        return value

    @field_validator("style_preset")
    @classmethod
    def _preset(cls, value):
        if value not in PRESETS:
            raise ValueError("스타일 프리셋을 목록에서 골라 주세요")
        return value

    @field_validator("platforms")
    @classmethod
    def _platforms(cls, value):
        value = [p for p in dict.fromkeys(value) if p]  # 순서 유지·중복 제거
        unknown = [p for p in value if p not in PLATFORMS]
        if unknown:
            raise ValueError(f"알 수 없는 플랫폼: {', '.join(unknown)}")
        if not value:
            raise ValueError("플랫폼을 하나 이상 골라 주세요")
        return value

    @field_validator("narration_mode")
    @classmethod
    def _narration(cls, value):
        if value not in NARRATION_MODES:
            raise ValueError("나레이션 방식을 골라 주세요")
        return value

    @field_validator("ad_mode")
    @classmethod
    def _ad(cls, value):
        if value not in AD_MODES:
            raise ValueError("광고 표기를 골라 주세요")
        return value


class ProjectCreate(ProjectSettings):
    product_id: int
    asset_ids: list[int] = Field(default_factory=list)


class ProjectUpdate(ProjectSettings):
    asset_ids: list[int] | None = None


FIELD_LABELS = {
    "title": "제목",
    "target_length": "영상 길이",
    "style_preset": "스타일 프리셋",
    "platforms": "플랫폼",
    "narration_mode": "나레이션 방식",
    "ad_mode": "광고 표기",
    "budget_limit": "AI 예산 상한",
    "product_id": "제품",
    "asset_ids": "사용할 소재",
}
