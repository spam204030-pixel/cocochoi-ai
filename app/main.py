"""COCOCHOI AI CONTENT FACTORY — 프로그램 시작점.

실행: `uv run factory` → 브라우저에서 http://localhost:8000
"""

import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.db import Database
from app.core.errors import ERRORS, AppError, ErrorCode, error_payload
from app.core.logging import get_logger, setup_logging
from app.core.settings import Settings, get_settings
from app.media.probe import WINDOWS_INSTALL_GUIDE, check_ffmpeg
from app.products.routes import api as products_api
from app.products.routes import pages as products_pages
from app.web.templating import templates

APP_NAME = "COCOCHOI AI CONTENT FACTORY"
APP_VERSION = "0.0.5"


_HTTP_STATUS_TO_CODE = {
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    422: ErrorCode.VALIDATION_ERROR,
}


def _wants_json(request: Request) -> bool:
    """/api/ 주소는 JSON, 화면 주소는 한국어 오류 화면으로 답한다."""
    return request.url.path.startswith("/api/")


def _error_response(request: Request, code: ErrorCode, detail: str = "", error_id: str | None = None):
    status = ERRORS[code].status
    payload = error_payload(code, detail, error_id)
    if _wants_json(request):
        return JSONResponse(payload, status_code=status)
    return templates.TemplateResponse(
        request, "error.html", {"error": payload["error"], "app_name": APP_NAME}, status_code=status
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.ensure_storage()
    logger = setup_logging(settings.logs_dir, settings.log_level)

    app = FastAPI(title=APP_NAME, version=APP_VERSION)
    app.state.settings = settings
    db = Database(settings.db_path)
    db.init()  # DB 파일 생성 + 최신 구조로 맞춤 (기존 데이터 유지)
    app.state.db = db
    ffmpeg = check_ffmpeg(settings.ffmpeg_path, settings.ffprobe_path)
    app.state.ffmpeg = ffmpeg
    log = get_logger("web")

    def health_status() -> dict:
        return {
            "status": "ok",
            "message": "정상",
            "app": APP_NAME,
            "version": APP_VERSION,
            "checks": {
                "storage": "정상" if settings.storage_writable() else "쓰기 불가",
                "db": "정상" if db.is_ok() else "연결 실패",
                "ffmpeg": ffmpeg.label,
                "ai_key": "설정됨" if settings.ai_key_configured else "없음 (Phase 1부터 필요)",
            },
        }

    @app.get("/api/health")
    def api_health() -> dict:
        return health_status()

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "home.html",
            {"health": health_status(), "ffmpeg": ffmpeg, "ffmpeg_guide": WINDOWS_INSTALL_GUIDE},
        )

    app.include_router(products_api)
    app.include_router(products_pages)

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError):
        error_id = uuid.uuid4().hex[:8]
        log.warning("[%s] %s %s → %s %s", error_id, request.method, request.url.path, exc.code, exc.detail)
        return _error_response(request, exc.code, exc.detail, error_id)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException):
        code = _HTTP_STATUS_TO_CODE.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        log.info("%s %s → %s", request.method, request.url.path, exc.status_code)
        return _error_response(request, code, str(exc.detail or ""))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        fields = [".".join(str(p) for p in err.get("loc", [])[1:]) for err in exc.errors()]
        detail = "확인할 칸: " + ", ".join(f for f in fields if f) if fields else ""
        log.info("%s %s → 입력 오류 %s", request.method, request.url.path, detail)
        return _error_response(request, ErrorCode.VALIDATION_ERROR, detail)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        error_id = uuid.uuid4().hex[:8]
        log.exception("[%s] 예상하지 못한 오류: %s %s", error_id, request.method, request.url.path)
        # 원인 상세는 로그에만 남기고 화면에는 오류 번호만 보여준다
        return _error_response(
            request, ErrorCode.INTERNAL_ERROR, f"오류 번호 {error_id}로 로그를 확인하세요.", error_id
        )

    logger.info("프로그램 시작 — 버전 %s, 데이터 폴더 %s", APP_VERSION, settings.storage_dir)
    if ffmpeg.installed:
        logger.info("FFmpeg 확인 — 버전 %s (%s)", ffmpeg.version, ffmpeg.ffmpeg_path)
    else:
        logger.warning("FFmpeg를 찾을 수 없습니다. 영상 기능을 쓰려면 설치가 필요합니다.")
    return app


app = create_app()


def run() -> None:
    """`uv run factory` 명령으로 서버를 켠다."""
    import uvicorn

    settings = get_settings()
    print(
        f"\n  {APP_NAME} 실행 중 → 브라우저에서 http://localhost:{settings.port} 을 여세요 (끄기: Ctrl + C)\n"
    )
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
