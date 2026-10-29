"""Add, backfill, constrain, and index a test-only column."""

import sqlalchemy as sa
from alembic import op

revision = "evidence_backfill"
down_revision = "evidence_base"


def upgrade() -> None:
    op.add_column("items", sa.Column("evidence_label", sa.String(120), nullable=True))
    op.execute(sa.text("UPDATE items SET evidence_label = name"))
    with op.batch_alter_table("items") as batch:
        batch.alter_column(
            "evidence_label",
            existing_type=sa.String(120),
            nullable=False,
            server_default="new",
        )
        batch.create_index("ix_items_evidence_label", ["evidence_label"])


def downgrade() -> None:
    with op.batch_alter_table("items") as batch:
        batch.drop_index("ix_items_evidence_label")
        batch.drop_column("evidence_label")
