from sqlmodel import Session

from ..config import get_settings
from ..models import Membership, Organization, User
from .engine import engine


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
