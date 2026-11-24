"""AI 호출 창구 — 모든 AI·음성 호출은 반드시 여기를 거친다.

하는 일 (설계서 2-1, 7-2, 13장)
1. providers.yaml 로 공급자·모델 결정 (호출별 모델 등급)
2. 호출 전 예상 비용 계산 → 콘텐츠 예산 상한을 넘으면 실행하지 않음
3. 일시적 오류(사용량 많음·연결 실패·시간 초과)는 간격을 늘리며 최대 2번 더 시도
   (키 오류·크레딧 부족은 재시도 안 함)
4. 결과가 JSON 형식(스키마)에 맞지 않으면 이유를 붙여 1번만 다시 요청, 그래도 틀리면 AI_BAD_OUTPUT
5. 호출마다 사용량·비용을 usage_logs 에 기록 (실패한 시도도 기록)
"""

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select

from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger
from app.core.models import Project, UsageLog
from app.providers.base import LLMRequest, LLMResult, TTSResult
from app.providers.fake import count_tokens
from app.providers.registry import Registry

log = get_logger("ai")

RETRYABLE = {ErrorCode.AI_RATE_LIMITED, ErrorCode.AI_UNAVAILABLE, ErrorCode.AI_TIMEOUT}
MAX_ATTEMPTS = 3  # 처음 1번 + 재시도 2번
IMAGE_TOKENS = 800  # 축소 이미지 1장당 대략적인 토큰 (예상 비용용)


@dataclass
class AIResponse:
    data: dict | None  # 스키마 검사를 통과한 결과 (스키마 없으면 JSON 해석 결과 또는 None)
    raw_text: str
    result: LLMResult
    cost: float  # 원 (이번 호출 전체, 재요청 포함)
    attempts: int


def _parse_json(text: str) -> dict:
    cleaned = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text.strip())
    return json.loads(cleaned)


