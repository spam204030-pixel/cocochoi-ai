"""화면 템플릿 공통 설정."""

from pathlib import Path

from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def won(value) -> str:
    """19800 → '19,800원'"""
    return "" if value is None else f"{int(value):,}원"


def seconds(value) -> str:
    """20.8 → '20.8초'"""
    return "" if value is None else f"{value:.1f}초"


def megabytes(value) -> str:
    return "" if value is None else f"{value / 1024 / 1024:.1f}MB"


templates.env.filters["won"] = won
templates.env.filters["seconds"] = seconds
templates.env.filters["mb"] = megabytes
