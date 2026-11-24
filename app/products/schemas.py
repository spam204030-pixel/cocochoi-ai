"""제품 입력·출력 형식. 필수는 제품명 하나 (설계서 화면 ①)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _blank_to_none(value):
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


class ProductBase(BaseModel):
    category: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=5000)
    price: int | None = Field(default=None, ge=0, le=100_000_000)
    detail_text: str | None = Field(default=None, max_length=50_000)
    purchase_url: str | None = Field(default=None, max_length=1000)
    features: list[str] | None = None

    @field_validator("category", "description", "detail_text", "purchase_url", "price", mode="before")
    @classmethod
    def _strip(cls, value):
        return _blank_to_none(value)

    @field_validator("purchase_url")
    @classmethod
    def _check_url(cls, value):
        if value and not value.lower().startswith(("http://", "https://")):
            raise ValueError("구매 링크는 http:// 또는 https:// 로 시작해야 합니다")
        return value

    @field_validator("features", mode="before")
    @classmethod
    def _features_list(cls, value):
        if value is None:
            return None
        if isinstance(value, str):  # 화면 입력: 한 줄에 하나씩
            value = value.splitlines()
        items = [str(v).strip().lstrip("-•· ").strip() for v in value]
        items = [v for v in items if v]
        return items or None


class ProductCreate(ProductBase):
    name: str = Field(min_length=1, max_length=200)

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class ProductUpdate(ProductBase):
    """수정: 보낸 칸만 바꾼다."""

    name: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class ProductOut(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    updated_at: datetime


FIELD_LABELS = {
    "name": "제품명",
    "category": "카테고리",
    "description": "제품 설명",
    "price": "가격",
    "detail_text": "상세페이지 내용",
    "purchase_url": "구매 링크",
    "features": "주요 특징",
}
