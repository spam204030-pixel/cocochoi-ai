"""제작 단계 정의 (설계서 2-2 실행 파이프라인).

9단계 중 1~8단계가 "제작"이고, 9단계(성과 분석)는 게시 후 따로 실행한다.
화면 표시 상태는 5종: 대기 / 진행 중 / 완료 / 오류 / 사용자 확인 필요.
"""

STEPS: list[tuple[str, str]] = [
    ("product_analysis", "상품 분석"),
    ("media_analysis", "영상·사진 분석"),
    ("strategy", "전략"),
    ("planning", "기획"),
    ("script", "대본"),
    ("production", "영상 제작"),
    ("quality", "품질 검수"),
    ("platform", "플랫폼 게시물"),
]
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
