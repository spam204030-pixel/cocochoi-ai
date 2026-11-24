import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.errors import AppError
from app.core.models import Job, Product, Project, RoleRun
from app.main import create_app
from app.pipeline import engine, handlers
from app.pipeline.steps import STEP_KEYS
from app.pipeline.worker import wait_until_idle


@pytest.fixture
def ctx(test_app):
    db, worker = test_app.state.db, test_app.state.worker
    with db.session_factory() as s:
        product = Product(name="겨울 니삭스")
        s.add(product)
        s.flush()
        project = Project(product_id=product.id, title="시험 콘텐츠")
        s.add(project)
        s.commit()
        pid = project.id
    return db, worker, pid


def state(db, pid):
    with db.session_factory() as s:
        return engine.pipeline_state(s, pid)


def do(db, fn, pid, *args):
    with db.session_factory() as s:
        fn(s, pid, *args)


def statuses(db, pid):
    return [st["status"] for st in state(db, pid)["steps"]]


def active_jobs(db, pid):
    with db.session_factory() as s:
        return s.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.project_id == pid, Job.status.in_(engine.ACTIVE_JOB))
        )


def test_full_run_completes_all_steps_in_order(ctx):
    db, worker, pid = ctx
    do(db, engine.start, pid)
    assert state(db, pid)["status"] == "running" and state(db, pid)["board_status"] == "제작 중"
    assert active_jobs(db, pid) == 1

    order = []
    while worker.run_once():
        order.append([st["key"] for st in state(db, pid)["steps"] if st["status"] == "succeeded"][-1])
        assert active_jobs(db, pid) <= 1  # 한 번에 하나만
    assert order == STEP_KEYS
    s = state(db, pid)
    assert s["status"] == "waiting_user" and s["board_status"] == "검수 대기" and s["done_count"] == 8
    assert s["steps"][0]["output"]["fake"] is True


def test_duplicate_start_is_blocked(ctx):
    db, _, pid = ctx
    do(db, engine.start, pid)
    with pytest.raises(AppError) as exc:
        do(db, engine.start, pid)
    assert exc.value.code == "PROJECT_ALREADY_RUNNING"
    assert active_jobs(db, pid) == 1


def test_pause_before_and_resume(ctx):
    db, worker, pid = ctx
    do(db, engine.start, pid)
    do(db, engine.pause, pid)
    assert worker.run_once() is False  # 멈춘 작업은 처리하지 않음
    assert state(db, pid)["status"] == "paused"
    do(db, engine.resume, pid)
    wait_until_idle(worker)
    assert state(db, pid)["status"] == "waiting_user"


def test_pause_during_step_finishes_that_step_then_stops(ctx, monkeypatch):
    db, worker, pid = ctx

    def pausing(c):
        do(db, engine.pause, c.project_id)  # 단계 진행 중에 일시정지 누름
        return {"fake": True}

    monkeypatch.setitem(handlers.HANDLERS, "strategy", pausing)
    monkeypatch.setattr("app.pipeline.worker.HANDLERS", handlers.HANDLERS)
    do(db, engine.start, pid)
    wait_until_idle(worker)
    assert statuses(db, pid)[:3] == ["succeeded"] * 3  # 지금 단계(전략)는 끝까지
    assert statuses(db, pid)[3] == "pending"  # 다음 단계로 넘어가지 않음
    assert state(db, pid)["status"] == "paused" and active_jobs(db, pid) == 0

    monkeypatch.setitem(handlers.HANDLERS, "strategy", handlers.fake_step)
    do(db, engine.resume, pid)
    wait_until_idle(worker)
    assert state(db, pid)["done_count"] == 8


def test_cancel_during_step_keeps_finished_results(ctx, test_app, monkeypatch):
    db, worker, pid = ctx

    def cancelling(c):
        do(db, engine.cancel, c.project_id)
        return handlers.fake_step(c)  # 취소를 확인하고 멈춤

    monkeypatch.setitem(handlers.HANDLERS, "planning", cancelling)
    do(db, engine.start, pid)
    wait_until_idle(worker)
    st = statuses(db, pid)
    assert st[:3] == ["succeeded"] * 3 and st[3] == "cancelled" and set(st[4:]) == {"cancelled"}
    assert state(db, pid)["status"] == "cancelled" and active_jobs(db, pid) == 0

    # 다시 시작하면 새 버전(v2)으로 처음부터, 예전 결과는 보관
    monkeypatch.setitem(handlers.HANDLERS, "planning", handlers.fake_step)
    do(db, engine.start, pid)
    wait_until_idle(worker)
    assert state(db, pid)["status"] == "waiting_user"
    assert {st["version"] for st in state(db, pid)["steps"]} == {2}
    with db.session_factory() as s:
        assert s.scalar(select(func.count()).select_from(RoleRun).where(RoleRun.project_id == pid)) == 16


