"""footage_segments 대표 사진·화질 칸 추가

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("footage_segments") as batch:
        batch.add_column(sa.Column("thumb_path", sa.String(length=300), nullable=True))
        batch.add_column(sa.Column("sharpness", sa.Float(), nullable=True))
        batch.add_column(sa.Column("shake", sa.Float(), nullable=True))
        batch.add_column(sa.Column("brightness", sa.Float(), nullable=True))
        batch.add_column(sa.Column("quality", sa.Integer(), nullable=True))


def downgrade() -> None:
    raise RuntimeError("데이터 보호를 위해 되돌리기(downgrade)는 막혀 있습니다.")
