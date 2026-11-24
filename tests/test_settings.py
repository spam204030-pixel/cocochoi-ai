import pytest

from app.core.settings import DEFAULT_STORAGE_DIR, Settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """설정 테스트는 테스트용 환경 변수 없이, .env 파일 내용만으로 검사한다."""
    for name in ("STORAGE_DIR", "ANTHROPIC_API_KEY", "PORT", "LOG_LEVEL"):
        monkeypatch.delenv(name, raising=False)


def test_default_storage_dir_is_project_storage():
    s = Settings(_env_file=None)
    assert s.storage_dir == DEFAULT_STORAGE_DIR
    assert s.storage_dir.name == "storage"


def test_empty_values_in_env_use_defaults(tmp_path):
    env = tmp_path / ".env"
    env.write_text("ANTHROPIC_API_KEY=\nSTORAGE_DIR=\nLOG_LEVEL=\n", encoding="utf-8")
    s = Settings(_env_file=env)
    assert s.anthropic_api_key is None
    assert s.ai_key_configured is False
    assert s.storage_dir == DEFAULT_STORAGE_DIR
    assert s.log_level == "INFO"


def test_env_file_values_are_read(tmp_path):
    env = tmp_path / ".env"
    target = tmp_path / "내 데이터"  # 한글 폴더 이름
    env.write_text(f"ANTHROPIC_API_KEY=test-key-123\nSTORAGE_DIR={target}\nPORT=8123\n", encoding="utf-8")
    s = Settings(_env_file=env)
    assert s.ai_key_configured is True
    assert s.storage_dir == target
    assert s.port == 8123


def test_api_key_is_not_shown_in_text():
    s = Settings(_env_file=None, anthropic_api_key="secret-value-xyz")
    assert "secret-value-xyz" not in repr(s)
    assert "secret-value-xyz" not in str(s.model_dump())


def test_ensure_storage_creates_folders(tmp_path):
    s = Settings(_env_file=None, storage_dir=tmp_path / "새폴더" / "storage")
    s.ensure_storage()
    assert s.storage_dir.is_dir()
    assert s.logs_dir.is_dir()
    assert s.storage_writable() is True
