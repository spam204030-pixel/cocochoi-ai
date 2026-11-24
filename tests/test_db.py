import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from app.core.db import Database
from app.core.models import Asset, Base, Job, Product, Project, ProjectAsset, RoleRun

TABLES = {"products", "assets", "projects", "project_assets", "jobs", "role_runs"}


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    database.init()
    return database


def test_migration_creates_six_tables(db):
    tables = set(inspect(db.engine).get_table_names())
    assert TABLES <= tables
    assert "alembic_version" in tables


def test_migration_matches_models(db):
    """models.py 와 변경 기록(Alembic)이 어긋나지 않았는지 확인."""
    with db.engine.connect() as conn:
        diff = compare_metadata(
            MigrationContext.configure(conn, opts={"render_as_batch": True}), Base.metadata
        )
    assert diff == []


def test_save_and_read_all_tables(db):
    with db.session_factory() as s:
        product = Product(name="겨울 기모 니삭스", price=19800, features=["무릎 위 길이"])
        s.add(product)
        s.flush()
        asset = Asset(product_id=product.id, kind="footage", path="assets/1/socks.mp4", duration=20.8)
        project = Project(product_id=product.id, platforms=["youtube", "instagram"])
        s.add_all([asset, project])
        s.flush()
        s.add(ProjectAsset(project_id=project.id, asset_id=asset.id))
        s.add(Job(project_id=project.id, task="analyze_video", payload_json={"asset_id": asset.id}))
        s.add(RoleRun(project_id=project.id, role_key="product_analysis", call_key="B"))
        s.commit()

    with db.session_factory() as s:
        p = s.scalar(select(Project))
        assert p.target_length == 20 and p.quality_threshold == 80 and p.board_status == "신규"
        assert s.scalar(select(Asset)).path == "assets/1/socks.mp4"  # 파일이 아니라 경로만 저장
        assert s.scalar(select(Job)).status == "queued"
        assert s.scalar(select(RoleRun)).status == "pending"
        assert s.scalar(select(Product)).features == ["무릎 위 길이"]


def test_upgrade_again_keeps_existing_data(db):
    with db.session_factory() as s:
        s.add(Product(name="카멜 코트"))
        s.commit()
    db.init()  # 프로그램을 다시 켠 것과 같음
    with db.session_factory() as s:
        assert s.scalar(select(Product)).name == "카멜 코트"


def test_duplicate_file_hash_is_rejected(db):
    with db.session_factory() as s:
        s.add(Asset(kind="product_photo", path="a.jpg", file_hash="abc"))
        s.add(Asset(kind="product_photo", path="b.jpg", file_hash="abc"))
        with pytest.raises(IntegrityError):
            s.commit()


def test_project_needs_existing_product(db):
    with db.session_factory() as s:
        s.add(Project(product_id=999))
        with pytest.raises(IntegrityError):
            s.commit()


def test_app_start_creates_db_file(client, tmp_settings):
    assert tmp_settings.db_path.exists()
    assert client.get("/api/health").json()["checks"]["db"] == "정상"
