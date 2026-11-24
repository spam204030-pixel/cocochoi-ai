"""메인 현황판 데이터 (설계서 화면 0): 신규 / 제작 중 / 검수 대기 / 완료."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.models import Product, Project, UsageLog
from app.pipeline.engine import pipeline_state
from app.pipeline.steps import STEP_KEYS

COLUMNS = [
    ("신규", "제품·소재 업로드"),
    ("제작 중", "AI 제작 진행"),
    ("검수 대기", "완성 콘텐츠 확인"),
    ("완료", "다운로드·게시 준비"),
]


def month_start_utc(now: datetime | None = None) -> datetime:
    """이번 달 1일 0시(컴퓨터 시간 기준)를 UTC로."""
    local = (now or datetime.now()).astimezone()
    return local.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


def board(session: Session) -> dict:
    names = dict(session.execute(select(Product.id, Product.name)).all())
    columns = {name: [] for name, _ in COLUMNS}
    any_running = False
    for project in session.scalars(select(Project).order_by(Project.updated_at.desc(), Project.id.desc())):
        state = pipeline_state(session, project.id)
        card = {
            "id": project.id,
            "title": project.title or names.get(project.product_id, ""),
            "product": names.get(project.product_id, ""),
            "status": project.status,
            "status_label": state["status_label"],
            "done": state["done_count"],
            "total": len(STEP_KEYS),
            "current": next(
                (s["name"] for s in state["steps"] if s["status"] in ("running", "waiting_ai")), None
            ),
            "waiting_ai": any(st["status"] == "waiting_ai" for st in state["steps"]),
            "needs_user": project.status in ("failed", "waiting_user", "paused")
            or any(st["status"] == "waiting_ai" for st in state["steps"]),
            "ai_cost": state["ai_cost"],
        }
        any_running = any_running or project.status == "running"
        columns.setdefault(project.board_status, []).append(card)

    since = month_start_utc()
    month_cost = (
        session.scalar(select(func.sum(UsageLog.actual_cost)).where(UsageLog.created_at >= since)) or 0
    )
    return {
        "columns": [(name, desc, columns.get(name, [])) for name, desc in COLUMNS],
        "month_cost": round(float(month_cost), 2),
        "any_running": any_running,
        "product_count": len(names),
    }
