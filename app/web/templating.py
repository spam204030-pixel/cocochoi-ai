"""화면 템플릿 공통 설정."""

from pathlib import Path

from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def won(value) -> str:
    """19800 → '19,800원'"""
    return "" if value is None else f"{int(value):,}원"


templates.env.filters["won"] = won
