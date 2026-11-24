"""사진·영상 업로드 (설계서 작업 0-6).

저장 규칙: storage/assets/<id>/original.<확장자> + thumb.jpg
- DB에는 파일이 아니라 storage/ 기준 경로만 저장한다
- 원래 파일 이름(한글 포함)은 DB에 기록하고, 디스크에는 영문 이름으로 저장한다 (윈도우 경로 문제 방지)
- 같은 파일(내용 해시 동일)은 두 번 저장하지 않는다
"""

import hashlib
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger
from app.core.models import Asset, ProjectAsset
from app.core.settings import Settings
from app.media.probe import FFmpegStatus, probe_media

log = get_logger("assets")

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm"}
VIDEO_KINDS = {"footage", "own_clip"}  # 영상 소재(샤오홍슈 등) / 직접 촬영
THUMB_WIDTH = 320
CHUNK = 1024 * 1024


@dataclass
class UploadResult:
    filename: str
    ok: bool
    asset_id: int | None = None
    message: str = ""
    existing_asset_id: int | None = None


def _ext(filename: str) -> str:
    return Path(filename).suffix.lower()


def _save_temp(stream: BinaryIO, settings: Settings) -> tuple[Path, str, int]:
    """임시 폴더에 저장하면서 내용 해시와 크기를 계산한다. 크기 제한을 넘으면 중단."""
    limit = settings.max_upload_mb * 1024 * 1024
    tmp = settings.tmp_dir / f"upload-{uuid.uuid4().hex}"
    sha = hashlib.sha256()
    size = 0
    try:
        with tmp.open("wb") as out:
            while chunk := stream.read(CHUNK):
                size += len(chunk)
                if size > limit:
                    raise AppError(ErrorCode.FILE_TOO_LARGE, f"최대 {settings.max_upload_mb}MB")
                sha.update(chunk)
                out.write(chunk)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return tmp, sha.hexdigest(), size


def _make_thumbnail(source: Path, target: Path, status: FFmpegStatus, duration: float | None) -> bool:
    seek = min(1.0, duration * 0.1) if duration else 0
    cmd = [status.ffmpeg_path, "-y", "-v", "error"]
    if duration:
        cmd += ["-ss", f"{seek:.2f}"]
    cmd += ["-i", str(source), "-frames:v", "1", "-vf", f"scale={THUMB_WIDTH}:-2", str(target)]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and target.is_file()


def save_upload(
    session: Session,
    settings: Settings,
    ffmpeg: FFmpegStatus,
    *,
    filename: str,
    stream: BinaryIO,
    product_id: int | None,
    video_kind: str = "footage",
    source_url: str | None = None,
    source_memo: str | None = None,
) -> Asset:
    filename = Path(filename or "파일").name
    ext = _ext(filename)
    if ext not in PHOTO_EXTS | VIDEO_EXTS:
        raise AppError(ErrorCode.UNSUPPORTED_FILE, filename)
    if not ffmpeg.installed:
        raise AppError(ErrorCode.FFMPEG_MISSING)

    tmp, file_hash, size = _save_temp(stream, settings)
    try:
        existing = session.scalar(select(Asset).where(Asset.file_hash == file_hash))
        if existing is not None:
            raise AppError(ErrorCode.ASSET_DUPLICATE, f"{filename} = 기존 파일 #{existing.id}")

        info = probe_media(tmp, ffmpeg)  # 읽을 수 없는 파일이면 여기서 한국어 오류
        if ext in VIDEO_EXTS and info.kind != "video":
            raise AppError(ErrorCode.MEDIA_UNREADABLE, f"영상으로 읽을 수 없습니다: {filename}")
        if ext in PHOTO_EXTS and info.kind != "image":
            raise AppError(ErrorCode.MEDIA_UNREADABLE, f"사진으로 읽을 수 없습니다: {filename}")

        kind = (
            "product_photo"
            if info.kind == "image"
            else (video_kind if video_kind in VIDEO_KINDS else "footage")
        )
        asset = Asset(
            product_id=product_id,
            kind=kind,
            path="",
            original_name=filename,
            source_url=(source_url or "").strip() or None,
            source_memo=(source_memo or "").strip() or None,
            duration=info.duration,
            width=info.width,
            height=info.height,
            fps=info.fps,
            has_audio=info.has_audio,
            file_size=size,
            file_hash=file_hash,
        )
        session.add(asset)
        session.flush()  # 번호(id) 받기

        folder = settings.assets_dir / str(asset.id)
        folder.mkdir(parents=True, exist_ok=True)
        final = folder / f"original{ext}"
        shutil.move(str(tmp), final)
        asset.path = final.relative_to(settings.storage_dir).as_posix()

        if not _make_thumbnail(final, folder / "thumb.jpg", ffmpeg, info.duration):
            log.warning("썸네일 생성 실패 #%s %s", asset.id, filename)

        session.commit()
        log.info("업로드 #%s %s (%s, %.1fMB)", asset.id, filename, kind, size / 1024 / 1024)
        return asset
    except BaseException:
        session.rollback()
        tmp.unlink(missing_ok=True)
        raise


def asset_file(settings: Settings, asset: Asset) -> Path:
    return settings.storage_dir / asset.path


def thumb_file(settings: Settings, asset: Asset) -> Path:
    return settings.assets_dir / str(asset.id) / "thumb.jpg"


def list_assets(session: Session, product_id: int) -> list[Asset]:
    stmt = select(Asset).where(Asset.product_id == product_id).order_by(Asset.id)
    return list(session.scalars(stmt))


def get_asset(session: Session, asset_id: int) -> Asset:
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise AppError(ErrorCode.NOT_FOUND, f"파일 번호 {asset_id}")
    return asset


def update_source(session: Session, asset_id: int, source_url: str | None, source_memo: str | None) -> Asset:
    asset = get_asset(session, asset_id)
    asset.source_url = (source_url or "").strip() or None
    asset.source_memo = (source_memo or "").strip() or None
    session.commit()
    return asset


def delete_asset(session: Session, settings: Settings, asset_id: int) -> None:
    asset = get_asset(session, asset_id)
    used = session.scalar(
        select(func.count()).select_from(ProjectAsset).where(ProjectAsset.asset_id == asset_id)
    )
    if used:
        raise AppError(ErrorCode.ASSET_IN_USE, f"파일 #{asset_id}을 쓰는 콘텐츠 {used}개")
    folder = settings.assets_dir / str(asset.id)
    session.delete(asset)
    session.commit()
    if folder.is_dir() and folder.parent == settings.assets_dir:
        shutil.rmtree(folder, ignore_errors=True)
    log.info("파일 삭제 #%s %s", asset_id, asset.original_name)


def upload_many(session, settings, ffmpeg, files, **kwargs) -> list[UploadResult]:
    """여러 파일을 올릴 때 한 파일이 실패해도 나머지는 계속 올린다."""
    results = []
    for upload in files:
        name = Path(upload.filename or "파일").name
        try:
            asset = save_upload(session, settings, ffmpeg, filename=name, stream=upload.file, **kwargs)
            results.append(UploadResult(name, True, asset.id, "올림"))
        except AppError as exc:
            existing = None
            if exc.code == ErrorCode.ASSET_DUPLICATE and "#" in exc.detail:
                existing = int(exc.detail.rsplit("#", 1)[1])
            results.append(UploadResult(name, False, None, exc.info.message, existing))
    return results
