"""제작 단계 정의 (설계서 V4-5).

AI 단계(상품·소재 분석, 기획·대본, 플랫폼 캡션)는 Claude 구독(/공장)으로 처리하고,
나머지는 프로그램(코드)이 처리한다. 마지막 뒤에는 대표님 확인.
"""

STEPS: list[tuple[str, str]] = [
    ("media_prep", "소재 준비"),
    ("analysis", "상품·소재 분석"),
    ("planning", "후킹·기획·대본"),
    ("script_check", "장면 연결 검사"),
    ("captions", "플랫폼 캡션"),
    ("caption_check", "캡션 검사"),
    ("package", "결과 패키지"),
]
# AI 단계 → (호출, 묶음 번호). /공장 한 번에 같은 묶음을 모두 처리
AI_STEPS = {"analysis": ("PING", 1), "planning": ("PING", 2), "captions": ("PING", 3)}
STEP_KEYS = [k for k, _ in STEPS]
STEP_NAMES = dict(STEPS)

# role_runs.status → 화면 표시
DISPLAY = {
    "pending": ("대기", "○"),
    "queued": ("대기", "○"),
    "paused": ("대기", "○"),
    "stale": ("대기", "○"),
    "cancelled": ("대기", "○"),
    "running": ("진행 중", "▶"),
    "succeeded": ("완료", "✅"),
    "failed": ("오류", "✖"),
    "waiting_user": ("사용자 확인 필요", "⚠"),
    "waiting_ai": ("Claude 처리 대기", "⏳"),
}

# projects.status → 화면 이름, 현황판 칸
PROJECT_STATUS = {
    "ready": ("준비됨", "신규"),
    "running": ("제작 중", "제작 중"),
    "paused": ("일시정지", "제작 중"),
    "failed": ("오류로 멈춤", "제작 중"),
    "cancelled": ("취소됨", "신규"),
    "waiting_user": ("검수 대기", "검수 대기"),
    "done": ("완료", "완료"),
}


def next_step(step_key: str) -> str | None:
    i = STEP_KEYS.index(step_key)
    return STEP_KEYS[i + 1] if i + 1 < len(STEP_KEYS) else None
