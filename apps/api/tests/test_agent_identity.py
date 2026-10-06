from app.agent_identity import AgentIdentityError, AgentIdentityService
from app.auth import Principal
from app.database import create_db_and_tables, engine
from app.models import MarketplaceEntry
from sqlmodel import Session
import pytest


DEFINITION = {
    "name": "Developer Agent",
    "version": "1.0.0",
    "description": "Implements changes",
    "status": "promoted",
    "capabilities": ["repository.read", "repository.write"],
}


def test_agentmesh_identity_signs_and_verifies_marketplace_entry(tmp_path):
    create_db_and_tables()
    service = AgentIdentityService(tmp_path)
    principal = Principal("sponsor-1", "org-1", "admin",
                          "sponsor@example.test")

    with Session(engine) as session:
        identity = service.enroll(session, "developer", DEFINITION, principal)
        verified = service.verify(session, "developer", "org-1", DEFINITION)
        entries = service.list_entries(session, "org-1")

    assert identity.did.startswith("did:mesh:")
    assert verified.did == identity.did
    assert entries[0]["verified"] is True
    assert entries[0]["author"] == identity.did


def test_marketplace_tampering_fails_closed(tmp_path):
    create_db_and_tables()
    service = AgentIdentityService(tmp_path)
    principal = Principal("sponsor-2", "org-2", "admin",
                          "sponsor@example.test")

    with Session(engine) as session:
        service.enroll(session, "developer", DEFINITION, principal)
        entry = session.get(MarketplaceEntry, "org-2:developer")
        entry.manifest = {**entry.manifest,
                          "capabilities": ["production.deploy"]}
        session.add(entry)
        session.commit()
        with pytest.raises(AgentIdentityError, match="signature verification"):
            service.verify(session, "developer", "org-2", DEFINITION)
