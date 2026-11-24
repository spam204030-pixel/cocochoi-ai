"""제작 진행 API(/api/projects/{id}/...)와 화면 버튼 동작."""

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.pipeline import engine
from app.products.routes import get_session

api = APIRouter(prefix="/api/projects/{project_id}", tags=["제작 진행"])
pages = APIRouter(prefix="/projects/{project_id}")

ACTIONS = {"start": engine.start, "pause": engine.pause, "resume": engine.resume, "cancel": engine.cancel}


@api.get("/pipeline")
def api_state(project_id: int, session: Session = Depends(get_session)):
    return engine.pipeline_state(session, project_id)


@api.post("/{action}")
def api_action(project_id: int, action: str, session: Session = Depends(get_session)):
    if action not in ACTIONS:
        raise AppError(ErrorCode.NOT_FOUND, f"동작 {action}")
    ACTIONS[action](session, project_id)
    return engine.pipeline_state(session, project_id)


@api.post("/steps/{step}/rerun")
def api_rerun(project_id: int, step: str, session: Session = Depends(get_session)):
    engine.rerun_from(session, project_id, step)
    return engine.pipeline_state(session, project_id)


def _redirect(project_id: int, msg: str | None = None):
    suffix = f"?msg={msg}" if msg else ""
    return RedirectResponse(f"/projects/{project_id}{suffix}#pipeline", status_code=303)


@pages.post("/run/{action}")
def page_action(project_id: int, action: str, session: Session = Depends(get_session)):
    try:
        if action in ACTIONS:
            ACTIONS[action](session, project_id)
    except AppError as exc:
        session.rollback()
        return _redirect(project_id, exc.code.value)
    return _redirect(project_id, action)


@pages.post("/steps/{step}/rerun")
def page_rerun(project_id: int, step: str, session: Session = Depends(get_session)):
    try:
        engine.rerun_from(session, project_id, step)
    except AppError as exc:
        session.rollback()
        return _redirect(project_id, exc.code.value)
    return _redirect(project_id, "rerun")
