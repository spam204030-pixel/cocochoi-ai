"""DB 연결 — SQLite 파일(storage/cocochoi.db) 하나. 표 구조는 Alembic 변경 기록으로만 만든다."""

from collections.abc import Iterator
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import PROJECT_ROOT

MIGRATIONS_DIR = PROJECT_ROOT / "migrations"


def make_engine(db_url: str) -> Engine:
    engine = create_engine(db_url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")  # 연결된 자료가 어긋나지 않게
        cur.execute("PRAGMA journal_mode=WAL")  # 화면과 작업자가 동시에 읽고 쓸 수 있게
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    return engine


def alembic_config(db_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def upgrade_db(db_url: str) -> None:
    """DB를 최신 구조로 맞춘다. 이미 최신이면 아무것도 바꾸지 않고, 기존 데이터는 지우지 않는다."""
    command.upgrade(alembic_config(db_url), "head")


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.url = f"sqlite:///{db_path.as_posix()}"
        self.engine = make_engine(self.url)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def init(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        upgrade_db(self.url)

    def session(self) -> Iterator[Session]:
        with self.session_factory() as session:
            yield session

    def is_ok(self) -> bool:
        try:
            with self.engine.connect() as conn:
                conn.exec_driver_sql("SELECT 1")
            return True
        except Exception:
            return False
