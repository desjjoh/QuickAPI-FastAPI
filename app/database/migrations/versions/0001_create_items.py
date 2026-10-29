"""Create the existing item schema without changing its public contract."""

import sqlalchemy as sa
from alembic import op

revision = "0001_create_items"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "items",
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("id", sa.String(16), nullable=False),
        sa.Column(
            "createdAt",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updatedAt",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_items_name", "items", ["name"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_items_name", table_name="items")
    op.drop_table("items")
