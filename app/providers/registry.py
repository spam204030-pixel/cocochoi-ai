"""config/providers.yaml 을 읽어 AI 호출마다 쓸 공급자·모델을 정한다."""

from dataclasses import dataclass
from pathlib import Path

import yaml

from app.core.errors import AppError, ErrorCode
from app.providers.fake import FakeLLM, FakeSearch, FakeSTT, FakeTTS


@dataclass(frozen=True)
class Route:
    call_key: str
    tier: str
    provider: str
    model: str


def _load_yaml(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise AppError(ErrorCode.PROVIDER_NOT_CONFIGURED, f"{path.name}: {exc}") from exc


class Registry:
    """공급자 이름 → 실제 객체. Phase 1에서 실제 공급자(예: anthropic)를 여기에 등록한다."""

    def __init__(self, providers_file: Path, pricing_file: Path) -> None:
        self.config = _load_yaml(providers_file)
        self.pricing = _load_yaml(pricing_file)
        self.llms = {"fake": FakeLLM()}
        self.tts = {"fake": FakeTTS()}
        self.stt = {"fake": FakeSTT()}
        self.search = {"fake": FakeSearch()}

    # ---------- AI(LLM) ----------

    def route(self, call_key: str) -> Route:
        calls, tiers = self.config.get("calls", {}), self.config.get("tiers", {})
        tier = calls.get(call_key)
        target = tiers.get(tier) if tier else None
        if not target or "provider" not in target or "model" not in target:
            raise AppError(
                ErrorCode.PROVIDER_NOT_CONFIGURED, f"호출 {call_key}의 등급·공급자 설정이 없습니다"
            )
        return Route(call_key, tier, target["provider"], target["model"])

    def llm(self, provider: str):
        if provider not in self.llms:
            raise AppError(ErrorCode.PROVIDER_NOT_CONFIGURED, f"연결되지 않은 AI 공급자: {provider}")
        return self.llms[provider]

    def llm_price(self, provider: str, model: str) -> tuple[float, float]:
        """100만 토큰당 원 (입력, 출력). 단가표에 없으면 설정 오류 — 모르는 비용으로 실행하지 않는다."""
        price = (self.pricing.get("llm", {}).get(provider) or {}).get(model)
        if price is None:
            raise AppError(ErrorCode.PROVIDER_NOT_CONFIGURED, f"단가표에 {provider}/{model} 가격이 없습니다")
        return float(price.get("input", 0)), float(price.get("output", 0))

    # ---------- 음성·검색 ----------

    def _pick(self, kind: str, table: dict):
        name = (self.config.get(kind) or {}).get("provider", "fake")
        if name not in table:
            raise AppError(ErrorCode.PROVIDER_NOT_CONFIGURED, f"연결되지 않은 {kind} 공급자: {name}")
        return table[name]

    def tts_provider(self):
        return self._pick("tts", self.tts)

    def tts_price_per_1k(self, provider: str) -> float:
        price = (self.pricing.get("tts") or {}).get(provider)
        if price is None:
            raise AppError(ErrorCode.PROVIDER_NOT_CONFIGURED, f"단가표에 TTS {provider} 가격이 없습니다")
        return float(price.get("per_1k_chars", 0))

    def stt_provider(self):
        return self._pick("stt", self.stt)

    def search_provider(self):
        return self._pick("search", self.search)

    def summary(self) -> dict:
        """화면 표시용: 호출별 등급·공급자."""
        out = {}
        for call in self.config.get("calls", {}):
            try:
                r = self.route(call)
                out[call] = f"{r.tier} · {r.provider}/{r.model}"
            except AppError as exc:
                out[call] = f"설정 오류: {exc.detail}"
        return out

    def all_fake(self) -> bool:
        tiers = self.config.get("tiers", {}).values()
        return all(t.get("provider") == "fake" for t in tiers)
