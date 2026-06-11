"""add summary viewed_at (읽지 않음 표시용)

Revision ID: d4f1a2b3c5e6
Revises: c3d8e91a7b42
Create Date: 2026-06-11

- summary_records.viewed_at: 사용자가 처음 열람한 시각 (NULL = 읽지 않음)
- 기존 레코드는 이미 본 것으로 간주하여 현재 시각으로 백필
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4f1a2b3c5e6"
down_revision: Union[str, Sequence[str], None] = "c3d8e91a7b42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "summary_records",
        sa.Column("viewed_at", sa.DateTime(timezone=True), nullable=True, comment="처음 열람한 시각 (NULL = 읽지 않음)"),
    )
    # 기존 레코드는 전부 '읽음' 처리 (새 기능 도입 시 전부 안읽음으로 표시되는 것 방지)
    op.execute("UPDATE summary_records SET viewed_at = CURRENT_TIMESTAMP")


def downgrade() -> None:
    op.drop_column("summary_records", "viewed_at")
