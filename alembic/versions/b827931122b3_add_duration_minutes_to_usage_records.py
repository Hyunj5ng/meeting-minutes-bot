"""add_duration_minutes_to_usage_records

Revision ID: b827931122b3
Revises: a6c5aa937945
Create Date: 2026-03-12 19:09:18.419163

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'b827931122b3'
down_revision: Union[str, Sequence[str], None] = 'a6c5aa937945'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_cols = [c['name'] for c in inspector.get_columns('usage_records')]
    if 'duration_minutes' in existing_cols:
        return
    with op.batch_alter_table('usage_records', schema=None) as batch_op:
        batch_op.add_column(sa.Column('duration_minutes', sa.Float(), nullable=True, comment='오디오 길이 (분, STT 전용)'))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('usage_records', schema=None) as batch_op:
        batch_op.drop_column('duration_minutes')
