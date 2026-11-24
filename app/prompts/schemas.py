"""AI 응답 형식 (코드가 검사). 설계서 V4-16 작업 B."""

from typing import Literal

from pydantic import BaseModel, ValidationInfo, field_validator, model_validator

Source = Literal["user_input", "visible", "inferred"]  # 입력 정보 / 화면에 보임 / AI 추정


def _check_ids(ids: list[int], info: ValidationInfo) -> list[int]:
    valid = (info.context or {}).get("segment_ids")
    if valid is not None:
        bad = [i for i in ids if i not in valid]
        if bad:
            raise ValueError(f"없는 장면 번호: {bad}")
    return ids


class SceneAnalysis(BaseModel):
    segment_id: int
    content: str  # 장면에서 일어나는 일 (한 줄)
    visible_facts: list[str]  # 화면에 실제로 보이는 것
    inferred: list[str] = []  # AI 추정 (보이지 않음)
    shot_type: str  # 착용 / 디테일 / 사용 / 분위기 / 제품 전체 / 기타
    proof_value: str  # 이 장면으로 증명할 수 있는 것
    usable: bool = True  # 쇼핑 영상에 쓸 만한가
    note: str = ""

    _ids = field_validator("segment_id")(lambda v, info: _check_ids([v], info)[0])


class Fact(BaseModel):
    text: str
    source: Source
    evidence: str  # 근거 위치: "입력란 특징" / "장면 7" / "상품 사진 2"


class PurchasePoint(BaseModel):
    point: str  # 소비자 말로 쓴 구매 포인트
    situation: str  # 어떤 상황·고민을 해결하는가
    source: Source
    segment_ids: list[int] = []  # 증명하는 장면

    _ids = field_validator("segment_ids")(_check_ids)


class Worry(BaseModel):
    worry: str  # 구매 고민 (망설이는 이유)
    answer: str  # 콘텐츠에서 풀어줄 답. 근거 없으면 "답 근거 없음"
    source: Source
    segment_ids: list[int] = []

    _ids = field_validator("segment_ids")(_check_ids)


class Target(BaseModel):
    situation: str  # 나이보다 상황·고민
    persona: str
    likelihood: Literal["상", "중", "하"]
    reason: str


class AnalysisResult(BaseModel):
    scenes: list[SceneAnalysis] = []  # 사진만 있는 상품은 비어 있음
    identity: str  # 무엇을 파는가 (한 문장)
    features: list[Fact]
    purchase_points: list[PurchasePoint]
    buy_reasons: list[str]  # 소비자가 사는 이유
    worries: list[Worry]
    targets: list[Target]
    differentiators: list[Fact]  # 근거 없으면 비워 두고 needs_confirmation 에
    banned_claims: list[str]  # 쓰면 안 되는 표현
    needs_confirmation: list[str]  # 대표님께 확인할 질문

    @model_validator(mode="after")
    def _all_scenes_and_points(self, info: ValidationInfo):
        valid = (info.context or {}).get("segment_ids")
        if valid:
            missing = sorted(set(valid) - {sc.segment_id for sc in self.scenes})
            if missing:
                raise ValueError(f"분석이 빠진 장면 번호: {missing}")
        if not self.purchase_points or not self.targets:
            raise ValueError("purchase_points 와 targets 는 1개 이상 필요")
        return self