def test_failed_step_retry_does_not_redo_earlier_steps(ctx):
    db, worker, pid = ctx
    worker.settings.fake_fail_step = "strategy"
    do(db, engine.start, pid)
    wait_until_idle(worker)
    s = state(db, pid)
    assert s["status"] == "failed" and s["board_status"] == "제작 중"
    assert statuses(db, pid)[:3] == ["succeeded", "succeeded", "failed"]
    assert s["steps"][2]["error"] == "AI_UNAVAILABLE"

    do(db, engine.rerun_from, pid, "strategy")
    wait_until_idle(worker)
    s = state(db, pid)
    assert s["status"] == "waiting_user"
    assert [st["version"] for st in s["steps"]] == [1, 1, 2, 2, 2, 2, 2, 2]  # 앞 두 단계는 다시 하지 않음


def test_rerun_from_middle_after_completion(ctx):
    db, worker, pid = ctx
    do(db, engine.start, pid)
    wait_until_idle(worker)
    do(db, engine.rerun_from, pid, "script")
    wait_until_idle(worker)
    assert [st["version"] for st in state(db, pid)["steps"]] == [1, 1, 1, 1, 2, 2, 2, 2]
    with db.session_factory() as s:
        old = s.scalars(
            select(RoleRun).where(
                RoleRun.project_id == pid, RoleRun.role_key == "script", RoleRun.version == 1
            )
        ).one()
        assert old.status == "stale"  # 예전 결과는 보관


def test_rerun_requires_previous_steps_done(ctx):
    db, worker, pid = ctx
    worker.settings.fake_fail_step = "strategy"
    do(db, engine.start, pid)
    wait_until_idle(worker)
    with pytest.raises(AppError) as exc:
        do(db, engine.rerun_from, pid, "script")
    assert exc.value.code == "INVALID_ACTION"


def test_recover_after_crash(ctx):
    db, worker, pid = ctx
    do(db, engine.start, pid)
    worker._claim()  # 작업을 잡은 상태에서 프로그램이 꺼졌다고 가정
    assert worker.run_once() is False  # 실행 중으로 묶여 있어 다른 작업 없음
    with db.session_factory() as s:
        assert engine.recover(s) == 1
    wait_until_idle(worker)
    assert state(db, pid)["status"] == "waiting_user"


def test_unexpected_error_marks_failed_and_worker_continues(ctx, monkeypatch):
    db, worker, pid = ctx
    monkeypatch.setitem(handlers.HANDLERS, "script", lambda c: 1 / 0)
    do(db, engine.start, pid)
    wait_until_idle(worker)
    s = state(db, pid)
    assert s["status"] == "failed" and s["steps"][4]["error"] == "INTERNAL_ERROR"
    assert worker.run_once() is False  # 작업자는 멈추지 않고 대기


def test_api_and_page_buttons(client, ctx):
    db, worker, pid = ctx
    assert client.get(f"/api/projects/{pid}/pipeline").json()["status"] == "ready"
    page = client.get(f"/projects/{pid}")
    assert "시험 실행 시작" in page.text and "상품 분석" in page.text

    res = client.post(f"/projects/{pid}/run/start", follow_redirects=True)
    assert "시험 실행을 시작했습니다" in res.text and "일시정지" in res.text
    res = client.post(f"/projects/{pid}/run/start", follow_redirects=True)
    assert "이미 제작이 진행 중입니다" in res.text

    client.post(f"/projects/{pid}/run/pause")
    assert "재개" in client.get(f"/projects/{pid}").text
    client.post(f"/api/projects/{pid}/resume")
    wait_until_idle(worker)
    page = client.get(f"/projects/{pid}").text
    assert "대표님 확인" in page and "시험 실행이 끝났습니다" in page
    assert client.post(f"/api/projects/{pid}/nope").status_code == 404
    assert (
        client.patch(f"/api/projects/{pid}", json={"target_length": 15}).json()["error"]["code"]
        == "PROJECT_LOCKED"
    )


def test_background_worker_runs_with_server(tmp_settings):
    tmp_settings.worker_enabled = True
    tmp_settings.worker_poll_seconds = 0.05
    app = create_app(tmp_settings)
    with TestClient(app) as client:  # 서버 켜짐 → 작업자도 켜짐
        pid = client.post("/api/products", json={"name": "x"}).json()["id"]
        with app.state.db.session_factory() as s:
            project = Project(product_id=pid)
            s.add(project)
            s.commit()
            proj_id = project.id
        client.post(f"/api/projects/{proj_id}/start")
        end = time.monotonic() + 15
        while (
            time.monotonic() < end
            and client.get(f"/api/projects/{proj_id}/pipeline").json()["status"] != "waiting_user"
        ):
            time.sleep(0.05)
        assert client.get(f"/api/projects/{proj_id}/pipeline").json()["done_count"] == 8
