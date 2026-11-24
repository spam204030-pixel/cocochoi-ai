import os
import tempfile

# 테스트 중에는 실제 storage/ 대신 임시 폴더를 쓴다 (프로그램 본체를 불러오기 전에 설정)
os.environ["STORAGE_DIR"] = tempfile.mkdtemp(prefix="factory-test-")

import pytest
from fastapi.testclient import TestClient

from app.core.errors import AppError, ErrorCode
from app.core.settings import Settings
from app.main import create_app

# 로그 가림 테스트용 가짜 키. 키 유출 검사에 걸리지 않도록 실행 중에 조합한다
FAKE_KEY = "sk-" + "ant-" + "abcdefghijklmnop1234"


@pytest.fixture
def tmp_settings(tmp_path):
    """테스트마다 임시 폴더를 데이터 폴더로 쓴다 (실제 storage/는 건드리지 않음)."""
    return Settings(
        _env_file=None,
        storage_dir=tmp_path / "storage",
        anthropic_api_key=None,
        worker_enabled=False,  # 테스트는 작업자를 직접 실행
        fake_step_seconds=0,
    )


@pytest.fixture
def test_app(tmp_settings):
    app = create_app(tmp_settings)

    # 오류 처리 확인용 테스트 전용 주소 (실제 프로그램에는 없음)
    @app.get("/api/_test/app-error")
    def _api_app_error():
        raise AppError(ErrorCode.AI_KEY_MISSING, "테스트용")

    @app.get("/api/_test/crash")
    def _api_crash():
        raise RuntimeError(f"테스트용 예상하지 못한 오류 {FAKE_KEY}")

    @app.get("/_test/crash")
    def _page_crash():
        raise RuntimeError("테스트용 화면 오류")

    @app.get("/api/_test/number")
    def _api_number(n: int):
        return {"n": n}

    return app


@pytest.fixture
def client(test_app):
    return TestClient(test_app, raise_server_exceptions=False)
