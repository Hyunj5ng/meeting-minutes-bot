"""add_projects_and_contexts

Revision ID: f7a2e8c44b91
Revises: d9b3c25a1f8e
Create Date: 2026-06-04 15:00:00.000000

프로젝트 + 컨텍스트 글로서리 테이블 추가.
transcript_records.project_id 컬럼 추가 (nullable, 기존 데이터 호환).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f7a2e8c44b91"
down_revision: Union[str, Sequence[str], None] = "d9b3c25a1f8e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # 1. projects 테이블
    if "projects" not in existing_tables:
        op.create_table(
            "projects",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index("ix_projects_user_id", "projects", ["user_id"])
        op.create_index("ix_projects_user_name", "projects", ["user_id", "name"])

    # 2. context_entries 테이블
    if "context_entries" not in existing_tables:
        op.create_table(
            "context_entries",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "project_id",
                sa.Integer(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("term", sa.String(length=200), nullable=False),
            sa.Column("correction", sa.String(length=500), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column(
                "source",
                sa.String(length=20),
                nullable=False,
                server_default="manual",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index("ix_context_entries_user_id", "context_entries", ["user_id"])
        op.create_index("ix_context_entries_project_id", "context_entries", ["project_id"])
        op.create_index(
            "ix_context_entries_user_project",
            "context_entries",
            ["user_id", "project_id"],
        )

    # 3. transcript_records.project_id 컬럼 추가
    existing_cols = [c["name"] for c in inspector.get_columns("transcript_records")]
    if "project_id" not in existing_cols:
        with op.batch_alter_table("transcript_records", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("project_id", sa.Integer(), nullable=True)
            )
            batch_op.create_foreign_key(
                "fk_transcript_records_project_id",
                "projects",
                ["project_id"],
                ["id"],
                ondelete="SET NULL",
            )
            batch_op.create_index("ix_transcript_records_project_id", ["project_id"])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("transcript_records", schema=None) as batch_op:
        batch_op.drop_index("ix_transcript_records_project_id")
        batch_op.drop_constraint("fk_transcript_records_project_id", type_="foreignkey")
        batch_op.drop_column("project_id")

    with op.batch_alter_table("context_entries") as batch_op:
        batch_op.drop_index("ix_context_entries_user_project")
        batch_op.drop_index("ix_context_entries_project_id")
        batch_op.drop_index("ix_context_entries_user_id")
    op.drop_table("context_entries")

    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_index("ix_projects_user_name")
        batch_op.drop_index("ix_projects_user_id")
    op.drop_table("projects")
