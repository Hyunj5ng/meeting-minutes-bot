"""add project memory and context entry_type

Revision ID: c3d8e91a7b42
Revises: f7a2e8c44b91
Create Date: 2026-06-11

- projects.memory: 프로젝트 누적 AI 메모리 (회의록 생성마다 갱신)
- projects.memory_updated_at: 메모리 갱신 시각
- context_entries.entry_type: 'term' (용어 교정) | 'style' (스타일 선호)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3d8e91a7b42"
down_revision: Union[str, Sequence[str], None] = "f7a2e8c44b91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("memory", sa.Text(), nullable=True, comment="AI 누적 메모리 (결정사항/진행 주제/인물·역할)"),
    )
    op.add_column(
        "projects",
        sa.Column("memory_updated_at", sa.DateTime(timezone=True), nullable=True, comment="메모리 갱신 시각"),
    )
    op.add_column(
        "context_entries",
        sa.Column(
            "entry_type",
            sa.String(length=20),
            nullable=False,
            server_default="term",
            comment="term (용어 교정) | style (스타일 선호)",
        ),
    )


def downgrade() -> None:
    op.drop_column("context_entries", "entry_type")
    op.drop_column("projects", "memory_updated_at")
    op.drop_column("projects", "memory")
