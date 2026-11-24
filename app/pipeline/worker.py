"""작업자 — 대기열(jobs)에서 작업을 하나씩 꺼내 단계 처리기를 실행한다.

`uv run factory`로 프로그램을 켜면 함께 켜진다(별도 창 불필요).
작업 상태는 DB에 있으므로 프로그램을 껐다 켜도 이어서 진행한다.
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select, update

from app.core.errors import AppError
from app.core.logging import get_logger
from app.core.models import Job, Project, RoleRun, utcnow
from app.core.settings import Settings
from app.pipeline import engine
from app.pipeline.handlers import HANDLERS, StepCancelled, StepWaiting
from app.pipeline.steps import STEP_NAMES, next_step
from app.providers.claude_code import ClaudeCodeBridge

log = get_logger("worker")


@dataclass
class StepContext:
    project_id: int
    step: str
    run: RoleRun
    settings: Settings
    should_stop: Callable[[], bool]
    ai: object | None = None  # AIGateway
    bridge: ClaudeCodeBridge | None = None
    job_id: int | None = None
    session_factory: object | None = None


class Worker:
    def __init__(self, session_factory, settings: Settings, ai=None) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self.ai = ai
        use_bridge = settings.ai_mode == "claude_code"
        self.bridge = ClaudeCodeBridge(settings.bridge_dir, session_factory) if use_bridge else None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---------- 작업 하나 처리 ----------

    def _claim(self) -> int | None:
        """대기 중인 작업 하나를 '실행 중'으로 바꾸고 번호를 돌려준다 (동시에 두 번 잡히지 않게)."""
        with self.session_factory() as s:
            job = s.scalars(
                select(Job).where(Job.status == "queued").order_by(Job.priority.desc(), Job.id)
            ).first()
            if job is None:
                return None
            claimed = s.execute(
                update(Job)
                .where(Job.id == job.id, Job.status == "queued")
                .values(status="running", locked_at=utcnow(), attempts=Job.attempts + 1)
            ).rowcount
            s.commit()
            return job.id if claimed == 1 else None

    def _is_cancelled(self, project_id: int) -> bool:
        with self.session_factory() as s:
            status = s.scalar(select(Project.status).where(Project.id == project_id))
            return status == "cancelled"

    def run_once(self) -> bool:
        """작업을 하나 처리하면 True, 할 일이 없으면 False."""
        job_id = self._claim()
        if job_id is None:
            return False
        with self.session_factory() as s:
            job = s.get(Job, job_id)
            run = s.get(RoleRun, (job.payload_json or {}).get("run_id"))
            project = s.get(Project, job.project_id)
            if run is None or project is None or project.status == "cancelled":
                job.status, job.finished_at = "cancelled", utcnow()
                if run is not None:
                    run.status = "cancelled"
                s.commit()
                return True
            run.status, run.started_at = "running", utcnow()
            s.commit()
            step, pid = job.step_key, job.project_id

        log.info("단계 시작 #%s %s (v%s)", pid, STEP_NAMES.get(step, step), run.version)
        ctx = StepContext(
            pid,
            step,
            run,
            self.settings,
            lambda: self._is_cancelled(pid),
            self.ai,
            self.bridge,
            job_id,
            self.session_factory,
        )
        try:
            output = HANDLERS[step](ctx)
        except StepWaiting as wait:
            self._set_waiting(job_id, run.id)
            log.info("Claude 처리 대기 #%s %s (%s)", pid, step, wait.request_id)
        except StepCancelled:
            self._finish(job_id, run.id, "cancelled")
            log.info("단계 취소 #%s %s", pid, step)
        except AppError as exc:
            self._finish(job_id, run.id, "failed", error_code=str(exc.code), error=exc.detail)
            log.warning("단계 실패 #%s %s: %s %s", pid, step, exc.code, exc.detail)
        except Exception as exc:  # 예상하지 못한 오류도 작업자를 멈추지 않는다
            self._finish(job_id, run.id, "failed", error_code="INTERNAL_ERROR", error=repr(exc))
            log.exception("단계 오류 #%s %s", pid, step)
        else:
            self._finish(job_id, run.id, "succeeded", output=output)
            log.info("단계 완료 #%s %s", pid, step)
        return True

    def _finish(self, job_id, run_id, status, output=None, error_code=None, error=None) -> None:
        with self.session_factory() as s:
            job, run = s.get(Job, job_id), s.get(RoleRun, run_id)
            project = s.get(Project, job.project_id)
            now = utcnow()
            run.status, run.finished_at = status, now
            job.finished_at = now
            if status == "succeeded":
                job.status = "done"
                run.output_json = output
                run.provider, run.model = (output or {}).get("provider"), (output or {}).get("model")
                run.call_key = (output or {}).get("call")
                run.actual_cost = (output or {}).get("cost", 0)
            elif status == "cancelled":
                job.status = "cancelled"
            else:
                job.status, job.error = "failed", error
                run.error_code = error_code
                if project.status in ("running", "paused"):
                    engine.set_project_status(project, "failed")
            s.flush()
            if status == "succeeded" and project.status == "running":
                nxt = next_step(job.step_key)
                if nxt is None:
                    engine.set_project_status(project, "waiting_user")  # 대표 최종 확인 대기
                else:
                    engine.enqueue(s, project.id, nxt)
            s.commit()

    # ---------- /공장 응답 처리 ----------

    def _set_waiting(self, job_id: int, run_id: int) -> None:
        with self.session_factory() as s:
            s.get(Job, job_id).status = "waiting"
            s.get(RoleRun, run_id).status = "waiting_ai"
            s.commit()

    def poll_bridge(self) -> int:
        """도착한 응답서를 반영한다. 처리한 응답 수를 돌려준다."""
        if self.bridge is None:
            return 0
        handled = 0
        with self.session_factory() as s:
            rows = self.bridge.waiting(s)
            pending = []
            for row in rows:
                job = s.get(Job, row.job_id) if row.job_id else None
                if job is None or job.status != "waiting":  # 취소 등으로 더 이상 기다리지 않음
                    self.bridge.cancel(row)
                    continue
                result = self.bridge.check(s, row)
                if result is not None:
                    pending.append(
                        (
                            result.kind,
                            row.job_id,
                            row.run_id,
                            row.call_key,
                            row.request_id,
                            result.data,
                            result.error,
                        )
                    )
            s.commit()
        for kind, job_id, run_id, call, rid, data, error in pending:
            if kind == "done":
                output = {
                    "call": call,
                    "provider": "claude_code",
                    "model": "구독",
                    "cost": 0,
                    "request_id": rid,
                    "result": data,
                }
                self._finish(job_id, run_id, "succeeded", output=output)
            elif kind == "failed":
                self._finish(job_id, run_id, "failed", error_code="AI_BAD_OUTPUT", error=error)
            handled += 1
        return handled

    # ---------- 백그라운드 실행 ----------

    def _loop(self) -> None:
        with self.session_factory() as s:
            engine.recover(s)
        while not self._stop.is_set():
            try:
                worked = self.run_once()
                worked = self.poll_bridge() > 0 or worked
            except Exception:
                log.exception("작업자 오류 — 잠시 후 계속합니다")
                worked = False
            if not worked:
                self._stop.wait(self.settings.worker_poll_seconds)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="factory-worker", daemon=True)
        self._thread.start()
        log.info("작업자 시작")

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)
        log.info("작업자 정지")


def wait_until_idle(worker: Worker, limit: float = 30.0) -> None:
    """테스트용: 할 일이 없을 때까지 처리한다."""
    end = time.monotonic() + limit
    while time.monotonic() < end and worker.run_once():
        pass
