"""제작 진행 관리: 시작·일시정지·재개·취소·다시 실행 (설계서 2-3 작업 복구).

규칙
- 단계가 끝날 때마다 결과를 role_runs 에 저장한다. 실패해도 앞 단계는 다시 하지 않는다
- 한 콘텐츠에는 동시에 작업이 하나만 돈다 (중복 실행 방지)
- 다시 실행하면 새 버전(version)을 만들고, 이전 결과는 지우지 않는다
"""

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger
from app.core.models import Job, Project, RoleRun, UsageLog, utcnow
from app.pipeline.steps import PROJECT_STATUS, STEP_KEYS

log = get_logger("pipeline")

ACTIVE_JOB = ("queued", "running", "paused")


def set_project_status(project: Project, status: str) -> None:
    project.status = status
    project.board_status = PROJECT_STATUS[status][1]


def latest_runs(session: Session, project_id: int) -> dict[str, RoleRun]:
    runs = session.scalars(select(RoleRun).where(RoleRun.project_id == project_id).order_by(RoleRun.version))
    return {r.role_key: r for r in runs}  # 단계마다 가장 최근 버전


def active_job(session: Session, project_id: int) -> Job | None:
    stmt = select(Job).where(Job.project_id == project_id, Job.status.in_(ACTIVE_JOB)).order_by(Job.id)
    return session.scalars(stmt).first()


def _new_run(session: Session, project_id: int, step: str) -> RoleRun:
    last = session.scalar(
        select(func.max(RoleRun.version)).where(RoleRun.project_id == project_id, RoleRun.role_key == step)
    )
    run = RoleRun(project_id=project_id, role_key=step, version=(last or 0) + 1, status="pending")
    session.add(run)
    return run


def enqueue(session: Session, project_id: int, step: str) -> Job:
    """단계 작업을 대기열에 넣는다. 이미 진행 중인 작업이 있으면 넣지 않는다."""
    existing = active_job(session, project_id)
    if existing is not None:
        raise AppError(ErrorCode.PROJECT_ALREADY_RUNNING, f"작업 #{existing.id} ({existing.step_key})")
    run = latest_runs(session, project_id)[step]
    run.status = "queued"
    job = Job(
        project_id=project_id,
        step_key=step,
        task="run_step",
        status="queued",
        payload_json={"run_id": run.id},
    )
    session.add(job)
    return job


def _get(session: Session, project_id: int) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise AppError(ErrorCode.NOT_FOUND, f"콘텐츠 번호 {project_id}")
    return project


def start(session: Session, project_id: int) -> None:
    """처음부터 제작 시작 (모든 단계 새 버전)."""
    project = _get(session, project_id)
    if project.status in ("running", "paused") or active_job(session, project_id):
        raise AppError(ErrorCode.PROJECT_ALREADY_RUNNING)
    for step in STEP_KEYS:
        _new_run(session, project_id, step)
    session.flush()
    set_project_status(project, "running")
    enqueue(session, project_id, STEP_KEYS[0])
    session.commit()
    log.info("제작 시작 #%s", project_id)


def pause(session: Session, project_id: int) -> None:
    """지금 하는 단계는 끝까지 하고, 다음 단계로 넘어가지 않는다."""
    project = _get(session, project_id)
    if project.status != "running":
        raise AppError(ErrorCode.INVALID_ACTION, f"현재 상태: {PROJECT_STATUS[project.status][0]}")
    set_project_status(project, "paused")
    session.execute(
        update(Job).where(Job.project_id == project_id, Job.status == "queued").values(status="paused")
    )
    session.commit()
    log.info("일시정지 #%s", project_id)


def resume(session: Session, project_id: int) -> None:
    project = _get(session, project_id)
    if project.status != "paused":
        raise AppError(ErrorCode.INVALID_ACTION, f"현재 상태: {PROJECT_STATUS[project.status][0]}")
    set_project_status(project, "running")
    paused_job = session.scalars(
        select(Job).where(Job.project_id == project_id, Job.status == "paused")
    ).first()
    if paused_job is not None:
        paused_job.status = "queued"
    elif not active_job(session, project_id):
        runs = latest_runs(session, project_id)
        step = next((s for s in STEP_KEYS if runs[s].status != "succeeded"), None)
        if step is None:
            set_project_status(project, "waiting_user")
        else:
            enqueue(session, project_id, step)
    session.commit()
    log.info("재개 #%s", project_id)


