"""프로그램 설정 — `.env` 파일을 읽고, 프로그램 데이터 폴더(storage/)를 준비한다.

- API 키는 `.env`에서만 읽는다. 화면·로그에는 "설정됨 / 없음"만 표시한다.
- 경로는 pathlib로 다룬다 (윈도우·맥 공통).
"""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STORAGE_DIR = PROJECT_ROOT / "storage"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # AI 공급자 키 (Phase 1부터 사용). 값이 비어 있으면 None
    anthropic_api_key: SecretStr | None = None

    # 프로그램 데이터 폴더. 비워두면 프로젝트 안의 storage/
    storage_dir: Path = DEFAULT_STORAGE_DIR

    # 서버 주소
    host: str = "127.0.0.1"
    port: int = 8000

    # 로그 수준 (DEBUG / INFO / WARNING / ERROR)
    log_level: str = "INFO"

    @field_validator("anthropic_api_key", mode="before")
    @classmethod
    def _empty_key_is_none(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value

    @field_validator("storage_dir", mode="before")
    @classmethod
    def _empty_storage_is_default(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            return DEFAULT_STORAGE_DIR
        return value

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        value = value.strip().upper()
        if value not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
            return "INFO"
        return value

    @property
    def logs_dir(self) -> Path:
        return self.storage_dir / "logs"

    @property
    def ai_key_configured(self) -> bool:
        return self.anthropic_api_key is not None

    def ensure_storage(self) -> None:
        """storage/ 와 storage/logs/ 폴더가 없으면 만든다."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def storage_writable(self) -> bool:
        """storage/ 폴더에 실제로 쓸 수 있는지 확인한다."""
        probe = self.storage_dir / ".write_test"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return True
        except OSError:
            return False


@lru_cache
def get_settings() -> Settings:
    return Settings()
