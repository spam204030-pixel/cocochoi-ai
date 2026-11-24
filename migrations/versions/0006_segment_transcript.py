"""footage_segments 원본 대사(중국어) 칸 추가

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("footage_segments") as batch:
        batch.add_column(sa.Column("transcript_zh", sa.Text(), nullable=True))


def downgrade() -> None:
    raise RuntimeError("데이터 보호를 위해 되돌리기(downgrade)는 막혀 있습니다.")
