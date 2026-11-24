"""FFmpeg 연결 확인과 영상·사진 정보 읽기 (설계서 작업 0-4).

이 단계에서는 정보 읽기만 한다. 자르기·합치기·렌더링은 Phase 3에서 만든다.
FFmpeg 위치: .env 의 FFMPEG_PATH / FFPROBE_PATH → 없으면 PATH에서 찾음.
"""

import json
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from app.core.errors import AppError, ErrorCode

PROBE_TIMEOUT_SEC = 30

WINDOWS_INSTALL_GUIDE = [
    "PowerShell을 열고 다음을 입력합니다: winget install Gyan.FFmpeg",
    "설치가 끝나면 PowerShell을 닫았다가 다시 엽니다.",
    "ffmpeg -version 을 입력해 버전이 나오면 설치 완료입니다.",
    "프로그램을 다시 켭니다 (uv run factory).",
]


@dataclass(frozen=True)
class FFmpegStatus:
    installed: bool
    ffmpeg_path: str | None
    ffprobe_path: str | None
    version: str | None

    @property
    def label(self) -> str:
        return f"정상 (버전 {self.version})" if self.installed else "없음 — 설치 필요"


@dataclass(frozen=True)
class MediaInfo:
    kind: str  # video / image / audio
    duration: float | None  # 초
    width: int | None
    height: int | None
    fps: float | None
    has_audio: bool
    video_codec: str | None
    file_size: int

    def to_dict(self) -> dict:
        return asdict(self)


def _resolve(configured: str | None, name: str) -> str | None:
    if configured:
        path = Path(configured)
        return str(path) if path.is_file() else None
    return shutil.which(name)


def check_ffmpeg(ffmpeg_path: str | None = None, ffprobe_path: str | None = None) -> FFmpegStatus:
    """FFmpeg·ffprobe가 설치되어 있고 실행되는지 확인한다."""
    ffmpeg = _resolve(ffmpeg_path, "ffmpeg")
    ffprobe = _resolve(ffprobe_path, "ffprobe")
    if not ffmpeg or not ffprobe:
        return FFmpegStatus(False, ffmpeg, ffprobe, None)
    try:
        out = subprocess.run(
            [ffmpeg, "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return FFmpegStatus(False, ffmpeg, ffprobe, None)
    if out.returncode != 0:
        return FFmpegStatus(False, ffmpeg, ffprobe, None)
    match = re.search(r"ffmpeg version (\S+)", out.stdout)
    return FFmpegStatus(True, ffmpeg, ffprobe, match.group(1) if match else "알 수 없음")


def _parse_fps(rate: str | None) -> float | None:
    if not rate or rate in {"0/0", "0"}:
        return None
    try:
        num, _, den = rate.partition("/")
        value = float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return None
    return round(value, 3) if value > 0 else None


def _rotation(stream: dict) -> int:
    """휴대폰 세로 영상의 회전 정보. 90·270이면 가로·세로를 바꿔야 실제 화면 크기가 된다."""
    tags_rotate = stream.get("tags", {}).get("rotate")
    if tags_rotate:
        try:
            return abs(int(tags_rotate)) % 360
        except ValueError:
            pass
    for side in stream.get("side_data_list", []) or []:
        if "rotation" in side:
            try:
                return abs(int(float(side["rotation"]))) % 360
            except (TypeError, ValueError):
                pass
    return 0


def probe_media(path: Path, status: FFmpegStatus) -> MediaInfo:
    """영상·사진·음원 파일의 길이, 해상도, fps, 소리 유무를 읽는다."""
    if not status.installed:
        raise AppError(ErrorCode.FFMPEG_MISSING, "ffprobe를 찾을 수 없습니다.")
    path = Path(path)
    if not path.is_file():
        raise AppError(ErrorCode.MEDIA_UNREADABLE, f"파일이 없습니다: {path.name}")

    cmd = [
        status.ffprobe_path,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=PROBE_TIMEOUT_SEC
        )
    except subprocess.TimeoutExpired as exc:
        raise AppError(
            ErrorCode.MEDIA_UNREADABLE, f"파일 정보를 읽는 데 너무 오래 걸립니다: {path.name}"
        ) from exc
    if out.returncode != 0:
        raise AppError(ErrorCode.MEDIA_UNREADABLE, f"영상·사진으로 읽을 수 없는 파일입니다: {path.name}")

    try:
        data = json.loads(out.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise AppError(ErrorCode.MEDIA_UNREADABLE, f"파일 정보를 해석할 수 없습니다: {path.name}") from exc

    streams = data.get("streams", [])
    fmt = data.get("format", {})
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    if video is None and not has_audio:
        raise AppError(ErrorCode.MEDIA_UNREADABLE, f"영상·사진·소리가 들어 있지 않은 파일입니다: {path.name}")

    duration = None
    for raw in (fmt.get("duration"), (video or {}).get("duration")):
        try:
            if raw is not None:
                duration = round(float(raw), 3)
                break
        except ValueError:
            continue

    width = height = fps = codec = None
    kind = "audio"
    if video is not None:
        width, height = video.get("width"), video.get("height")
        if width and height and _rotation(video) in (90, 270):
            width, height = height, width
        codec = video.get("codec_name")
        # 사진: 프레임이 1장뿐이거나 이미지 코덱 (jpg, png, webp 등)
        is_image = (
            codec in {"mjpeg", "png", "webp", "bmp", "tiff", "gif"}
            and (duration is None or duration < 0.1 or str(video.get("nb_frames", "1")) == "1")
        ) or fmt.get("format_name", "").endswith("_pipe")
        kind = "image" if is_image else "video"
        if kind == "video":
            fps = _parse_fps(video.get("avg_frame_rate")) or _parse_fps(video.get("r_frame_rate"))
        else:
            duration = None

    return MediaInfo(
        kind=kind,
        duration=duration,
        width=width,
        height=height,
        fps=fps,
        has_audio=has_audio,
        video_codec=codec,
        file_size=path.stat().st_size,
    )
