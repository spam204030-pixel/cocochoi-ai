"""COCOCHOI AI CONTENT FACTORY — 프로그램 시작점.

실행: `uv run factory` → 브라우저에서 http://localhost:8000
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

APP_NAME = "COCOCHOI AI CONTENT FACTORY"
APP_VERSION = "0.0.1"

TEMPLATES_DIR = Path(__file__).parent / "web" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app = FastAPI(title=APP_NAME, version=APP_VERSION)


def health_status() -> dict:
    """프로그램 상태. 이후 작업(0-3 DB, 0-4 FFmpeg)에서 검사 항목이 추가된다."""
    return {
        "status": "ok",
        "message": "정상",
        "app": APP_NAME,
        "version": APP_VERSION,
    }


@app.get("/api/health")
def api_health() -> dict:
    return health_status()


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "home.html", {"health": health_status()})


def run() -> None:
    """`uv run factory` 명령으로 서버를 켠다."""
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    run()
