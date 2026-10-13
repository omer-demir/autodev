from sqlmodel import create_engine

from ..config import get_settings


database_url = get_settings().database_url
engine = create_engine(
    database_url,
    connect_args={"check_same_thread": False} if database_url.startswith(
        "sqlite") else {},
    pool_pre_ping=not database_url.startswith("sqlite"),
)
