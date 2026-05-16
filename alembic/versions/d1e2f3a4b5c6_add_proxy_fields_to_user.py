"""add proxy fields to user

Revision ID: d1e2f3a4b5c6
Revises: c5c513b6569a
Create Date: 2026-05-16 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, Sequence[str], None] = 'c5c513b6569a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('http_proxy', sa.String(512), nullable=True))
        batch_op.add_column(sa.Column('https_proxy', sa.String(512), nullable=True))
        batch_op.add_column(sa.Column('ytdlp_proxy', sa.String(512), nullable=True))
        batch_op.add_column(sa.Column('ytdlp_cookies', sa.String(512), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('ytdlp_cookies')
        batch_op.drop_column('ytdlp_proxy')
        batch_op.drop_column('https_proxy')
        batch_op.drop_column('http_proxy')
