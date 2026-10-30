"""Add item revision preconditions, initializing existing rows at version one."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = '0002_item_versions'
down_revision = '0001_create_items'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'items',
        sa.Column(
            'version',
            mysql.INTEGER(unsigned=True),
            server_default=sa.text('1'),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column('items', 'version')