class AIGateway:
    def __init__(self, registry: Registry, session_factory, retry_backoff: float = 2.0) -> None:
        self.registry = registry
        self.session_factory = session_factory
        self.retry_backoff = retry_backoff

    # ---------- 비용 ----------

    def estimate_llm(self, request: LLMRequest) -> float:
        route = self.registry.route(request.call_key)
        p_in, p_out = self.registry.llm_price(route.provider, route.model)
        tokens_in = count_tokens(request.system + request.user) + IMAGE_TOKENS * len(request.images)
        return round(
            tokens_in * p_in / 1e6 + request.max_output_tokens * p_out / 1e6, 2
        )  # 출력은 최대치로 계산

    def project_spent(self, project_id: int) -> float:
        with self.session_factory() as s:
            total = s.scalar(select(func.sum(UsageLog.actual_cost)).where(UsageLog.project_id == project_id))
            return float(total or 0)

    def _check_budget(self, project_id: int | None, est_cost: float) -> None:
        if project_id is None:
            return
        with self.session_factory() as s:
            limit = s.scalar(select(Project.budget_limit).where(Project.id == project_id))
        if limit is None:
            return
        spent = self.project_spent(project_id)
        if spent + est_cost > limit:
            raise AppError(
                ErrorCode.BUDGET_EXCEEDED,
                f"사용 {spent:,.0f}원 + 이번 예상 {est_cost:,.0f}원 > 상한 {limit:,}원",
            )

    def _record(self, **fields) -> None:
        with self.session_factory() as s:
            s.add(UsageLog(**fields))
            s.commit()

    # ---------- AI(LLM) 호출 ----------

    def _call_once(self, request, route, provider, project_id, role_key) -> tuple[LLMResult, float, int]:
        p_in, p_out = self.registry.llm_price(route.provider, route.model)
        est = self.estimate_llm(request)
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                result = provider.generate(request, route.model)
            except AppError as exc:
                self._record(
                    project_id=project_id, role_key=role_key, call_key=request.call_key,
                    provider=route.provider, model=route.model, unit="tokens", est_cost=est,
                    actual_cost=0, attempt=attempt, ok=False,
                    error_code=str(exc.code),
                )  # fmt: skip
                if exc.code in RETRYABLE and attempt < MAX_ATTEMPTS:
                    wait = self.retry_backoff * (2 ** (attempt - 1))
                    log.warning(
                        "AI 호출 재시도 %s (%s) %d/%d, %.1f초 뒤",
                        request.call_key,
                        exc.code,
                        attempt,
                        MAX_ATTEMPTS,
                        wait,
                    )
                    time.sleep(wait)
                    continue
                raise
            cost = round(result.input_tokens * p_in / 1e6 + result.output_tokens * p_out / 1e6, 4)
            self._record(
                project_id=project_id, role_key=role_key, call_key=request.call_key, provider=result.provider,
                model=result.model, unit="tokens", input_units=result.input_tokens,
                output_units=result.output_tokens, est_cost=est, actual_cost=cost, attempt=attempt,
            )  # fmt: skip
            return result, cost, attempt
        raise AppError(ErrorCode.AI_UNAVAILABLE)  # 도달하지 않음

    def call_llm(
        self,
        request: LLMRequest,
        *,
        project_id: int | None = None,
        role_key: str | None = None,
        schema: type[BaseModel] | None = None,
    ) -> AIResponse:
        route = self.registry.route(request.call_key)
        provider = self.registry.llm(route.provider)
        self._check_budget(project_id, self.estimate_llm(request))

        result, cost, attempts = self._call_once(request, route, provider, project_id, role_key)
        data, problem = self._validate(result.text, schema)
        if problem is not None:
            # 형식 오류 → 이유를 붙여 1번만 다시 요청
            log.warning("AI 결과 형식 오류 %s: %s — 1번 다시 요청", request.call_key, problem[:200])
            retry = LLMRequest(
                call_key=request.call_key,
                system=request.system,
                user=request.user + f"\n\n[이전 응답 오류]\n{problem}\n지정된 JSON 형식으로만 다시 출력하라.",
                images=request.images,
                max_output_tokens=request.max_output_tokens,
                prompt_version=request.prompt_version,
            )
            self._check_budget(project_id, self.estimate_llm(retry))
            result, cost2, attempts2 = self._call_once(retry, route, provider, project_id, role_key)
            cost, attempts = cost + cost2, attempts + attempts2
            data, problem = self._validate(result.text, schema)
            if problem is not None:
                raise AppError(ErrorCode.AI_BAD_OUTPUT, f"호출 {request.call_key}: {problem[:300]}")
        log.info("AI 호출 %s %s/%s %.2f원", request.call_key, route.provider, route.model, cost)
        return AIResponse(data=data, raw_text=result.text, result=result, cost=cost, attempts=attempts)

    @staticmethod
    def _validate(text: str, schema: type[BaseModel] | None) -> tuple[dict | None, str | None]:
        try:
            data = _parse_json(text)
        except (json.JSONDecodeError, ValueError) as exc:
            return None, f"JSON으로 읽을 수 없음: {exc}" if schema else None
        if schema is None:
            return data, None
        try:
            return schema.model_validate(data).model_dump(), None
        except ValidationError as exc:
            return None, f"형식 불일치: {exc.errors()[:5]}"

    # ---------- 음성(TTS) ----------

    def tts(
        self, text: str, out_path: Path, *, voice: str | None = None, speed: float = 1.0,
        project_id: int | None = None, role_key: str | None = None,
    ) -> TTSResult:  # fmt: skip
        provider = self.registry.tts_provider()
        per_1k = self.registry.tts_price_per_1k(provider.name)
        est = round(len(text) / 1000 * per_1k, 2)
        self._check_budget(project_id, est)
        voice = voice or (self.registry.config.get("tts") or {}).get("voice", "")
        result = provider.synthesize(text, voice, speed, out_path)
        self._record(
            project_id=project_id, role_key=role_key, call_key="tts", provider=provider.name, model=voice,
            unit="chars", input_units=result.chars, est_cost=est, actual_cost=est,
        )  # fmt: skip
        return result
