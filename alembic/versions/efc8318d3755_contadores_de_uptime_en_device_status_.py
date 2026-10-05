"""contadores de uptime en device_status_summary

Revision ID: efc8318d3755
Revises: f38e26304255
Create Date: 2026-10-04 20:37:35.119609

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'efc8318d3755'
down_revision: Union[str, Sequence[str], None] = 'f38e26304255'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade():
    op.add_column('device_status_summary', sa.Column('total_checks', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('device_status_summary', sa.Column('total_failures', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('device_status_summary', sa.Column('uptime_percentage', sa.Float(), nullable=True))


def downgrade():
    op.drop_column('device_status_summary', 'uptime_percentage')
    op.drop_column('device_status_summary', 'total_failures')
    op.drop_column('device_status_summary', 'total_checks')
