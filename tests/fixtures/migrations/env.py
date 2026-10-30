"""Programmatic-only evidence chain, isolated from application revision history."""

from alembic import context

connection = context.config.attributes["connection"]

context.configure(
    connection=connection,
    version_table="migration_evidence_version",
)
with context.begin_transaction():
    context.run_migrations()
