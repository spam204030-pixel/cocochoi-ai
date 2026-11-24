"""단계 처리기.

- fake 모드: 모든 단계가 시험 실행(가짜 작업). 비용 0원, 결과에 fake=True
- claude_code 모드: AI 단계는 /공장 요청서를 만들고 대기(StepWaiting), 나머지는 아직 시험 실행
  (실제 분석·검사 내용은 1-2 이후 작업에서 단계별로 교체)
"""

import time

from app.core.errors import AppError, ErrorCode
from app.pipeline.steps import AI_STEPS, STEP_KEYS, STEP_NAMES
from app.providers.base import LLMRequest

# 단계 → AI 호출 (PROMPTS.md). 전략·기획은 호출 C 하나로 함께 처리
STEP_CALLS = {"analysis": "B", "planning": "D", "captions": "G1"}


class StepCancelled(Exception):
    """사용자가 취소함."""


class StepWaiting(Exception):
    """/공장 요청서를 만들고 Claude 응답을 기다림."""

    def __init__(self, request_id: str) -> None:
        super().__init__(request_id)
        self.request_id = request_id


PING_PROMPT = """[연결 확인 — 작업 1-1]
이 요청서는 프로그램과 Claude 구독(/공장) 연결을 확인하기 위한 것이다. 실제 분석은 하지 않는다.
output_schema 에 맞춰 {{"ok": true, "note": "묶음 {batch} ({step}) 연결 확인"}} 형식의
JSON 하나만 응답서로 쓴다.
"""


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
    return output


def ai_step(ctx) -> dict:
    """claude_code 모드: 요청서를 만들고 대기. fake 모드: 시험 실행."""
    if ctx.settings.ai_mode != "claude_code" or ctx.bridge is None:
        return fake_step(ctx)
    if ctx.should_stop():
        raise StepCancelled
    call, batch = AI_STEPS[ctx.step]
    prompt, attachments, extra = PING_PROMPT.format(batch=batch, step=STEP_NAMES[ctx.step]), [], None
    if call == "ANALYSIS":
        prompt, attachments, extra = analysis_request(ctx)
    rid = ctx.bridge.create(
        project_id=ctx.project_id,
        job_id=ctx.job_id,
        run_id=ctx.run.id,
        step=ctx.step,
        call=call,
        batch=batch,
        prompt=prompt,
        attachments=attachments,
        extra=extra,
    )
    raise StepWaiting(rid)


def analysis_request(ctx) -> tuple[str, list[str], dict]:
    """작업 B: 상품 정보·사진 + 영상 격자·장면 목록으로 분석 요청서를 만든다."""
    from app.assets.service import VIDEO_KINDS, asset_file
    from app.core.models import Product, Project
    from app.media.frames import labels
    from app.media.scenes import segments_for
    from app.projects.service import project_assets
    from app.prompts import analysis

    root = ctx.settings.storage_dir
    with ctx.session_factory() as s:
        project = s.get(Project, ctx.project_id)
        product = s.get(Product, project.product_id)
        assets = project_assets(s, ctx.project_id)
        info = {
            "상품명": product.name,
            "카테고리": product.category,
            "설명": product.description,
            "가격": product.price,
            "특징": product.features,
            "구매 링크": product.purchase_url,
        }
        info = {k: v for k, v in info.items() if v}
        attach: list[tuple[str, str]] = []
        for n, a in enumerate([a for a in assets if a.kind == "product_photo"], 1):
            path = asset_file(ctx.settings, a)
            if path.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
                path = root / "assets" / str(a.id) / "thumb.jpg"
            attach.append((f"상품 사진 {n}", str(path)))
        videos = [a for a in assets if a.kind in VIDEO_KINDS]
        segs = segments_for(s, [a.id for a in videos])
        scenes = []
        for v, a in enumerate(videos, 1):
            for grid in sorted((root / "frames" / str(a.id)).glob("grid_*.jpg")):
                attach.append((f"영상{v} 장면 격자 {grid.stem[-2:]}", str(grid)))
            for sg in segs.get(a.id, []):
                if sg.thumb_path:
                    attach.append((f"[{sg.id}] 영상{v} 장면{sg.idx} 사진", str(root / sg.thumb_path)))
                scenes.append(
                    {
                        "id": sg.id,
                        "video": v,
                        "idx": sg.idx,
                        "start": sg.start,
                        "end": sg.end,
                        "warnings": labels(sg),
                        "transcript_zh": sg.transcript_zh,
                    }
                )
        prompt = analysis.build(info, product.detail_text or "", attach, scenes)
    extra = {"valid_segment_ids": [sc["id"] for sc in scenes], "prompt_version": analysis.VERSION}
    return prompt, [p for _, p in attach], extra


def media_prep(ctx) -> dict:
    """소재 준비: 영상마다 장면 나누기 (작업 1-2). 이미 나눈 영상은 건너뛴다."""
    from app.assets.service import VIDEO_KINDS, asset_file
    from app.media.frames import measure_segments
    from app.media.scenes import segment_asset
    from app.media.transcribe import transcribe_asset
    from app.projects.service import project_assets

    counts, lines = {}, {}
    with ctx.session_factory() as s:
        videos = [a for a in project_assets(s, ctx.project_id) if a.kind in VIDEO_KINDS]
        for asset in videos:
            if ctx.should_stop():
                raise StepCancelled
            path = asset_file(ctx.settings, asset)
            counts[str(asset.id)] = segment_asset(s, asset, path)
            measure_segments(s, asset, path, ctx.settings.storage_dir)
            s.commit()
            if ctx.should_stop():
                raise StepCancelled
            lines[str(asset.id)] = transcribe_asset(
                s, asset, path, ctx.settings.storage_dir, ctx.settings.whisper_model
            )
            s.commit()
    return {
        "message": f"영상 {len(videos)}개 장면 나누기·사진·받아쓰기 완료",
        "segments": counts,
        "transcript_lines": lines,
    }


HANDLERS = {key: (ai_step if key in AI_STEPS else fake_step) for key in STEP_KEYS}
HANDLERS["media_prep"] = media_prep