def cancel(session: Session, project_id: int) -> None:
    """제작을 멈춘다. 이미 끝난 단계의 결과는 남긴다."""
    project = _get(session, project_id)
    if project.status not in ("running", "paused", "failed"):
        raise AppError(ErrorCode.INVALID_ACTION, f"현재 상태: {PROJECT_STATUS[project.status][0]}")
    set_project_status(project, "cancelled")
    now = utcnow()
    session.execute(
        update(Job)
        .where(Job.project_id == project_id, Job.status.in_(("queued", "paused")))
        .values(status="cancelled", finished_at=now)
    )
    for run in latest_runs(session, project_id).values():
        if run.status in ("pending", "queued", "paused"):
            run.status = "cancelled"
    session.commit()  # 실행 중인 단계는 작업자가 취소를 확인하고 멈춘다
    log.info("취소 #%s", project_id)


def rerun_from(session: Session, project_id: int, step: str) -> None:
    """이 단계부터 다시 실행. 앞 단계 결과는 그대로 쓰고, 이 단계와 뒤 단계는 새 버전으로 만든다."""
    if step not in STEP_KEYS:
        raise AppError(ErrorCode.NOT_FOUND, f"단계 {step}")
    project = _get(session, project_id)
    if project.status in ("running", "paused") or active_job(session, project_id):
        raise AppError(ErrorCode.PROJECT_ALREADY_RUNNING)
    runs = latest_runs(session, project_id)
    if not runs:
        raise AppError(ErrorCode.INVALID_ACTION, "아직 제작을 시작하지 않았습니다.")
    i = STEP_KEYS.index(step)
    if any(runs[s].status != "succeeded" for s in STEP_KEYS[:i]):
        raise AppError(ErrorCode.INVALID_ACTION, "앞 단계가 모두 끝나야 이 단계부터 다시 할 수 있습니다.")
    for s in STEP_KEYS[i:]:
        if runs[s].status == "succeeded":
            runs[s].status = "stale"  # 예전 결과는 보관 (다시 만들어야 함 표시)
        _new_run(session, project_id, s)
    session.flush()
    set_project_status(project, "running")
    enqueue(session, project_id, step)
    session.commit()
    log.info("다시 실행 #%s %s부터", project_id, step)


def recover(session: Session) -> int:
    """프로그램이 꺼졌다 켜졌을 때: 실행 중이던 작업을 다시 대기열로 돌린다."""
    jobs = list(session.scalars(select(Job).where(Job.status == "running")))
    for job in jobs:
        job.status = "queued"
        job.locked_at = None
        run = session.get(RoleRun, (job.payload_json or {}).get("run_id"))
        if run is not None and run.status == "running":
            run.status = "queued"
    session.commit()
    if jobs:
        log.warning("중단됐던 작업 %d개를 이어서 진행합니다", len(jobs))
    return len(jobs)


def pipeline_state(session: Session, project_id: int) -> dict:
    from app.pipeline.steps import DISPLAY, STEP_NAMES

    project = _get(session, project_id)
    runs = latest_runs(session, project_id)
    steps = []
    for key in STEP_KEYS:
        run = runs.get(key)
        status = run.status if run else "pending"
        label, icon = DISPLAY[status]
        steps.append(
            {
                "key": key,
                "name": STEP_NAMES[key],
                "status": status,
                "label": label,
                "icon": icon,
                "version": run.version if run else 0,
                "error": run.error_code if run else None,
                "output": run.output_json if run else None,
            }
        )
    job = active_job(session, project_id)
    cost = (
        session.scalar(select(func.sum(UsageLog.actual_cost)).where(UsageLog.project_id == project_id)) or 0
    )
    calls = session.scalar(
        select(func.count()).select_from(UsageLog).where(UsageLog.project_id == project_id)
    )
    return {
        "ai_cost": round(float(cost), 2),
        "ai_calls": calls,
        "project_id": project_id,
        "status": project.status,
        "status_label": PROJECT_STATUS[project.status][0],
        "board_status": project.board_status,
        "steps": steps,
        "active_step": job.step_key if job else None,
        "done_count": sum(s["status"] == "succeeded" for s in steps),
    }
