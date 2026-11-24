"""중국어 음성 받아쓰기 (설계서 V4-16 작업 A). faster-whisper, 로컬·무료.

받아쓴 문장은 장면 시간에 맞춰 나눠 붙인다 (문장 가운데 시점이 속한 장면).
번역은 하지 않는다 (작업 B에서 Claude 가 한다).
"""

import json
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger
from app.core.models import Asset, FootageSegment

log = get_logger("transcribe")
Line = tuple[float, float, str]  # (시작, 끝, 문장)
_models: dict[str, object] = {}


def choose_model(setting: str) -> str:
    if setting != "auto":
        return setting
    import psutil

    return "small" if psutil.virtual_memory().total / 1024**3 >= 7.5 else "base"


def whisper_transcribe(path: Path, model_name: str) -> list[Line]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise AppError(
            ErrorCode.AI_UNAVAILABLE,
            "받아쓰기 부품이 설치되지 않았습니다. 터미널에서 uv sync --extra transcribe 를 실행하세요.",
        ) from exc

    if model_name not in _models:  # 처음 한 번 모델을 내려받고 불러온다
        log.info("받아쓰기 모델 준비: %s", model_name)
        try:
            _models[model_name] = WhisperModel(model_name, device="cpu", compute_type="int8")
        except Exception as exc:
            raise AppError(
                ErrorCode.AI_UNAVAILABLE,
                f"받아쓰기 모델({model_name})을 내려받지 못했습니다. "
                "인터넷 연결을 확인하고 이 단계를 다시 실행하세요.",
            ) from exc
    try:
        segments, _ = _models[model_name].transcribe(str(path), language="zh", vad_filter=True)
        return [(round(s.start, 2), round(s.end, 2), s.text.strip()) for s in segments if s.text.strip()]
    except Exception as exc:
        raise AppError(ErrorCode.MEDIA_UNREADABLE, f"받아쓰기 실패: {path.name}") from exc


def assign(lines: list[Line], segs: list[FootageSegment]) -> None:
    for seg in segs:
        seg.transcript_zh = None
    for start, end, text in lines:
        mid = (start + end) / 2
        target = next((s for s in segs if s.start <= mid < s.end), segs[-1] if mid >= segs[-1].end else None)
        if target is not None:
            target.transcript_zh = f"{target.transcript_zh} {text}" if target.transcript_zh else text


def transcribe_asset(
    session: Session,
    asset: Asset,
    video: Path,
    storage_dir: Path,
    model_setting: str = "auto",
    transcriber: Callable[[Path, str], list[Line]] = whisper_transcribe,
) -> int | None:
    """받아쓴 문장 수. 소리가 없거나 이미 받아쓴 영상은 None (건너뜀)."""
    out = storage_dir / "frames" / str(asset.id) / "transcript.json"
    if model_setting == "off" or out.exists() or asset.has_audio is False:
        return None
    segs = session.scalars(
        select(FootageSegment).where(FootageSegment.asset_id == asset.id).order_by(FootageSegment.idx)
    ).all()
    if not segs:
        return None
    model = choose_model(model_setting)
    lines = transcriber(video, model)
    assign(lines, segs)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"model": model, "lines": lines}, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    session.flush()
    return len(lines)
