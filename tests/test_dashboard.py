from datetime import datetime

from app.core.models import Product, Project, UsageLog
from app.pipeline import engine
from app.pipeline.worker import wait_until_idle
from app.web.dashboard import month_start_utc


def _project(db, title, status="ready", board="신규"):
    with db.session_factory() as s:
        p = Product(name=f"{title} 제품")
        s.add(p)
        s.flush()
        proj = Project(product_id=p.id, title=title, status=status, board_status=board)
        s.add(proj)
        s.commit()
        return proj.id


def test_empty_board_guides_first_steps(client):
    page = client.get("/").text
    for col in ("신규", "제작 중", "검수 대기", "완료"):
        assert col in page
    assert "제품 등록" in page and 'href="/products/new"' in page


def test_projects_go_to_right_columns(client, test_app):
    db, worker = test_app.state.db, test_app.state.worker
    _project(db, "새 콘텐츠")
    done_id = _project(db, "끝난 콘텐츠")
    failed_id = _project(db, "오류 콘텐츠")

    with db.session_factory() as s:
        engine.start(s, done_id)
    wait_until_idle(worker)
    worker.settings.fake_fail_step = "planning"
    with db.session_factory() as s:
        engine.start(s, failed_id)
    wait_until_idle(worker)

    page = client.get("/").text
    board = {
        name: page.split(f"<strong>{name}</strong>")[1].split("</section>")[0]
        for name in ("신규", "제작 중", "검수 대기")
    }
    assert "새 콘텐츠" in board["신규"]
    assert (
        "⚠ 오류 콘텐츠" in board["제작 중"]
        and "오류로 멈춤" in board["제작 중"]
        and "2/7" in board["제작 중"]
    )
    assert "⚠ 끝난 콘텐츠" in board["검수 대기"] and "확인하기" in board["검수 대기"]
    assert f'href="/projects/{done_id}"' in page


def test_running_board_auto_refreshes(client, test_app):
    db = test_app.state.db
    pid = _project(db, "진행 중")
    assert 'http-equiv="refresh"' not in client.get("/").text
    with db.session_factory() as s:
        engine.start(s, pid)
    page = client.get("/").text
    assert 'http-equiv="refresh"' in page and "0/7" in page


def test_month_cost_only_counts_this_month(client, test_app):
    db = test_app.state.db
    with db.session_factory() as s:
        s.add(UsageLog(provider="fake", unit="tokens", actual_cost=1234.4))
        s.add(UsageLog(provider="fake", unit="tokens", actual_cost=9999, created_at=datetime(2020, 1, 1)))
        s.commit()
    assert "이번 달 AI 비용 <strong" in client.get("/").text
    assert "1,234원" in client.get("/").text


def test_month_start():
    start = month_start_utc(datetime(2026, 11, 24, 12, 0).astimezone())
    assert start.tzinfo is not None
    assert start.astimezone().day == 1 and start.astimezone().hour == 0


def test_nav_has_all_menus(client):
    page = client.get("/products").text
    assert all(f'href="{u}"' in page for u in ("/", "/projects", "/products"))
