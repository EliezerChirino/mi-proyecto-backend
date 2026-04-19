"""add_dns_to_devices

Revision ID: f38e26304255
Revises: 7ce979ae68b7
Create Date: 2025-12-02 11:02:30.605615

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f38e26304255'
down_revision: Union[str, Sequence[str], None] = '7ce979ae68b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade():
    # Agregar columna dns
    op.add_column('devices', sa.Column('dns', sa.String(400), nullable=True))


def downgrade():
    # Eliminar columna dns si se revierte
    op.drop_column('devices', 'dns')