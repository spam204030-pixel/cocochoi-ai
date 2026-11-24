import subprocess

import pytest
from fastapi.testclient import TestClient

from app.core.errors import AppError, ErrorCode
from app.main import create_app
from app.media.probe import FFmpegStatus, check_ffmpeg, probe_media

FFMPEG = check_ffmpeg()
needs_ffmpeg = pytest.mark.skipif(not FFMPEG.installed, reason="이 컴퓨터에 FFmpeg가 없음")


def _make(path, *args):
    subprocess.run([FFMPEG.ffmpeg_path, "-y", "-v", "error", *args, str(path)], check=True)
    return path


@pytest.fixture(scope="module")
def samples(tmp_path_factory):
    d = tmp_path_factory.mktemp("샘플")  # 한글 폴더 이름
    return {
        # 세로 9:16 영상 2초, 30fps, 소리 있음
        "video": _make(
            d / "세로영상.mp4",
            "-f", "lavfi", "-i", "color=c=red:s=360x640:r=30:d=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        ),
        # 소리 없는 영상 1초, 25fps
        "silent": _make(
            d / "무음.mp4",
            "-f", "lavfi", "-i", "color=c=blue:s=640x360:r=25:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        ),
        "photo": _make(d / "제품사진.jpg", "-f", "lavfi", "-i", "color=c=white:s=800x1000", "-frames:v", "1"),
        "broken": _write(d / "깨진파일.mp4", b"this is not a video"),
    }  # fmt: skip


def _write(path, data):
    path.write_bytes(data)
    return path


@needs_ffmpeg
def test_check_ffmpeg_finds_installed():
    assert FFMPEG.installed and FFMPEG.version
    assert FFMPEG.label.startswith("정상")


def test_check_ffmpeg_reports_missing_with_wrong_path(tmp_path):
    status = check_ffmpeg(str(tmp_path / "없는" / "ffmpeg.exe"), str(tmp_path / "없는" / "ffprobe.exe"))
    assert status.installed is False
    assert "설치 필요" in status.label


@needs_ffmpeg
def test_probe_vertical_video_with_audio(samples):
    info = probe_media(samples["video"], FFMPEG)
    assert info.kind == "video"
    assert (info.width, info.height) == (360, 640)
    assert info.duration == pytest.approx(2.0, abs=0.1)
    assert info.fps == pytest.approx(30.0, abs=0.1)
    assert info.has_audio is True
    assert info.file_size > 0


@needs_ffmpeg
def test_probe_silent_video(samples):
    info = probe_media(samples["silent"], FFMPEG)
    assert info.has_audio is False
    assert info.fps == pytest.approx(25.0, abs=0.1)


@needs_ffmpeg
def test_probe_photo(samples):
    info = probe_media(samples["photo"], FFMPEG)
    assert info.kind == "image"
    assert (info.width, info.height) == (800, 1000)
    assert info.duration is None and info.fps is None


@needs_ffmpeg
def test_probe_broken_file_gives_korean_error(samples):
    with pytest.raises(AppError) as exc:
        probe_media(samples["broken"], FFMPEG)
    assert exc.value.code == ErrorCode.MEDIA_UNREADABLE
    assert "깨진파일.mp4" in exc.value.detail


@needs_ffmpeg
def test_probe_missing_file(tmp_path):
    with pytest.raises(AppError) as exc:
        probe_media(tmp_path / "없음.mp4", FFMPEG)
    assert exc.value.code == ErrorCode.MEDIA_UNREADABLE


def test_probe_without_ffmpeg_raises(tmp_path):
    with pytest.raises(AppError) as exc:
        probe_media(tmp_path / "a.mp4", FFmpegStatus(False, None, None, None))
    assert exc.value.code == ErrorCode.FFMPEG_MISSING


@needs_ffmpeg
def test_health_and_home_show_ffmpeg(client):
    assert client.get("/api/health").json()["checks"]["ffmpeg"].startswith("정상")
    assert "FFmpeg): 정상" in client.get("/").text


def test_home_shows_install_guide_when_missing(tmp_settings, tmp_path):
    tmp_settings.ffmpeg_path = str(tmp_path / "없음.exe")
    tmp_settings.ffprobe_path = str(tmp_path / "없음.exe")
    client = TestClient(create_app(tmp_settings))
    assert "없음 — 설치 필요" in client.get("/api/health").json()["checks"]["ffmpeg"]
    page = client.get("/").text
    assert "FFmpeg)을 설치해 주세요" in page
    assert "winget install Gyan.FFmpeg" in page
