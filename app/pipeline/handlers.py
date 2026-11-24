"""단계 처리기. 지금은 모두 '시험 실행(가짜 작업)'이다.

실제 AI·편집 기능은 Phase 1 이후 단계별로 이 자리를 교체한다.
가짜 작업은 비용이 들지 않고, 결과에 fake=True 가 표시된다.
"""

import time

from app.core.errors import AppError, ErrorCode
from app.pipeline.steps import STEP_KEYS, STEP_NAMES


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
    return {"fake": True, "message": f"{STEP_NAMES[ctx.step]} 시험 실행 완료 (실제 AI 사용 안 함)"}


HANDLERS = {key: fake_step for key in STEP_KEYS}
