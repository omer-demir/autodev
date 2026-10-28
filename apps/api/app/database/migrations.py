from sqlalchemy import inspect, text
from sqlmodel import SQLModel

from .engine import engine


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)
    migrations = {
        "project": {
            "workspace_only": "BOOLEAN NOT NULL DEFAULT FALSE",
            "source_type": "TEXT NOT NULL DEFAULT 'local'",
            "repository_url": "TEXT",
            "default_branch": "TEXT",
            "connector_id": "TEXT",
            "transport": "TEXT NOT NULL DEFAULT 'https'",
            "organization_id": "TEXT NOT NULL DEFAULT 'local'",
            "created_by": "TEXT",
        },
        "task": {
            "model_name": "TEXT",
            "selected_agents": "JSON NOT NULL DEFAULT '[]'",
            "additional_skills": "JSON NOT NULL DEFAULT '[]'",
            "is_chat": "BOOLEAN NOT NULL DEFAULT FALSE",
            "approval_strategy": "TEXT NOT NULL DEFAULT 'agent_policy'",
            "mode": "TEXT NOT NULL DEFAULT 'change'",
            "verbose_logging": "BOOLEAN NOT NULL DEFAULT FALSE",
            "workflow_id": "TEXT NOT NULL DEFAULT 'sdlc'",
            "organization_id": "TEXT NOT NULL DEFAULT 'local'",
            "created_by": "TEXT",
        },
        "chatturn": {
            "model_provider": "TEXT",
            "model_name": "TEXT",
            "input_tokens": "INTEGER",
            "output_tokens": "INTEGER",
            "estimated_cost_usd": "REAL",
            "cost_note": "TEXT",
        },
        "approval": {
            "organization_id": "TEXT NOT NULL DEFAULT 'local'",
            "requester_id": "TEXT",
            "approver_id": "TEXT",
        },
        "sandbox": {
            "container_id": "TEXT",
            "host_workspace": "TEXT",
            "workspace_revision_id": "TEXT",
        },
        "evaluationrun": {
            "dataset_id": "TEXT",
            "metrics": "JSON NOT NULL DEFAULT '{}'",
            "comparison": "JSON NOT NULL DEFAULT '{}'",
            "provenance": "JSON NOT NULL DEFAULT '{}'",
            "completed_at": "TIMESTAMP",
            "organization_id": "TEXT NOT NULL DEFAULT 'local'",
            "created_by": "TEXT",
        },
        "evaluationdataset": {
            "organization_id": "TEXT NOT NULL DEFAULT 'local'",
            "created_by": "TEXT",
            "adapter_specs": "JSON NOT NULL DEFAULT '{}'",
            "dataset_name": "TEXT NOT NULL DEFAULT ''",
            "version": "INTEGER NOT NULL DEFAULT 1",
        },
        "executionjob": {
            "deduplication_key": "TEXT",
            "result": "JSON",
        },
        "githubinstallation": {
            "connector_id": "TEXT",
            "bot_id": "BIGINT",
        },
        "oauthstate": {
            "context": "JSON NOT NULL DEFAULT '{}'",
        },
    }
    with engine.begin() as connection:
        inspector = inspect(connection)
        for table, columns in migrations.items():
            existing = {column["name"]
                        for column in inspector.get_columns(table)}
            for name, definition in columns.items():
                if name not in existing:
                    connection.execute(
                        text(
                            f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
                    )
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_executionjob_deduplication_key "
            "ON executionjob (deduplication_key)"
        ))
        connection.execute(text(
            "UPDATE evaluationdataset SET dataset_name = agent_id || '-' || suite_id "
            "WHERE dataset_name = ''"
        ))
