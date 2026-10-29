"""Fail after DDL to demonstrate MySQL's partial migration state."""

import sqlalchemy as sa
from alembic import op

revision = "evidence_failure"
down_revision = "evidence_base"


def upgrade() -> None:
    op.create_table(
        "migration_evidence_partial", sa.Column("id", sa.Integer(), primary_key=True)
    )
    raise RuntimeError("Deliberate migration failure after DDL")


def downgrade() -> None:
    op.drop_table("migration_evidence_partial")
