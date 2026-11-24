"""로그 시스템 — 프로그램 기록을 storage/logs/factory.log 에 남긴다.

- 파일이 5MB가 넘으면 새 파일로 넘기고, 최근 5개까지 보관한다.
- API 키처럼 보이는 문자열은 로그에 쓰기 전에 가린다.
- 한글이 깨지지 않도록 UTF-8로 저장한다.
"""

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "factory"
LOG_FILE_NAME = "factory.log"
LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"

_SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
]


def mask_secrets(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[가려진 키]", text)
    return text


class SecretMaskingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return mask_secrets(super().format(record))


def setup_logging(logs_dir: Path, level: str = "INFO") -> logging.Logger:
    """로그 기록을 준비한다. 여러 번 불러도 기록이 중복되지 않는다."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    formatter = SecretMaskingFormatter(LOG_FORMAT)

    file_handler = RotatingFileHandler(
        logs_dir / LOG_FILE_NAME, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


def get_logger(name: str = "") -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{name}" if name else LOGGER_NAME)
