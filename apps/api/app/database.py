from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings
from .models import Membership, Organization, User


engine = create_engine(get_settings().database_url,
                       connect_args={"check_same_thread": False})


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)
    migrations = {
        "project": {
            "source_type": "TEXT NOT NULL DEFAULT 'local'",
            "repository_url": "TEXT",
            "default_branch": "TEXT",
            "organization_id": "TEXT NOT NULL DEFAULT 'local'",
            "created_by": "TEXT",
        },
        "task": {
            "model_name": "TEXT",
            "mode": "TEXT NOT NULL DEFAULT 'change'",
            "verbose_logging": "BOOLEAN NOT NULL DEFAULT 0",
            "organization_id": "TEXT NOT NULL DEFAULT 'local'",
            "created_by": "TEXT",
        },
        "approval": {
            "organization_id": "TEXT NOT NULL DEFAULT 'local'",
            "requester_id": "TEXT",
            "approver_id": "TEXT",
        },
        "sandbox": {"container_id": "TEXT", "host_workspace": "TEXT"},
        "evaluationrun": {
            "dataset_id": "TEXT",
            "metrics": "JSON NOT NULL DEFAULT '{}'",
            "comparison": "JSON NOT NULL DEFAULT '{}'",
            "provenance": "JSON NOT NULL DEFAULT '{}'",
            "completed_at": "DATETIME",
            "organization_id": "TEXT NOT NULL DEFAULT 'local'",
            "created_by": "TEXT",
        },
        "evaluationdataset": {
            "organization_id": "TEXT NOT NULL DEFAULT 'local'",
            "created_by": "TEXT",
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
                        text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))


def ensure_local_identity() -> None:
    settings = get_settings()
    if settings.auth_mode != "local":
        return
    with Session(engine) as session:
        organization = session.get(
            Organization, settings.local_organization_id)
        if organization is None:
            session.add(Organization(
                id=settings.local_organization_id, name="Local Workbench"
            ))
        user = session.get(User, settings.local_user_id)
        if user is None:
            session.add(User(
                id=settings.local_user_id,
                display_name="Local Administrator",
                issuer="local",
            ))
        membership = session.get(
            Membership, (settings.local_user_id,
                         settings.local_organization_id)
        )
        if membership is None:
            session.add(Membership(
                user_id=settings.local_user_id,
                organization_id=settings.local_organization_id,
                role="admin",
            ))
        session.commit()


def get_session():
    with Session(engine) as session:
        yield session
