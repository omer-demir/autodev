import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlmodel import Session

from ..config import Settings
from ..models import BrowserSession
from .principal import Principal


def session_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_browser_session(
    session: Session, principal: Principal, settings: Settings
) -> tuple[str, BrowserSession]:
    token = secrets.token_urlsafe(48)
    record = BrowserSession(
        id=session_digest(token),
        user_id=principal.user_id,
        organization_id=principal.organization_id,
        expires_at=datetime.now(
            UTC) + timedelta(hours=settings.session_ttl_hours),
    )
    session.add(record)
    session.commit()
    return token, record


def delete_browser_session(session: Session, token: str | None) -> None:
    if not token:
        return
    record = session.get(BrowserSession, session_digest(token))
    if record:
        session.delete(record)
        session.commit()
