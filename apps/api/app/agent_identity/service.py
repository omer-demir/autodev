import base64
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentmesh import AgentIdentity
from agentmesh.marketplace import PluginManifest, PluginSigner, PluginType, verify_signature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from sqlmodel import Session, select

from ..auth import Principal
from ..config import get_settings
from ..models import AgentIdentityRecord, MarketplaceEntry
from .errors import AgentIdentityError


class AgentIdentityService:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(get_settings().agent_identity_dir).resolve()

    def enroll(
        self,
        session: Session,
        agent_id: str,
        definition: dict[str, Any],
        principal: Principal,
    ) -> AgentIdentityRecord:
        existing = self._record(session, agent_id, principal.organization_id)
        if existing is not None:
            return self._refresh(session, existing, definition)

        sponsor_email = principal.email or f"{principal.user_id}@local.invalid"
        identity = AgentIdentity.create(
            name=str(definition["name"]),
            sponsor=sponsor_email,
            capabilities=[str(item)
                          for item in definition.get("capabilities", [])],
            organization=principal.organization_id,
            description=str(definition.get("description") or ""),
        )
        identity.organization_id = principal.organization_id
        identity.sponsor_verified = True
        private_key = identity._private_key
        if private_key is None:
            raise AgentIdentityError("AgentMesh did not create a signing key")
        self._write_private_key(
            principal.organization_id, agent_id, private_key)

        record = AgentIdentityRecord(
            did=str(identity.did),
            agent_id=agent_id,
            organization_id=principal.organization_id,
            public_key=identity.public_key,
            verification_key_id=identity.verification_key_id,
            sponsor_id=principal.user_id,
            sponsor_email=sponsor_email,
            sponsor_verified=True,
            capabilities=identity.capabilities,
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        self._publish(session, record, definition, private_key)
        return record

    def verify(
        self,
        session: Session,
        agent_id: str,
        organization_id: str,
        definition: dict[str, Any],
    ) -> AgentIdentityRecord:
        record = self._record(session, agent_id, organization_id)
        if record is None:
            raise AgentIdentityError(
                f"Agent {agent_id} has no AgentMesh identity")
        if record.status != "active":
            raise AgentIdentityError(f"Agent identity is {record.status}")
        expected = sorted(str(item)
                          for item in definition.get("capabilities", []))
        if sorted(record.capabilities) != expected:
            raise AgentIdentityError(
                "Agent capabilities differ from its signed identity")
        entry = session.get(MarketplaceEntry, self._entry_id(
            organization_id, agent_id))
        if entry is None or entry.agent_did != record.did:
            raise AgentIdentityError("Agent has no matching Marketplace entry")
        manifest = PluginManifest.model_validate(entry.manifest)
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(
            base64.b64decode(record.public_key)
        )
        try:
            verified = verify_signature(manifest, public_key)
        except Exception as exc:
            raise AgentIdentityError(
                "Marketplace signature verification failed") from exc
        if not verified:
            raise AgentIdentityError(
                "Marketplace signature verification failed")
        return record

    def list_entries(
        self, session: Session, organization_id: str
    ) -> list[dict[str, Any]]:
        entries = session.exec(
            select(MarketplaceEntry)
            .where(MarketplaceEntry.organization_id == organization_id)
            .order_by(MarketplaceEntry.agent_id)
        ).all()
        return [
            {
                **entry.manifest,
                "agent_id": entry.agent_id,
                "agent_did": entry.agent_did,
                "verified": self._entry_verified(session, entry),
            }
            for entry in entries
        ]

    def revoke(
        self, session: Session, agent_id: str, organization_id: str
    ) -> AgentIdentityRecord:
        record = self._record(session, agent_id, organization_id)
        if record is None:
            raise AgentIdentityError(
                f"Agent {agent_id} has no AgentMesh identity")
        record.status = "revoked"
        record.updated_at = datetime.now(UTC)
        session.add(record)
        session.commit()
        session.refresh(record)
        return record

    def _refresh(
        self, session: Session, record: AgentIdentityRecord, definition: dict[str, Any]
    ) -> AgentIdentityRecord:
        capabilities = [str(item)
                        for item in definition.get("capabilities", [])]
        private_key = self._read_private_key(
            record.organization_id, record.agent_id)
        if record.capabilities != capabilities:
            record.capabilities = capabilities
            record.updated_at = datetime.now(UTC)
            session.add(record)
            session.commit()
            session.refresh(record)
        self._publish(session, record, definition, private_key)
        return record

    def _publish(
        self,
        session: Session,
        record: AgentIdentityRecord,
        definition: dict[str, Any],
        private_key: ed25519.Ed25519PrivateKey,
    ) -> None:
        unsigned = PluginManifest(
            name=record.agent_id,
            version=str(definition["version"]),
            description=str(definition.get("description")
                            or definition["name"]),
            author=record.did,
            plugin_type=PluginType.AGENT,
            capabilities=record.capabilities,
            min_agentmesh_version="5.0.0",
        )
        manifest = PluginSigner(private_key).sign(unsigned)
        if not verify_signature(manifest, private_key.public_key()):
            raise AgentIdentityError(
                "Could not verify signed Marketplace manifest")
        entry_id = self._entry_id(record.organization_id, record.agent_id)
        entry = session.get(MarketplaceEntry, entry_id) or MarketplaceEntry(
            id=entry_id,
            agent_id=record.agent_id,
            organization_id=record.organization_id,
            agent_did=record.did,
        )
        entry.agent_did = record.did
        entry.manifest = manifest.model_dump(mode="json")
        entry.verified = True
        entry.updated_at = datetime.now(UTC)
        session.add(entry)
        session.commit()

    def _entry_verified(self, session: Session, entry: MarketplaceEntry) -> bool:
        record = session.get(AgentIdentityRecord, entry.agent_did)
        if record is None or record.status != "active":
            return False
        try:
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(
                base64.b64decode(record.public_key)
            )
            return verify_signature(PluginManifest.model_validate(entry.manifest), public_key)
        except Exception:
            return False

    def _record(
        self, session: Session, agent_id: str, organization_id: str
    ) -> AgentIdentityRecord | None:
        return session.exec(
            select(AgentIdentityRecord).where(
                AgentIdentityRecord.agent_id == agent_id,
                AgentIdentityRecord.organization_id == organization_id,
            )
        ).first()

    def _key_path(self, organization_id: str, agent_id: str) -> Path:
        safe_org = organization_id.replace("/", "_")
        safe_agent = agent_id.replace("/", "_")
        return self.root / safe_org / f"{safe_agent}.pem"

    def _write_private_key(
        self, organization_id: str, agent_id: str, key: ed25519.Ed25519PrivateKey
    ) -> None:
        path = self._key_path(organization_id, agent_id)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_bytes(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        os.chmod(path, 0o600)

    def _read_private_key(
        self, organization_id: str, agent_id: str
    ) -> ed25519.Ed25519PrivateKey:
        path = self._key_path(organization_id, agent_id)
        if not path.exists():
            raise AgentIdentityError("Agent identity key is unavailable")
        key = serialization.load_pem_private_key(
            path.read_bytes(), password=None)
        if not isinstance(key, ed25519.Ed25519PrivateKey):
            raise AgentIdentityError("Agent identity key is not Ed25519")
        return key

    @staticmethod
    def _entry_id(organization_id: str, agent_id: str) -> str:
        return f"{organization_id}:{agent_id}"
