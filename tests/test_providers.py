import json

import pytest
from pydantic import BaseModel
from sqlalchemy import select

from app.core.errors import AppError, ErrorCode
from app.core.models import Product, Project, UsageLog
from app.providers.base import LLMRequest
from app.providers.fake import FakeLLM
from app.providers.gateway import AIGateway
from app.providers.registry import Registry


class Hook(BaseModel):
    hooks: list[str]


@pytest.fixture
def setup(tmp_path, test_app):
    """시험용 설정 파일 + 단가 (고성능 모델은 100만 토큰당 입력 1,000원·출력 5,000원)."""
    prov = tmp_path / "providers.yaml"
    prov.write_text(
        """
tiers:
  cheap: {provider: fake, model: m-cheap}
  premium: {provider: fake, model: m-premium}
calls: {A: cheap, D: premium, X: premium, Z: nothing}
tts: {provider: fake, voice: v1}
""",
        encoding="utf-8",
    )
    price = tmp_path / "pricing.yaml"
    price.write_text(
        """
llm:
  fake:
    m-cheap: {input: 0, output: 0}
    m-premium: {input: 1000, output: 5000}
tts:
  fake: {per_1k_chars: 100}
""",
        encoding="utf-8",
    )
    reg = Registry(prov, price)
    fake = FakeLLM()
    reg.llms["fake"] = fake
    db = test_app.state.db
    with db.session_factory() as s:
        product = Product(name="p")
        s.add(product)
        s.flush()
        project = Project(product_id=product.id)
        s.add(project)
        s.commit()
        pid = project.id
    return AIGateway(reg, db.session_factory, retry_backoff=0), fake, db, pid


def logs(db, pid):
    with db.session_factory() as s:
        return list(s.scalars(select(UsageLog).where(UsageLog.project_id == pid).order_by(UsageLog.id)))


def req(call="D", user="안녕"):
    return LLMRequest(call_key=call, system="규칙", user=user, max_output_tokens=1000)


def test_route_and_tiers(setup):
    gw, *_ = setup
    r = gw.registry.route("D")
    assert (r.tier, r.provider, r.model) == ("premium", "fake", "m-premium")
    assert gw.registry.route("A").model == "m-cheap"


def test_unknown_call_or_provider_is_config_error(setup):
    gw, *_ = setup
    for call in ("NONE", "Z"):
        with pytest.raises(AppError) as exc:
            gw.registry.route(call)
        assert exc.value.code == ErrorCode.PROVIDER_NOT_CONFIGURED
    with pytest.raises(AppError) as exc:
        gw.registry.llm("anthropic")  # Phase 1 전에는 연결 안 됨
    assert exc.value.code == ErrorCode.PROVIDER_NOT_CONFIGURED


def test_call_records_usage_and_cost(setup):
    gw, fake, db, pid = setup
    fake.responses["D"] = [json.dumps({"hooks": ["무릎 시린 분들 주목"]}, ensure_ascii=False)]
    resp = gw.call_llm(req(), project_id=pid, role_key="script", schema=Hook)
    assert resp.data == {"hooks": ["무릎 시린 분들 주목"]}
    rows = logs(db, pid)
    assert len(rows) == 1 and rows[0].ok and rows[0].call_key == "D" and rows[0].model == "m-premium"
    expected = rows[0].input_units * 1000 / 1e6 + rows[0].output_units * 5000 / 1e6
    assert rows[0].actual_cost == pytest.approx(expected, abs=1e-3) and resp.cost == pytest.approx(
        expected, abs=1e-3
    )
    assert rows[0].est_cost >= rows[0].actual_cost  # 예상은 출력 최대치로 넉넉하게


def test_code_fence_json_is_accepted(setup):
    gw, fake, *_ = setup
    fake.responses["D"] = ['```json\n{"hooks": ["a"]}\n```']
    assert gw.call_llm(req(), schema=Hook).data == {"hooks": ["a"]}


def test_bad_output_is_reasked_once_then_succeeds(setup):
    gw, fake, db, pid = setup
    fake.responses["D"] = ["형식 아님", json.dumps({"hooks": ["b"]})]
    resp = gw.call_llm(req(), project_id=pid, schema=Hook)
    assert resp.data == {"hooks": ["b"]}
    assert "[이전 응답 오류]" in fake.calls[1].user  # 이유를 붙여 재요청
    assert len(logs(db, pid)) == 2


