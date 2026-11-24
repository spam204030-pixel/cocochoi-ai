"""/공장 연결 (설계서 V4-4, 작업 1-1): 요청서 → 대기 → 응답서 → 다음 단계."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.errors import AppError
from app.core.models import BridgeRequest, Product, Project, UsageLog
from app.main import create_app
from app.pipeline import engine
from app.pipeline.worker import Worker, wait_until_idle


@pytest.fixture
def env(tmp_settings):
    settings = tmp_settings.model_copy(update={"ai_mode": "claude_code"})
    app = create_app(settings)
    db, worker = app.state.db, app.state.worker
    with db.session_factory() as s:
        p = Product(name="발열양말")
        s.add(p)
        s.flush()
        proj = Project(product_id=p.id)
        s.add(proj)
        s.commit()
        pid = proj.id
    return app, db, worker, pid, settings.bridge_dir


def start(db, pid):
    with db.session_factory() as s:
        engine.start(s, pid)


def state(db, pid):
    with db.session_factory() as s:
        return engine.pipeline_state(s, pid)


def requests(bridge):
    return sorted((bridge / "requests").glob("*.json"))


def answer(bridge, body):
    req = json.loads(requests(bridge)[0].read_text("utf-8"))
    (bridge / "responses" / f"{req['request_id']}.json").write_text(
        body if isinstance(body, str) else json.dumps(body), "utf-8"
    )
    return req


def step_status(db, pid, key):
    return next(s["status"] for s in state(db, pid)["steps"] if s["key"] == key)


def test_ai_step_waits_with_request_file(env):
    app, db, worker, pid, bridge = env
    start(db, pid)
    wait_until_idle(worker)
    assert step_status(db, pid, "media_prep") == "succeeded"
    assert step_status(db, pid, "analysis") == "waiting_ai"
    assert state(db, pid)["status"] == "running"
    req = json.loads(requests(bridge)[0].read_text("utf-8"))
    assert req["batch"] == 1 and req["call"] == "PING" and "output_schema" in req
    page = TestClient(app).get(f"/projects/{pid}").text
    assert "/공장" in page and "Claude 처리 대기" in page
    with pytest.raises(AppError):  # 대기 중에도 중복 시작 불가
        start(db, pid)


def test_full_run_with_three_batches(env):
    app, db, worker, pid, bridge = env
    start(db, pid)
    for batch in (1, 2, 3):
        wait_until_idle(worker)
        req = answer(bridge, {"ok": True, "note": "확인"})
        assert req["batch"] == batch
        assert worker.poll_bridge() == 1
    wait_until_idle(worker)
    s = state(db, pid)
    assert s["status"] == "waiting_user" and s["done_count"] == 7 and s["ai_cost"] == 0
    with db.session_factory() as ses:
        logs = list(ses.scalars(select(UsageLog).where(UsageLog.provider == "claude_code")))
        assert len(logs) == 3 and all(log.actual_cost == 0 for log in logs)
    assert requests(bridge) == [] and len(list((bridge / "done").glob("*"))) == 6


def test_bad_response_is_reasked_once_then_fails(env):
    _, db, worker, pid, bridge = env
    start(db, pid)
    wait_until_idle(worker)
    answer(bridge, "형식이 틀린 응답")
    worker.poll_bridge()
    req = json.loads(requests(bridge)[0].read_text("utf-8"))
    assert req["retry_reason"] and step_status(db, pid, "analysis") == "waiting_ai"
    answer(bridge, {"note": "ok 빠짐"})
    worker.poll_bridge()
    s = state(db, pid)
    assert s["status"] == "failed" and s["steps"][1]["error"] == "AI_BAD_OUTPUT"


def test_waiting_survives_restart(env, tmp_settings):
    app, db, worker, pid, bridge = env
    start(db, pid)
    wait_until_idle(worker)
    restarted = Worker(db.session_factory, app.state.settings, app.state.ai)
    with db.session_factory() as s:
        engine.recover(s)
    assert step_status(db, pid, "analysis") == "waiting_ai"
    answer(bridge, {"ok": True})
    assert restarted.poll_bridge() == 1
    wait_until_idle(restarted)
    assert step_status(db, pid, "planning") == "waiting_ai"


def test_cancel_while_waiting(env):
    _, db, worker, pid, bridge = env
    start(db, pid)
    wait_until_idle(worker)
    with db.session_factory() as s:
        engine.cancel(s, pid)
    worker.poll_bridge()
    assert requests(bridge) == []
    with db.session_factory() as s:
        assert s.scalars(select(BridgeRequest)).one().status == "cancelled"
    assert state(db, pid)["status"] == "cancelled"


def test_health_shows_pc_and_mode(env):
    app, *_ = env
    checks = TestClient(app).get("/api/health").json()["checks"]
    assert "메모리" in checks["pc"] and "/공장" in checks["ai_provider"]
