"""add_summary_versions

Revision ID: d9b3c25a1f8e
Revises: 8571c10fd641
Create Date: 2026-06-04 12:00:00.000000

요약 버전 이력 테이블 추가.
기존 summary_records 전체에 대해 v1(ai_initial)을 백필한다.
(실제 AI 원본인지 사용자 수정본인지는 구분 불가하지만,
 이 마이그레이션 이후의 수정은 새 버전으로 누적된다.)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d9b3c25a1f8e"
down_revision: Union[str, Sequence[str], None] = "8571c10fd641"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "summary_versions" not in inspector.get_table_names():
        op.create_table(
            "summary_versions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "summary_id",
                sa.Integer(),
                sa.ForeignKey("summary_records.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("version_no", sa.Integer(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("source", sa.String(length=20), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index(
            "ix_summary_versions_summary_id",
            "summary_versions",
            ["summary_id"],
        )
        op.create_index(
            "ix_summary_versions_summary_version",
            "summary_versions",
            ["summary_id", "version_no"],
            unique=True,
        )

        # 기존 요약 전체에 v1(ai_initial) 백필
        # NOTE: 실제로는 사용자가 이미 수정한 본도 있을 수 있지만,
        # 원본을 복구할 수 없으므로 모두 v1로 시작.
        op.execute(
            sa.text(
                "INSERT INTO summary_versions (summary_id, version_no, content, source, created_at) "
                "SELECT id, 1, summary, 'ai_initial', created_at FROM summary_records"
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("summary_versions") as batch_op:
        batch_op.drop_index("ix_summary_versions_summary_version")
        batch_op.drop_index("ix_summary_versions_summary_id")
    op.drop_table("summary_versions")
