"""AI·음성 공급자 공통 규격. 단계 코드는 이 규격만 알고, 어느 회사 것인지는 모른다 (설계서 2-1 원칙 2).

공급자를 바꾸려면: 이 규격을 따르는 클래스를 하나 만들고 registry 에 등록한 뒤
config/providers.yaml 에서 이름만 바꾼다.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class LLMRequest:
    call_key: str  # A~H (PROMPTS.md)
    system: str  # 공통 규칙 + 역할 지시문
    user: str  # 입력 데이터 (외부 텍스트는 <external_data> 안에)
    images: list[Path] = field(default_factory=list)
    max_output_tokens: int = 4000
    prompt_version: str = "v1"


@dataclass
class LLMResult:
    text: str  # AI가 돌려준 원문 (JSON 문자열)
    input_tokens: int
    output_tokens: int
    provider: str
    model: str


@dataclass
class TTSResult:
    audio_path: Path
    duration: float  # 초
    chars: int


@dataclass
class STTSegment:
    start: float
    end: float
    text: str


class LLMProvider(Protocol):
    name: str

    def generate(self, request: LLMRequest, model: str) -> LLMResult: ...


class TTSProvider(Protocol):
    name: str

    def synthesize(self, text: str, voice: str, speed: float, out_path: Path) -> TTSResult: ...


class STTProvider(Protocol):
    name: str

    def transcribe(self, audio_path: Path) -> list[STTSegment]: ...


class SearchProvider(Protocol):
    name: str

    def search(self, query: str) -> list[dict]: ...
