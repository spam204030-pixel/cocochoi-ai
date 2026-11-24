"""Phase 0 DB 표 6개 (설계서 7-2). 영상·사진 파일 자체는 저장하지 않고 경로만 저장한다.

표를 바꿀 때는 이 파일과 함께 migrations/versions/ 에 변경 기록(Alembic)을 추가한다.
기존 데이터를 지우는 변경(표·칸 삭제)은 대표 승인 없이 하지 않는다.
"""

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Product(Base):
    """제품. 필수 입력은 이름뿐."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    price: Mapped[int | None] = mapped_column(Integer)  # 원
    detail_text: Mapped[str | None] = mapped_column(Text)  # 상세페이지 복사 텍스트
    purchase_url: Mapped[str | None] = mapped_column(String(1000))
    features: Mapped[list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class Asset(Base):
    """사진·영상·음원 등 모든 파일. 파일은 storage/assets/ 에 두고 여기에는 경로만 저장."""

    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), index=True)
    # product_photo / footage / own_clip / bgm / sfx / narration / generated / other
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    path: Mapped[str] = mapped_column(String(1000), nullable=False)  # storage/ 기준 상대 경로
    original_name: Mapped[str | None] = mapped_column(String(500))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    source_memo: Mapped[str | None] = mapped_column(Text)
    duration: Mapped[float | None] = mapped_column(Float)  # 초
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    fps: Mapped[float | None] = mapped_column(Float)
    has_audio: Mapped[bool | None] = mapped_column(Boolean)
    file_size: Mapped[int | None] = mapped_column(Integer)  # 바이트
    file_hash: Mapped[str | None] = mapped_column(String(64), index=True, unique=True)  # 중복 업로드 방지
    analysis_status: Mapped[str] = mapped_column(String(20), default="none", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Project(Base):
    """콘텐츠 1편."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), index=True)
    brand_profile_id: Mapped[int | None] = mapped_column(Integer)  # brand_profiles 표는 이후 Phase에서 추가
    title: Mapped[str | None] = mapped_column(String(300))
    target_length: Mapped[int] = mapped_column(Integer, default=20, nullable=False)  # 초
    style_preset: Mapped[str | None] = mapped_column(String(40))
    platforms: Mapped[list | None] = mapped_column(JSON)
    narration_mode: Mapped[str] = mapped_column(String(20), default="tts", nullable=False)  # tts / own_voice
    tts_voice: Mapped[str | None] = mapped_column(String(100))
    ad_mode: Mapped[str] = mapped_column(String(20), default="none", nullable=False)  # none / ad / affiliate
    auto_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    budget_limit: Mapped[int | None] = mapped_column(Integer)  # 원
    quality_threshold: Mapped[int] = mapped_column(Integer, default=80, nullable=False)
    max_fix_rounds: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    board_status: Mapped[str] = mapped_column(String(20), default="신규", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="ready", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class ProjectAsset(Base):
    """프로젝트에 쓸 소재 연결."""

    __tablename__ = "project_assets"

    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Job(Base):
    """작업 대기열. status: queued / running / done / failed / cancelled / paused"""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    step_key: Mapped[str | None] = mapped_column(String(40))
    task: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    payload_json: Mapped[dict | None] = mapped_column(JSON)
    input_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RoleRun(Base):
    """단계·AI 호출 실행 기록 (버전별로 쌓이며 덮어쓰지 않음)."""

    __tablename__ = "role_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    role_key: Mapped[str] = mapped_column(String(40), nullable=False)  # 9단계 중 어느 단계
    call_key: Mapped[str | None] = mapped_column(String(10))  # A~H, G1, G2
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # pending / queued / running / succeeded / failed / stale / skipped / waiting_user / cancelled / paused
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(20))
    input_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    input_snapshot_path: Mapped[str | None] = mapped_column(String(1000))
    raw_response: Mapped[str | None] = mapped_column(Text)
    output_json: Mapped[dict | None] = mapped_column(JSON)
    self_score: Mapped[float | None] = mapped_column(Float)
    self_score_detail: Mapped[dict | None] = mapped_column(JSON)
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_adopted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(40))
    model: Mapped[str | None] = mapped_column(String(100))
    est_cost: Mapped[float | None] = mapped_column(Float)  # 원
    actual_cost: Mapped[float | None] = mapped_column(Float)  # 원
    error_code: Mapped[str | None] = mapped_column(String(40))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UsageLog(Base):
    """AI·음성 사용량과 비용 기록 (호출 1번 = 1줄). 비용 보고 화면의 원자료."""

    __tablename__ = "usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    role_key: Mapped[str | None] = mapped_column(String(40))  # 단계
    call_key: Mapped[str | None] = mapped_column(String(10))  # A~H, tts, stt
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str | None] = mapped_column(String(100))
    unit: Mapped[str] = mapped_column(String(20), nullable=False)  # tokens / chars / seconds
    input_units: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_units: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    est_cost: Mapped[float | None] = mapped_column(Float)  # 원 (호출 전 예상)
    actual_cost: Mapped[float] = mapped_column(Float, default=0, nullable=False)  # 원
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    ok: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class BridgeRequest(Base):
    """/공장 요청서 (Claude 구독 반자동 연결). 파일은 storage/bridge/ 에 있다."""

    __tablename__ = "bridge_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    job_id: Mapped[int | None] = mapped_column(Integer)
    run_id: Mapped[int | None] = mapped_column(Integer)
    step_key: Mapped[str] = mapped_column(String(40), nullable=False)
    call_key: Mapped[str] = mapped_column(String(20), nullable=False)
    batch: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # waiting / done / failed / cancelled
    status: Mapped[str] = mapped_column(String(20), default="waiting", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    retry_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FootageSegment(Base):
    """영상 장면 (설계서 V4-7, 작업 1-2). 시간은 코드가 영상에서 측정한 값."""

    __tablename__ = "footage_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    idx: Mapped[int] = mapped_column(Integer, nullable=False)  # 1부터
    start: Mapped[float] = mapped_column(Float, nullable=False)  # 초
    end: Mapped[float] = mapped_column(Float, nullable=False)
    duration: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
