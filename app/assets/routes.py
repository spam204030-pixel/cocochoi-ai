"""사진·영상 업로드 API와 화면 동작."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.assets import service
from app.core.errors import AppError, ErrorCode
from app.products.routes import get_session
from app.products.service import get_product

api = APIRouter(tags=["사진·영상"])
pages = APIRouter()


def _ctx(request: Request):
    return request.app.state.settings, request.app.state.ffmpeg


def asset_dict(a) -> dict:
    return {
        "id": a.id,
        "product_id": a.product_id,
        "kind": a.kind,
        "original_name": a.original_name,
        "duration": a.duration,
        "width": a.width,
        "height": a.height,
        "fps": a.fps,
        "has_audio": a.has_audio,
        "file_size": a.file_size,
        "source_url": a.source_url,
        "source_memo": a.source_memo,
        "thumb_url": f"/media/{a.id}/thumb",
        "file_url": f"/media/{a.id}/file",
    }


# ---------- API ----------


@api.post("/api/products/{product_id}/assets")
def api_upload(
    request: Request,
    product_id: int,
    files: list[UploadFile] = File(...),
    video_kind: str = Form("footage"),
    source_url: str = Form(""),
    source_memo: str = Form(""),
    session: Session = Depends(get_session),
):
    get_product(session, product_id)
    settings, ffmpeg = _ctx(request)
    results = service.upload_many(
        session,
        settings,
        ffmpeg,
        files,
        product_id=product_id,
        video_kind=video_kind,
        source_url=source_url,
        source_memo=source_memo,
    )
    return {"results": [asdict(r) for r in results], "ok_count": sum(r.ok for r in results)}


@api.get("/api/products/{product_id}/assets")
def api_list(product_id: int, session: Session = Depends(get_session)):
    get_product(session, product_id)
    return [asset_dict(a) for a in service.list_assets(session, product_id)]


@api.patch("/api/assets/{asset_id}")
def api_update(asset_id: int, payload: dict, session: Session = Depends(get_session)):
    asset = service.update_source(session, asset_id, payload.get("source_url"), payload.get("source_memo"))
    return asset_dict(asset)


@api.delete("/api/assets/{asset_id}", status_code=204)
def api_delete(request: Request, asset_id: int, session: Session = Depends(get_session)):
    service.delete_asset(session, request.app.state.settings, asset_id)
    return Response(status_code=204)


# ---------- 파일 보기 (DB 번호로만 찾으므로 storage 밖 파일은 열 수 없음) ----------


@api.get("/media/{asset_id}/thumb")
def media_thumb(request: Request, asset_id: int, session: Session = Depends(get_session)):
    asset = service.get_asset(session, asset_id)
    path = service.thumb_file(request.app.state.settings, asset)
    if not path.is_file():
        raise AppError(ErrorCode.NOT_FOUND, "썸네일 없음")
    return FileResponse(path, media_type="image/jpeg")


@api.get("/media/segments/{segment_id}/thumb")
def segment_thumb(request: Request, segment_id: int, session: Session = Depends(get_session)):
    from app.core.models import FootageSegment

    seg = session.get(FootageSegment, segment_id)
    path = request.app.state.settings.storage_dir / seg.thumb_path if seg and seg.thumb_path else None
    if path is None or not path.is_file():
        raise AppError(ErrorCode.NOT_FOUND, "장면 사진 없음")
    return FileResponse(path, media_type="image/jpeg")


@api.get("/media/{asset_id}/file")
def media_file(request: Request, asset_id: int, session: Session = Depends(get_session)):
    asset = service.get_asset(session, asset_id)
    path = service.asset_file(request.app.state.settings, asset)
    if not path.is_file():
        raise AppError(ErrorCode.NOT_FOUND, "파일 없음")
    return FileResponse(path, filename=asset.original_name)


# ---------- 화면 동작 (자바스크립트가 꺼져 있어도 동작) ----------


@pages.post("/products/{product_id}/upload")
def page_upload(
    request: Request,
    product_id: int,
    files: list[UploadFile] = File(...),
    video_kind: str = Form("footage"),
    source_url: str = Form(""),
    source_memo: str = Form(""),
    session: Session = Depends(get_session),
):
    data = api_upload(request, product_id, files, video_kind, source_url, source_memo, session)
    return RedirectResponse(f"/products/{product_id}?uploaded={data['ok_count']}#assets", status_code=303)


@pages.post("/assets/{asset_id}/source")
def page_update_source(
    asset_id: int,
    source_url: str = Form(""),
    source_memo: str = Form(""),
    session: Session = Depends(get_session),
):
    asset = service.update_source(session, asset_id, source_url, source_memo)
    return RedirectResponse(f"/products/{asset.product_id}?saved=1#asset-{asset_id}", status_code=303)


@pages.post("/assets/{asset_id}/delete")
def page_delete(request: Request, asset_id: int, session: Session = Depends(get_session)):
    asset = service.get_asset(session, asset_id)
    product_id = asset.product_id
    try:
        service.delete_asset(session, request.app.state.settings, asset_id)
    except AppError as exc:
        if exc.code == ErrorCode.ASSET_IN_USE:
            return RedirectResponse(f"/products/{product_id}?error=asset_in_use#assets", status_code=303)
        raise
    return RedirectResponse(f"/products/{product_id}?asset_deleted=1#assets", status_code=303)
