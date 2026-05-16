"""add registration system (system_settings, invite_codes, invite_usages, is_admin)

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-05-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2f3a4b5c6d7'
down_revision: Union[str, Sequence[str], None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # system_settings table
    op.create_table(
        'system_settings',
        sa.Column('key', sa.String(64), nullable=False),
        sa.Column('value', sa.String(4096), nullable=False, server_default=''),
        sa.PrimaryKeyConstraint('key'),
    )

    # invite_codes table
    op.create_table(
        'invite_codes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(32), nullable=False),
        sa.Column('creator_user_id', sa.Integer(), nullable=True),
        sa.Column('max_uses', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('current_uses', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
        sa.ForeignKeyConstraint(['creator_user_id'], ['users.id'], ),
    )
    op.create_index('ix_invite_codes_code', 'invite_codes', ['code'])

    # invite_usages table
    op.create_table(
        'invite_usages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('invite_code_id', sa.Integer(), nullable=False),
        sa.Column('used_by_user_id', sa.Integer(), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['invite_code_id'], ['invite_codes.id'], ),
        sa.ForeignKeyConstraint(['used_by_user_id'], ['users.id'], ),
    )

    # is_admin on users
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_admin', sa.Boolean(), nullable=False, server_default='0'))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('is_admin')

    op.drop_table('invite_usages')
    op.drop_index('ix_invite_codes_code', 'invite_codes')
    op.drop_table('invite_codes')
    op.drop_table('system_settings')
