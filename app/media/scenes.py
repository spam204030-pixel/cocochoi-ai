"""장면 나누기 (설계서 V4-16 작업 1-2). PySceneDetect 사용, 무료·로컬."""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.core.models import Asset, FootageSegment

MIN_SCENE_SEC = 0.5  # 이보다 짧은 장면은 앞 장면에 합친다
THRESHOLD = 27.0  # 장면 전환 민감도 (PySceneDetect 기본값)


def detect_scenes(path: Path, duration: float | None = None) -> list[tuple[float, float]]:
    """(시작, 끝) 초 목록. 경계가 없으면 영상 전체를 장면 1개로."""
    from scenedetect import ContentDetector, detect

    try:
        scenes = detect(str(path), ContentDetector(threshold=THRESHOLD), show_progress=False)
    except Exception as exc:  # 깨진 파일 등
        raise AppError(ErrorCode.MEDIA_UNREADABLE, f"장면 나누기 실패: {path.name}") from exc
    spans = [(s.seconds, e.seconds) for s, e in scenes]
    if not spans:
        return [(0.0, round(duration or 0.0, 3))]
    merged: list[list[float]] = []
    for start, end in spans:
        if merged and end - start < MIN_SCENE_SEC:
            merged[-1][1] = end
        else:
            merged.append([start, end])
    if len(merged) > 1 and merged[0][1] - merged[0][0] < MIN_SCENE_SEC:  # 첫 장면이 짧으면 다음과 합침
        merged[1][0] = merged[0][0]
        merged.pop(0)
    return [(round(s, 3), round(e, 3)) for s, e in merged]


def segment_asset(session: Session, asset: Asset, path: Path) -> int:
    """영상 하나의 장면을 저장한다. 이미 나눈 영상은 다시 하지 않는다. 장면 수를 돌려준다."""
    existing = session.scalars(select(FootageSegment).where(FootageSegment.asset_id == asset.id)).all()
    if existing:
        return len(existing)
    spans = detect_scenes(path, asset.duration)
    for i, (start, end) in enumerate(spans, 1):
        session.add(
            FootageSegment(asset_id=asset.id, idx=i, start=start, end=end, duration=round(end - start, 3))
        )
    session.flush()
    return len(spans)


def segments_for(session: Session, asset_ids: list[int]) -> dict[int, list[FootageSegment]]:
    rows = session.scalars(
        select(FootageSegment)
        .where(FootageSegment.asset_id.in_(asset_ids))
        .order_by(FootageSegment.asset_id, FootageSegment.idx)
    )
    out: dict[int, list[FootageSegment]] = {}
    for row in rows:
        out.setdefault(row.asset_id, []).append(row)
    return out
