"""콘텐츠 프로젝트 API(/api/projects)와 화면(/projects)."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.assets.service import list_assets
from app.core.errors import AppError
from app.products.routes import get_session
from app.products.service import get_product, list_products
from app.projects import service
from app.projects.schemas import (
    AD_MODES,
    FIELD_LABELS,
    LENGTHS,
    NARRATION_MODES,
    PLATFORMS,
    PRESETS,
    ProjectCreate,
    ProjectSettings,
    ProjectUpdate,
)
from app.web.templating import templates

api = APIRouter(prefix="/api/projects", tags=["콘텐츠 프로젝트"])
pages = APIRouter(prefix="/projects")

CHOICES = {
    "lengths": LENGTHS,
    "presets": PRESETS,
    "platforms": PLATFORMS,
    "narration_modes": NARRATION_MODES,
    "ad_modes": AD_MODES,
}


def project_dict(p, asset_ids: list[int]) -> dict:
    keys = (
        "id product_id title target_length style_preset platforms narration_mode ad_mode auto_mode "
        "budget_limit quality_threshold max_fix_rounds board_status status"
    ).split()
    data = {k: getattr(p, k) for k in keys}
    data["asset_ids"] = asset_ids
    data["created_at"] = p.created_at.isoformat()
    return data


# ---------- API ----------


@api.get("")
def api_list(session: Session = Depends(get_session)):
    return [project_dict(p, service.project_asset_ids(session, p.id)) for p in service.list_projects(session)]


@api.post("", status_code=201)
def api_create(data: ProjectCreate, session: Session = Depends(get_session)):
    project = service.create_project(session, data)
    return project_dict(project, service.project_asset_ids(session, project.id))


@api.get("/{project_id}")
def api_get(project_id: int, session: Session = Depends(get_session)):
    project = service.get_project(session, project_id)
    return project_dict(project, service.project_asset_ids(session, project_id))


@api.patch("/{project_id}")
def api_update(project_id: int, data: ProjectUpdate, session: Session = Depends(get_session)):
    project = service.update_project(session, project_id, data)
    return project_dict(project, service.project_asset_ids(session, project_id))


# ---------- 화면 ----------


async def _read_form(request: Request) -> dict:
    form = await request.form()
    return {
        "product_id": form.get("product_id") or None,
        "title": form.get("title", ""),
        "target_length": form.get("target_length", "20"),
        "style_preset": form.get("style_preset", "auto"),
        "platforms": form.getlist("platforms"),
        "narration_mode": form.get("narration_mode", "tts"),
        "ad_mode": form.get("ad_mode", "none"),
        "auto_mode": form.get("auto_mode") == "on",
        "budget_limit": form.get("budget_limit", ""),
        "asset_ids": [int(a) for a in form.getlist("asset_ids") if str(a).isdigit()],
    }


def _errors(exc: ValidationError) -> dict[str, str]:
    errors = {}
    for err in exc.errors():
        field = str(err["loc"][0]) if err.get("loc") else ""
        if err["type"].startswith("int_") or err["type"] in ("greater_than_equal", "less_than_equal"):
            msg = f"{FIELD_LABELS.get(field, field)}은(는) 0 이상의 숫자(원)로 입력해 주세요."
        elif err["type"] == "missing":
            msg = f"{FIELD_LABELS.get(field, field)}을(를) 골라 주세요."
        else:
            msg = str(err.get("msg", "")).removeprefix("Value error, ")
        errors.setdefault(field, msg)
    return errors


def _render_form(request, session, values, errors, project=None, status_code=200):
    product_id = values.get("product_id")
    product = get_product(session, int(product_id)) if product_id else None
    return templates.TemplateResponse(
        request,
        "projects/form.html",
        {
            "values": values,
            "errors": errors,
            "project": project,
            "product": product,
            "products": list_products(session) if project is None else [],
            "assets": list_assets(session, product.id) if product else [],
            **CHOICES,
        },
        status_code=status_code,
    )


@pages.get("", response_class=HTMLResponse)
def page_list(request: Request, session: Session = Depends(get_session)):
    projects = service.list_projects(session)
    names = {p.id: p.name for p in list_products(session, limit=10_000)}
    return templates.TemplateResponse(
        request, "projects/list.html", {"projects": projects, "product_names": names, **CHOICES}
    )


@pages.get("/new", response_class=HTMLResponse)
def page_new(request: Request, product_id: int | None = None, session: Session = Depends(get_session)):
    values = ProjectSettings().model_dump()
    values["product_id"] = product_id
    if product_id:
        values["asset_ids"] = [a.id for a in list_assets(session, product_id)]  # 기본: 모두 사용
    return _render_form(request, session, values, {})


@pages.post("/new", response_class=HTMLResponse)
async def page_create(request: Request, session: Session = Depends(get_session)):
    values = await _read_form(request)
    try:
        data = ProjectCreate(**values)
        project = service.create_project(session, data)
    except ValidationError as exc:
        return _render_form(request, session, values, _errors(exc), status_code=422)
    except AppError as exc:
        return _render_form(
            request, session, values, {"asset_ids": exc.info.message + " " + exc.detail}, status_code=422
        )
    return RedirectResponse(f"/projects/{project.id}?saved=1", status_code=303)


@pages.get("/{project_id}", response_class=HTMLResponse)
def page_detail(request: Request, project_id: int, session: Session = Depends(get_session)):
    project = service.get_project(session, project_id)
    return templates.TemplateResponse(
        request,
        "projects/detail.html",
        {
            "project": project,
            "product": get_product(session, project.product_id),
            "assets": service.project_assets(session, project_id),
            "saved": request.query_params.get("saved"),
            **CHOICES,
        },
    )


@pages.get("/{project_id}/edit", response_class=HTMLResponse)
def page_edit(request: Request, project_id: int, session: Session = Depends(get_session)):
    project = service.get_project(session, project_id)
    values = project_dict(project, service.project_asset_ids(session, project_id))
    values["budget_limit"] = "" if project.budget_limit is None else project.budget_limit
    return _render_form(request, session, values, {}, project)


@pages.post("/{project_id}/edit", response_class=HTMLResponse)
async def page_update(request: Request, project_id: int, session: Session = Depends(get_session)):
    project = service.get_project(session, project_id)
    values = await _read_form(request)
    values["product_id"] = project.product_id
    try:
        data = ProjectUpdate(**{k: v for k, v in values.items() if k != "product_id"})
        service.update_project(session, project_id, data)
    except ValidationError as exc:
        return _render_form(request, session, values, _errors(exc), project, status_code=422)
    except AppError as exc:
        session.rollback()
        return _render_form(
            request,
            session,
            values,
            {"asset_ids": exc.info.message + " " + exc.detail},
            project,
            status_code=422,
        )
    return RedirectResponse(f"/projects/{project_id}?saved=1", status_code=303)
