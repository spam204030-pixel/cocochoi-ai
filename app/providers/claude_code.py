"""Claude 구독 반자동 연결 (/공장). 설계서 V4-4.

프로그램이 요청서를 storage/bridge/requests/ 에 쓰면, 대표님이 Claude Code 에서 /공장 을 입력하고,
Claude 가 응답서를 storage/bridge/responses/ 에 쓴다. 프로그램은 응답서를 형식 검사한 뒤 다음 단계로 넘긴다.
"""

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ValidationError
from sqlalchemy import select

from app.core.logging import get_logger
from app.core.models import BridgeRequest, UsageLog, utcnow

log = get_logger("bridge")
MAX_ATTEMPTS = 2  # 첫 요청 + 형식 오류 시 재요청 1회


class ConnectionCheck(BaseModel):
    """1-1 연결 확인용 응답 형식. 실제 분석 형식은 1-6, 1-8 등에서 추가한다."""

    ok: bool
    note: str = ""


SCHEMAS: dict[str, type[BaseModel]] = {"PING": ConnectionCheck}


@dataclass
class BridgeResult:
    request: BridgeRequest
    kind: str  # done / retry / failed / cancelled
    data: dict | None = None
    error: str = ""


class ClaudeCodeBridge:
    def __init__(self, bridge_dir: Path, session_factory) -> None:
        self.dir = bridge_dir
        self.session_factory = session_factory
        for sub in ("requests", "responses", "done"):
            (self.dir / sub).mkdir(parents=True, exist_ok=True)

    def _req_path(self, rid: str) -> Path:
        return self.dir / "requests" / f"{rid}.json"

    def _resp_path(self, rid: str) -> Path:
        return self.dir / "responses" / f"{rid}.json"

    def _write_request(self, row: BridgeRequest, prompt: str, attachments: list[str]) -> None:
        schema = SCHEMAS[row.call_key].model_json_schema()
        body = {
            "request_id": row.request_id,
            "project_id": row.project_id,
            "batch": row.batch,
            "call": row.call_key,
            "step": row.step_key,
            "prompt": prompt,
            "attachments": attachments,
            "output_schema": schema,
            "retry_reason": row.retry_reason,
            "response_path": str(self._resp_path(row.request_id)),
        }
        self._req_path(row.request_id).write_text(json.dumps(body, ensure_ascii=False, indent=2), "utf-8")

    def create(self, *, project_id, job_id, run_id, step, call, batch, prompt, attachments=()) -> str:
        rid = f"p{project_id}-{step}-r{run_id}"
        with self.session_factory() as s:
            row = BridgeRequest(
                request_id=rid,
                project_id=project_id,
                job_id=job_id,
                run_id=run_id,
                step_key=step,
                call_key=call,
                batch=batch,
            )
            s.add(row)
            s.flush()
            self._write_request(row, prompt, list(attachments))
            s.commit()
        log.info("요청서 생성 %s (묶음 %s)", rid, batch)
        return rid

    def waiting(self, session) -> list[BridgeRequest]:
        return list(session.scalars(select(BridgeRequest).where(BridgeRequest.status == "waiting")))

    def check(self, session, row: BridgeRequest) -> BridgeResult | None:
        """응답서가 있으면 검사해서 결과를 돌려준다. 아직 없으면 None."""
        resp = self._resp_path(row.request_id)
        if not resp.exists():
            return None
        raw = resp.read_text("utf-8-sig")
        try:
            data = SCHEMAS[row.call_key].model_validate(json.loads(raw)).model_dump()
        except (json.JSONDecodeError, ValidationError) as exc:
            reason = f"응답 형식 오류: {str(exc)[:500]}"
            resp.unlink()
            if row.attempts >= MAX_ATTEMPTS:
                row.status, row.finished_at = "failed", utcnow()
                self._archive(row.request_id)
                log.warning("응답 형식 두 번 실패 %s", row.request_id)
                return BridgeResult(row, "failed", error=reason)
            row.attempts += 1
            row.retry_reason = reason
            body = json.loads(self._req_path(row.request_id).read_text("utf-8"))
            self._write_request(row, body["prompt"], body["attachments"])
            log.info("재요청 %s", row.request_id)
            return BridgeResult(row, "retry", error=reason)
        row.status, row.finished_at = "done", utcnow()
        session.add(
            UsageLog(
                project_id=row.project_id,
                role_key=row.step_key,
                call_key=row.call_key,
                provider="claude_code",
                model="구독",
                unit="request",
                input_units=self._req_path(row.request_id).stat().st_size,
                output_units=len(raw),
                est_cost=0,
                actual_cost=0,
                attempt=row.attempts,
                ok=True,
            )
        )
        self._archive(row.request_id)
        log.info("응답 반영 %s", row.request_id)
        return BridgeResult(row, "done", data=data)

    def cancel(self, row: BridgeRequest) -> None:
        row.status, row.finished_at = "cancelled", utcnow()
        self._archive(row.request_id)

    def _archive(self, rid: str) -> None:
        for path in (self._req_path(rid), self._resp_path(rid)):
            if path.exists():
                target = self.dir / "done" / path.name.replace(".json", f".{path.parent.name}.json")
                shutil.move(str(path), str(target))
