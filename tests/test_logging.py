from app.core.logging import LOG_FILE_NAME, get_logger, mask_secrets, setup_logging
from tests.conftest import FAKE_KEY


def _read_log(settings) -> str:
    for handler in get_logger().handlers:
        handler.flush()
    return (settings.logs_dir / LOG_FILE_NAME).read_text(encoding="utf-8")


def test_log_file_is_created_on_start(test_app, tmp_settings):
    log_text = _read_log(tmp_settings)
    assert "프로그램 시작" in log_text


def test_unexpected_error_is_logged_with_error_id(client, tmp_settings):
    res = client.get("/api/_test/crash")
    error_id = res.json()["error"]["error_id"]
    log_text = _read_log(tmp_settings)
    assert error_id in log_text
    assert "RuntimeError" in log_text  # 원인은 로그에 남는다


def test_api_keys_are_masked_in_log(client, tmp_settings):
    client.get("/api/_test/crash")  # 오류 메시지 안에 가짜 키가 들어 있음
    log_text = _read_log(tmp_settings)
    assert FAKE_KEY not in log_text
    assert "[가려진 키]" in log_text


def test_mask_secrets():
    assert mask_secrets(f"key={FAKE_KEY}") == "key=[가려진 키]"
    assert mask_secrets("일반 문장") == "일반 문장"


def test_setup_logging_twice_does_not_duplicate(tmp_path):
    logger = setup_logging(tmp_path / "logs")
    logger = setup_logging(tmp_path / "logs")
    assert len(logger.handlers) == 2  # 파일 1 + 화면 1
