"""콘텐츠 프로젝트 만들기·조회·설정 수정. 제작 실행은 이후 작업(0-8 작업 대기열)에서 붙는다."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger
from app.core.models import Asset, Project, ProjectAsset
from app.products.service import get_product
from app.projects.schemas import ProjectCreate, ProjectUpdate

log = get_logger("projects")


def _check_assets(session: Session, product_id: int, asset_ids: list[int]) -> list[Asset]:
    """고른 소재가 모두 이 제품의 파일인지, 사진이 1장 이상인지 확인 (설계서: 시작하려면 사진 1장 이상)."""
    asset_ids = list(dict.fromkeys(asset_ids))
    assets = list(session.scalars(select(Asset).where(Asset.id.in_(asset_ids)))) if asset_ids else []
    if len(assets) != len(asset_ids) or any(a.product_id != product_id for a in assets):
        raise AppError(ErrorCode.VALIDATION_ERROR, "이 제품에 올린 사진·영상만 고를 수 있습니다.")
    if not any(a.kind == "product_photo" for a in assets):
        raise AppError(ErrorCode.PROJECT_NEEDS_PHOTO, "고른 소재에 제품 사진이 없습니다.")
    return assets


def _set_assets(session: Session, project: Project, assets: list[Asset]) -> None:
    current = {
        pa.asset_id: pa
        for pa in session.scalars(select(ProjectAsset).where(ProjectAsset.project_id == project.id))
    }
    wanted = {a.id for a in assets}
    for asset_id, link in current.items():
        if asset_id not in wanted:
            session.delete(link)  # 프로젝트에서 빼기만 하고 파일은 그대로
    for asset_id in wanted - current.keys():
        session.add(ProjectAsset(project_id=project.id, asset_id=asset_id))


def create_project(session: Session, data: ProjectCreate) -> Project:
    product = get_product(session, data.product_id)
    assets = _check_assets(session, product.id, data.asset_ids)
    values = data.model_dump(exclude={"asset_ids"})
    if not values.get("title"):
        values["title"] = product.name
    project = Project(**values, board_status="신규", status="ready")
    session.add(project)
    session.flush()
    _set_assets(session, project, assets)
    session.commit()
    log.info("프로젝트 생성 #%s %s (소재 %d개)", project.id, project.title, len(assets))
    return project


def get_project(session: Session, project_id: int) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise AppError(ErrorCode.NOT_FOUND, f"콘텐츠 번호 {project_id}")
    return project


def list_projects(session: Session, limit: int = 200) -> list[Project]:
    return list(session.scalars(select(Project).order_by(Project.id.desc()).limit(limit)))


def project_asset_ids(session: Session, project_id: int) -> list[int]:
    stmt = (
        select(ProjectAsset.asset_id)
        .where(ProjectAsset.project_id == project_id)
        .order_by(ProjectAsset.asset_id)
    )
    return list(session.scalars(stmt))


def project_assets(session: Session, project_id: int) -> list[Asset]:
    stmt = (
        select(Asset)
        .join(ProjectAsset, ProjectAsset.asset_id == Asset.id)
        .where(ProjectAsset.project_id == project_id)
        .order_by(Asset.id)
    )
    return list(session.scalars(stmt))


def update_project(session: Session, project_id: int, data: ProjectUpdate) -> Project:
    project = get_project(session, project_id)
    if project.status != "ready":
        raise AppError(ErrorCode.PROJECT_LOCKED, f"현재 상태: {project.status}")
    values = data.model_dump(exclude={"asset_ids"}, exclude_unset=True)
    for key, value in values.items():
        setattr(project, key, value)
    if not project.title:
        project.title = get_product(session, project.product_id).name
    if data.asset_ids is not None:
        _set_assets(session, project, _check_assets(session, project.product_id, data.asset_ids))
    session.commit()
    log.info("프로젝트 설정 수정 #%s", project.id)
    return project
