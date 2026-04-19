"""add_handles_to_device_connections

Revision ID: 7ce979ae68b7
Revises: 76d0787d3140
Create Date: 2025-12-01 10:50:45.463969

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7ce979ae68b7'
down_revision: Union[str, Sequence[str], None] = '76d0787d3140'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Agregar columnas source_handle y target_handle 
    a la tabla device_connections para guardar las posiciones 
    de los handles de React Flow
    """
    # Agregar source_handle
    op.add_column(
        'device_connections',
        sa.Column('source_handle', sa.String(length=20), nullable=True)
    )
    
    # Agregar target_handle
    op.add_column(
        'device_connections',
        sa.Column('target_handle', sa.String(length=20), nullable=True)
    )
    
    print("✅ Columnas source_handle y target_handle agregadas exitosamente")


def downgrade() -> None:
    """
    Revertir los cambios: eliminar las columnas agregadas
    """
    # Eliminar en orden inverso
    op.drop_column('device_connections', 'target_handle')
    op.drop_column('device_connections', 'source_handle')
    
    print("✅ Columnas source_handle y target_handle eliminadas")