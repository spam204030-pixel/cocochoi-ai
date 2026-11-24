"""단계 처리기. 지금은 모두 '시험 실행(가짜 작업)'이다.

실제 AI·편집 기능은 Phase 1 이후 단계별로 이 자리를 교체한다.
가짜 작업은 비용이 들지 않고, 결과에 fake=True 가 표시된다.
"""

import time

from app.core.errors import AppError, ErrorCode
from app.pipeline.steps import STEP_KEYS, STEP_NAMES
from app.providers.base import LLMRequest

# 단계 → AI 호출 (PROMPTS.md). 전략·기획은 호출 C 하나로 함께 처리
STEP_CALLS = {
    "product_analysis": "B",
    "media_analysis": "A",
    "strategy": "C",
    "script": "D",
    "quality": "F",
    "platform": "G1",
}


class StepCancelled(Exception):
    """사용자가 취소함."""


def fake_step(ctx) -> dict:
    total = max(ctx.settings.fake_step_seconds, 0)
    waited = 0.0
    while waited < total:
        if ctx.should_stop():
            raise StepCancelled
        time.sleep(min(0.1, total - waited))
        waited += 0.1
    if ctx.should_stop():
        raise StepCancelled
    if ctx.settings.fake_fail_step == ctx.step and ctx.run.version == 1:
        # 시험용: 첫 실행만 실패 → '다시 실행'하면 성공
        raise AppError(ErrorCode.AI_UNAVAILABLE, f"시험용 실패: {STEP_NAMES[ctx.step]}")

    output = {"fake": True, "message": f"{STEP_NAMES[ctx.step]} 시험 실행 완료 (실제 AI 사용 안 함)"}
    call = STEP_CALLS.get(ctx.step)
    if call and ctx.ai is not None:  # AI 호출 창구를 거쳐 사용량·비용 기록 흐름까지 확인
        req = LLMRequest(
            call_key=call, system="[시험 실행]", user=f"{STEP_NAMES[ctx.step]} 시험", max_output_tokens=200
        )
        resp = ctx.ai.call_llm(req, project_id=ctx.project_id, role_key=ctx.step)
        output.update(call=call, provider=resp.result.provider, model=resp.result.model, cost=resp.cost)
    elif ctx.step == "production" and ctx.ai is not None:
        out = (
            ctx.settings.storage_dir
            / "projects"
            / str(ctx.project_id)
            / "audio"
            / f"fake_v{ctx.run.version}.wav"
        )
        tts = ctx.ai.tts("시험용 나레이션입니다", out, project_id=ctx.project_id, role_key=ctx.step)
        output.update(tts_seconds=tts.duration)
    return output


HANDLERS = {key: fake_step for key in STEP_KEYS}
