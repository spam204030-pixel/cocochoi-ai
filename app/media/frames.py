"""장면별 대표 사진·화질 측정·프레임 격자 (설계서 V4-16 작업 1-3). OpenCV, 무료·로컬.

윈도우 한글 경로 대비: 이미지 저장은 cv2.imencode → 파일 쓰기로 한다.
"""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.core.models import Asset, FootageSegment

THUMB_W = 360
TILE_W = 180
GRID_COLS, GRID_MAX = 4, 12  # 격자 한 장에 4열, 최대 12장면

# 표시 기준 (초기값, Phase 4 실전 테스트에서 조정)
BLUR_BELOW = 60.0
DARK_BELOW, BRIGHT_ABOVE = 50.0, 215.0
SHAKE_ABOVE = 15.0  # 연속 두 프레임의 평균 밝기 차이


def _cv2():
    import cv2

    return cv2


def _resize(img, width):
    cv2 = _cv2()
    h, w = img.shape[:2]
    return cv2.resize(img, (width, max(1, round(h * width / w))), interpolation=cv2.INTER_AREA)


def _write_jpg(path: Path, img) -> None:
    ok, buf = _cv2().imencode(".jpg", img, [int(_cv2().IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        raise AppError(ErrorCode.STORAGE_ERROR, f"이미지 저장 실패: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buf.tobytes())


def _frame_at(cap, sec: float):
    cap.set(_cv2().CAP_PROP_POS_MSEC, max(sec, 0) * 1000)
    ok, frame = cap.read()
    return frame if ok else None


def score(sharpness: float, shake: float, brightness: float) -> int:
    sharp_pts = min(sharpness / 150.0, 1.0) * 60
    if DARK_BELOW <= brightness <= BRIGHT_ABOVE:
        bright_pts = 25.0
    elif brightness < DARK_BELOW:
        bright_pts = 25.0 * brightness / DARK_BELOW
    else:
        bright_pts = 25.0 * max(0.0, (255 - brightness) / (255 - BRIGHT_ABOVE))
    steady_pts = 15 * (1 - min(shake / 20.0, 1.0))
    return round(sharp_pts + bright_pts + steady_pts)


def labels(seg: FootageSegment) -> list[str]:
    out = []
    if seg.sharpness is not None and seg.sharpness < BLUR_BELOW:
        out.append("흐림")
    if seg.brightness is not None and seg.brightness < DARK_BELOW:
        out.append("어두움")
    if seg.brightness is not None and seg.brightness > BRIGHT_ABOVE:
        out.append("너무 밝음")
    if seg.shake is not None and seg.shake > SHAKE_ABOVE:
        out.append("흔들림")
    return out


def measure_segments(session: Session, asset: Asset, video: Path, storage_dir: Path) -> int:
    """측정 안 된 장면만 처리한다. 처리한 장면 수를 돌려준다."""
    cv2 = _cv2()
    segs = session.scalars(
        select(FootageSegment).where(FootageSegment.asset_id == asset.id).order_by(FootageSegment.idx)
    ).all()
    todo = [s for s in segs if s.quality is None]
    if not todo:
        return 0
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise AppError(ErrorCode.MEDIA_UNREADABLE, f"영상을 열 수 없음: {video.name}")
    try:
        for seg in todo:
            mid = _frame_at(cap, seg.start + seg.duration / 2)
            if mid is None:
                continue
            ok, nxt = cap.read()  # 바로 다음 프레임: 짧은 순간의 화면 변화 = 흔들림
            small = _resize(mid, THUMB_W)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            shake = 0.0
            if ok and nxt is not None:
                a, b = (
                    cv2.cvtColor(_resize(f, 90), cv2.COLOR_BGR2GRAY).astype("float32") for f in (mid, nxt)
                )
                shake = float(abs(a - b).mean())
            seg.sharpness = round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 1)
            seg.brightness = round(float(gray.mean()), 1)
            seg.shake = round(shake, 1)
            seg.quality = score(seg.sharpness, seg.shake, seg.brightness)
            rel = Path("frames") / str(asset.id) / f"seg_{seg.idx:03d}.jpg"
            _write_jpg(storage_dir / rel, small)
            seg.thumb_path = rel.as_posix()
    finally:
        cap.release()
    session.flush()
    make_grids(segs, storage_dir / "frames" / str(asset.id), storage_dir)
    return len(todo)


def make_grids(segs: list[FootageSegment], out_dir: Path, storage_dir: Path) -> list[Path]:
    """장면 사진에 번호를 붙여 격자 이미지로 모은다 (Claude 가 한 번에 보는 자료)."""
    import numpy as np

    cv2 = _cv2()
    for old in out_dir.glob("grid_*.jpg"):
        old.unlink()
    tiles = []
    for seg in segs:
        if not seg.thumb_path:
            continue
        data = np.frombuffer((storage_dir / seg.thumb_path).read_bytes(), np.uint8)
        tile = _resize(cv2.imdecode(data, cv2.IMREAD_COLOR), TILE_W)
        cv2.rectangle(tile, (0, 0), (TILE_W, 26), (0, 0, 0), -1)
        text = f"{seg.idx}  {seg.start:.1f}-{seg.end:.1f}s"
        cv2.putText(tile, text, (6, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        tiles.append(tile)
    paths = []
    for g in range(0, len(tiles), GRID_MAX):
        chunk = tiles[g : g + GRID_MAX]
        h = max(t.shape[0] for t in chunk)
        chunk = [cv2.copyMakeBorder(t, 0, h - t.shape[0], 0, 0, cv2.BORDER_CONSTANT) for t in chunk]
        blank = np.zeros_like(chunk[0])
        rows = []
        for r in range(0, len(chunk), GRID_COLS):
            row = chunk[r : r + GRID_COLS]
            row += [blank] * (GRID_COLS - len(row))
            rows.append(np.hstack(row))
        path = out_dir / f"grid_{g // GRID_MAX + 1:02d}.jpg"
        _write_jpg(path, np.vstack(rows))
        paths.append(path)
    return paths
