"""Store durable mutation responses atomically with their domain changes."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = '0003_request_idempotency'
down_revision = '0002_item_versions'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'request_idempotency',
        sa.Column('scope_hash', sa.String(64), primary_key=True),
        sa.Column('namespace', sa.String(256), nullable=False),
        sa.Column('caller_scope', sa.String(128), nullable=False),
        sa.Column('operation', sa.String(128), nullable=False),
        sa.Column('route', sa.String(512), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('state', sa.String(16), nullable=False),
        sa.Column('response_status', mysql.SMALLINT(unsigned=True), nullable=True),
        sa.Column('response_body', mysql.MEDIUMBLOB(), nullable=True),
        sa.Column('completed_at', mysql.DATETIME(fsp=3), nullable=True),
        sa.Column('expires_at', mysql.DATETIME(fsp=3), nullable=True),
    )
    op.create_index(
        'ix_request_idempotency_expiry', 'request_idempotency', ['state', 'expires_at']
    )


def downgrade() -> None:
    op.drop_table('request_idempotency')
