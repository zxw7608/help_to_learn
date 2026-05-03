"""add ai config to user + analysis_records table

Revision ID: 9a1b2c3d4e5f
Revises: 81d962b1773d
Create Date: 2026-05-03 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '9a1b2c3d4e5f'
down_revision: Union[str, Sequence[str], None] = '81d962b1773d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ai_base_url', sqlmodel.sql.sqltypes.AutoString(length=512), nullable=True))
        batch_op.add_column(sa.Column('ai_api_key', sqlmodel.sql.sqltypes.AutoString(length=256), nullable=True))

    op.create_table(
        'analysis_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('segment_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('selected_phrase', sa.Text(), nullable=False),
        sa.Column('analysis', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['segment_id'], ['segments.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('analysis_records', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_analysis_records_segment_id'), ['segment_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_analysis_records_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('ai_api_key')
        batch_op.drop_column('ai_base_url')

    op.drop_table('analysis_records')