def test_bad_output_twice_raises(setup):
    gw, fake, *_ = setup
    fake.responses["D"] = ['{"wrong": 1}', '{"wrong": 2}']
    with pytest.raises(AppError) as exc:
        gw.call_llm(req(), schema=Hook)
    assert exc.value.code == ErrorCode.AI_BAD_OUTPUT
    assert len(fake.calls) == 2  # 무한 재요청 없음


def test_transient_errors_retry_up_to_two_more_times(setup):
    gw, fake, db, pid = setup
    fake.responses["D"] = [
        AppError(ErrorCode.AI_RATE_LIMITED),
        AppError(ErrorCode.AI_UNAVAILABLE),
        '{"hooks": []}',
    ]
    resp = gw.call_llm(req(), project_id=pid, schema=Hook)
    assert resp.attempts == 3
    assert [r.ok for r in logs(db, pid)] == [False, False, True]

    fake.responses["D"] = [AppError(ErrorCode.AI_TIMEOUT)] * 3
    with pytest.raises(AppError) as exc:
        gw.call_llm(req(), project_id=pid)
    assert exc.value.code == ErrorCode.AI_TIMEOUT


def test_auth_error_is_not_retried(setup):
    gw, fake, *_ = setup
    fake.responses["D"] = [AppError(ErrorCode.AI_AUTH_FAILED), '{"hooks": []}']
    with pytest.raises(AppError) as exc:
        gw.call_llm(req())
    assert exc.value.code == ErrorCode.AI_AUTH_FAILED and len(fake.calls) == 1


def test_budget_limit_stops_before_calling(setup):
    gw, fake, db, pid = setup
    with db.session_factory() as s:
        s.get(Project, pid).budget_limit = 1  # 1원
        s.commit()
    big = req(user="가" * 3000)  # 예상: 입력 약 1,500토큰 + 출력 1,000토큰 → 6.5원
    assert gw.estimate_llm(big) > 1
    with pytest.raises(AppError) as exc:
        gw.call_llm(big, project_id=pid)
    assert exc.value.code == ErrorCode.BUDGET_EXCEEDED
    assert fake.calls == [] and logs(db, pid) == []  # 호출하지 않았고 비용도 없음
    assert gw.call_llm(req(call="A"), project_id=pid).cost == 0  # 무료 모델은 통과


def test_tts_records_chars_and_cost(setup, tmp_path):
    gw, _, db, pid = setup
    result = gw.tts("시험용 나레이션입니다", tmp_path / "a.wav", project_id=pid, role_key="production")
    assert result.audio_path.is_file() and result.duration > 0
    row = logs(db, pid)[0]
    assert (row.call_key, row.unit, row.input_units) == ("tts", "chars", 11)
    assert row.actual_cost == pytest.approx(11 / 1000 * 100)


def test_missing_price_refuses_to_run(setup):
    gw, *_ = setup
    gw.registry.pricing["llm"]["fake"].pop("m-premium")
    with pytest.raises(AppError) as exc:
        gw.call_llm(req())
    assert exc.value.code == ErrorCode.PROVIDER_NOT_CONFIGURED  # 모르는 비용으로는 실행 안 함


def test_default_config_is_all_fake_and_free(test_app):
    reg = test_app.state.registry
    assert reg.all_fake()
    for call in ("A", "B", "C", "D", "E", "F", "G1", "G2", "G2_blog", "H"):
        r = reg.route(call)
        assert reg.llm_price(r.provider, r.model) == (0, 0)


def test_pipeline_records_fake_usage(client, test_app):
    from app.pipeline import engine
    from app.pipeline.worker import wait_until_idle

    db = test_app.state.db
    with db.session_factory() as s:
        p = Product(name="x")
        s.add(p)
        s.flush()
        proj = Project(product_id=p.id)
        s.add(proj)
        s.commit()
        pid = proj.id
        engine.start(s, pid)
    wait_until_idle(test_app.state.worker)
    state = client.get(f"/api/projects/{pid}/pipeline").json()
    assert state["status"] == "waiting_user"
    assert state["ai_calls"] == 7 and state["ai_cost"] == 0  # AI 6번 + 시험 음성 1번
    assert [r.call_key for r in logs(db, pid)] == ["B", "A", "C", "D", "tts", "F", "G1"]
    assert "AI 사용 7회 · 비용 0원" in client.get(f"/projects/{pid}").text
    assert "시험용 가짜 공급자" in client.get("/api/health").json()["checks"]["ai_provider"]
