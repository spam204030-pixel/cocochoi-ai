"""제품 저장·조회·수정·삭제. API와 화면이 같은 함수를 쓴다."""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger
from app.core.models import Product, Project
from app.products.schemas import ProductCreate, ProductUpdate

log = get_logger("products")


def list_products(session: Session, q: str | None = None, limit: int = 200) -> list[Product]:
    stmt = select(Product).order_by(Product.id.desc()).limit(limit)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Product.name.ilike(like), Product.category.ilike(like)))
    return list(session.scalars(stmt))


def get_product(session: Session, product_id: int) -> Product:
    product = session.get(Product, product_id)
    if product is None:
        raise AppError(ErrorCode.NOT_FOUND, f"제품 번호 {product_id}")
    return product


def create_product(session: Session, data: ProductCreate) -> Product:
    product = Product(**data.model_dump())
    session.add(product)
    session.commit()
    log.info("제품 등록 #%s %s", product.id, product.name)
    return product


def update_product(
    session: Session, product_id: int, data: ProductUpdate, replace_all: bool = False
) -> Product:
    """replace_all=True(화면 수정): 비운 칸은 지운다. False(API): 보낸 칸만 바꾼다."""
    product = get_product(session, product_id)
    values = data.model_dump(exclude_unset=not replace_all)
    if replace_all and not values.get("name"):
        values.pop("name", None)
    for key, value in values.items():
        if key == "name" and value is None:
            continue
        setattr(product, key, value)
    session.commit()
    log.info("제품 수정 #%s", product.id)
    return product


def delete_product(session: Session, product_id: int) -> None:
    product = get_product(session, product_id)
    used = session.scalar(select(func.count()).select_from(Project).where(Project.product_id == product_id))
    if used:
        raise AppError(ErrorCode.PRODUCT_IN_USE, f"제품 #{product_id}을 사용하는 콘텐츠 {used}개")
    session.delete(product)  # 연결된 사진·영상 기록은 남고 제품 연결만 끊긴다
    session.commit()
    log.info("제품 삭제 #%s %s", product_id, product.name)
