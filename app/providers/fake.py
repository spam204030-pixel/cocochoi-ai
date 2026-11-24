"""시험용 가짜 공급자 — 비용 없이 전체 흐름을 확인한다. 결과에는 항상 fake=True 가 들어간다."""

import json
import math
import wave
from pathlib import Path

from app.providers.base import LLMRequest, LLMResult, STTSegment, TTSResult


def count_tokens(text: str) -> int:
    """대략적인 토큰 수 (한국어 기준 약 2글자 = 1토큰). 실제 공급자는 응답의 정확한 값을 쓴다."""
    return max(1, math.ceil(len(text) / 2))


class FakeLLM:
    name = "fake"

    def __init__(self, responses: dict[str, list[str]] | None = None) -> None:
        # 테스트에서 호출별 응답을 미리 넣을 수 있다 (순서대로 하나씩 꺼냄)
        self.responses = responses or {}
        self.calls: list[LLMRequest] = []

    def generate(self, request: LLMRequest, model: str) -> LLMResult:
        self.calls.append(request)
        queue = self.responses.get(request.call_key)
        if queue:
            item = queue.pop(0)
            if isinstance(item, Exception):
                raise item
            text = item
        else:
            text = json.dumps({"fake": True, "call": request.call_key}, ensure_ascii=False)
        return LLMResult(
            text=text,
            input_tokens=count_tokens(request.system + request.user) + 800 * len(request.images),
            output_tokens=count_tokens(text),
            provider=self.name,
            model=model,
        )


class FakeTTS:
    name = "fake"

    def synthesize(self, text: str, voice: str, speed: float, out_path: Path) -> TTSResult:
        """글자 수에 비례한 길이의 무음 WAV (초당 약 6.5글자)."""
        duration = round(len(text) / 6.5 / max(speed, 0.1), 2)
        rate = 16000
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(out_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(b"\x00\x00" * int(rate * duration))
        return TTSResult(audio_path=out_path, duration=duration, chars=len(text))


class FakeSTT:
    name = "fake"

    def transcribe(self, audio_path: Path) -> list[STTSegment]:
        return []


class FakeSearch:
    name = "fake"

    def search(self, query: str) -> list[dict]:
        return []
