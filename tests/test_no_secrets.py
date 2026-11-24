"""API 키가 코드나 문서에 들어가지 않았는지 검사한다 (설계서 13-2, CLAUDE.md 규칙 5)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "storage", "__pycache__", ".ruff_cache", ".pytest_cache", "node_modules"}
KEY_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),  # Anthropic
    re.compile(r"sk-[A-Za-z0-9]{32,}"),  # OpenAI 형식
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),  # Google
]


def test_no_api_keys_in_repository():
    found = []
    for path in ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts) or not path.is_file():
            continue
        if path.name == ".env":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern in KEY_PATTERNS:
            if pattern.search(text):
                found.append(str(path.relative_to(ROOT)))
    assert not found, f"API 키로 보이는 문자열이 있습니다: {found}"


def test_env_file_is_ignored_by_git():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore.splitlines()
