"""제품 API(/api/products)와 화면(/products)."""

from collections.abc import Iterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.products import service
from app.products.schemas import FIELD_LABELS, ProductCreate, ProductOut, ProductUpdate
from app.web.templating import templates


def get_session(request: Request) -> Iterator[Session]:
    yield from request.app.state.db.session()


api = APIRouter(prefix="/api/products", tags=["제품"])
pages = APIRouter(prefix="/products")

FORM_FIELDS = ("name", "category", "price", "purchase_url", "description", "features", "detail_text")


# ---------- API ----------


@api.get("", response_model=list[ProductOut])
def api_list(q: str | None = None, session: Session = Depends(get_session)):
    return service.list_products(session, q)


@api.post("", response_model=ProductOut, status_code=201)
def api_create(data: ProductCreate, session: Session = Depends(get_session)):
    return service.create_product(session, data)


@api.get("/{product_id}", response_model=ProductOut)
def api_get(product_id: int, session: Session = Depends(get_session)):
    return service.get_product(session, product_id)


@api.patch("/{product_id}", response_model=ProductOut)
def api_update(product_id: int, data: ProductUpdate, session: Session = Depends(get_session)):
    return service.update_product(session, product_id, data)


@api.delete("/{product_id}", status_code=204)
def api_delete(product_id: int, session: Session = Depends(get_session)):
    service.delete_product(session, product_id)
    return Response(status_code=204)


# ---------- 화면 ----------


def _form_errors(exc: ValidationError) -> dict[str, str]:
    errors = {}
    for err in exc.errors():
        field = str(err["loc"][0]) if err.get("loc") else ""
        label = FIELD_LABELS.get(field, field)
        if err["type"] in ("string_too_short", "missing"):
            msg = f"{label}을(를) 입력해 주세요."
        elif err["type"].startswith("int_") or err["type"] in ("greater_than_equal", "less_than_equal"):
            msg = f"{label}은(는) 0 이상의 숫자(원)로 입력해 주세요."
        elif err["type"] == "string_too_long":
            msg = f"{label}이(가) 너무 깁니다."
        else:
            msg = str(err.get("msg", "")).removeprefix("Value error, ")
        errors.setdefault(field, msg)
    return errors


async def _read_form(request: Request) -> dict:
    form = await request.form()
    values = {k: str(form.get(k, "")) for k in FORM_FIELDS}
    values["price"] = values["price"].replace(",", "").replace("원", "").strip()
    return values


def _render_form(request: Request, values: dict, errors: dict, product=None, status_code: int = 200):
    return templates.TemplateResponse(
        request,
        "products/form.html",
        {"values": values, "errors": errors, "product": product},
        status_code=status_code,
    )


@pages.get("", response_class=HTMLResponse)
def page_list(request: Request, q: str | None = None, session: Session = Depends(get_session)):
    products = service.list_products(session, q)
    return templates.TemplateResponse(request, "products/list.html", {"products": products, "q": q or ""})


@pages.get("/new", response_class=HTMLResponse)
def page_new(request: Request):
    return _render_form(request, {}, {})


@pages.post("/new", response_class=HTMLResponse)
async def page_create(request: Request, session: Session = Depends(get_session)):
    values = await _read_form(request)
    try:
        data = ProductCreate(**values)
    except ValidationError as exc:
        return _render_form(request, values, _form_errors(exc), status_code=422)
    product = service.create_product(session, data)
    return RedirectResponse(f"/products/{product.id}?saved=1", status_code=303)


@pages.get("/{product_id}", response_class=HTMLResponse)
def page_detail(request: Request, product_id: int, session: Session = Depends(get_session)):
    product = service.get_product(session, product_id)
    return templates.TemplateResponse(
        request,
        "products/detail.html",
        {
            "product": product,
            "saved": request.query_params.get("saved"),
            "error": request.query_params.get("error"),
        },
    )


@pages.get("/{product_id}/edit", response_class=HTMLResponse)
def page_edit(request: Request, product_id: int, session: Session = Depends(get_session)):
    product = service.get_product(session, product_id)
    values = {k: getattr(product, k) for k in FORM_FIELDS}
    values["features"] = "\n".join(product.features or [])
    values["price"] = "" if product.price is None else str(product.price)
    return _render_form(request, values, {}, product)


@pages.post("/{product_id}/edit", response_class=HTMLResponse)
async def page_update(request: Request, product_id: int, session: Session = Depends(get_session)):
    product = service.get_product(session, product_id)
    values = await _read_form(request)
    try:
        ProductCreate(**values)  # 화면에서는 제품명이 항상 필요
        data = ProductUpdate(**values)
    except ValidationError as exc:
        return _render_form(request, values, _form_errors(exc), product, status_code=422)
    service.update_product(session, product_id, data, replace_all=True)
    return RedirectResponse(f"/products/{product_id}?saved=1", status_code=303)


@pages.post("/{product_id}/delete")
def page_delete(product_id: int, session: Session = Depends(get_session)):
    try:
        service.delete_product(session, product_id)
    except AppError as exc:
        if exc.code.value == "PRODUCT_IN_USE":
            return RedirectResponse(f"/products/{product_id}?error=in_use", status_code=303)
        raise
    return RedirectResponse("/products?deleted=1", status_code=303)
