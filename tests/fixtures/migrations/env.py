"""Programmatic-only evidence chain, isolated from application revision history."""

from alembic import context

connection = context.config.attributes["connection"]
context.configure(
    connection=connection,
    version_table="migration_evidence_version",
    render_as_batch=connection.dialect.name == "sqlite",
)
with context.begin_transaction():
    context.run_migrations()
