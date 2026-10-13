import base64
import hashlib
import secrets
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import jwt
from cryptography.fernet import Fernet
from sqlmodel import Session, select

from ..config import get_settings
from ..database import engine
from ..models import (
    Connector,
    ConnectorCredential,
    GitHubAppConfiguration,
    GitHubInstallation,
    OAuthState,
)
from .identity import GitHubIdentity


class GitHubCredentialStore:
    """Tenant-scoped GitHub credentials with durable OAuth state."""

    def __init__(self) -> None:
        # Kept only for deployment-token and existing local-test compatibility.
        self._identity: GitHubIdentity | None = None
        self._states: dict[str, float] = {}

    @property
    def token(self) -> str | None:
        return self._identity.token if self._identity else get_settings().github_token

    @property
    def login(self) -> str | None:
        return self._identity.login if self._identity else None

    @property
    def method(self) -> str | None:
        if self._identity:
            return "oauth"
        if get_settings().github_token:
            return "environment"
        return None

    @property
    def app_token_configured(self) -> bool:
        settings = get_settings()
        return bool(
            settings.github_app_id
            and settings.github_app_slug
            and (settings.github_app_private_key or settings.github_app_private_key_file)
        )

    @property
    def app_install_configured(self) -> bool:
        settings = get_settings()
        return bool(
            self.app_token_configured
            and settings.github_app_client_id
            and settings.github_app_client_secret
        )

    @staticmethod
    def _credential_id(organization_id: str, owner_id: str | None) -> str:
        owner = owner_id or "organization"
        digest = hashlib.sha256(
            f"github:{organization_id}:{owner}".encode()
        ).hexdigest()[:32]
        return f"CRED-{digest}"

    @staticmethod
    def _fernet() -> Fernet:
        digest = hashlib.sha256(
            get_settings().credential_master_key.encode()
        ).digest()
        return Fernet(base64.urlsafe_b64encode(digest))

    @staticmethod
    def _secret_name(credential_id: str) -> str:
        return credential_id.lower()

    @staticmethod
    def _installation_record_id(
        organization_id: str, owner_id: str | None, installation_id: int
    ) -> str:
        owner = owner_id or "organization"
        digest = hashlib.sha256(
            f"github-app:{organization_id}:{owner}:{installation_id}".encode()
        ).hexdigest()[:32]
        return f"GHI-{digest}"

    def _app_configuration(
        self, connector_id: str | None = None
    ) -> GitHubAppConfiguration | None:
        if not connector_id:
            return None
        with Session(engine) as session:
            return session.get(GitHubAppConfiguration, connector_id)

    def _private_key(self, connector_id: str | None = None) -> str:
        configuration = self._app_configuration(connector_id)
        if configuration:
            return self._fernet().decrypt(
                configuration.encrypted_private_key.encode()
            ).decode()
        settings = get_settings()
        if settings.github_app_private_key:
            return settings.github_app_private_key.replace("\\n", "\n")
        if settings.github_app_private_key_file:
            return Path(settings.github_app_private_key_file).expanduser().read_text(
                encoding="utf-8"
            )
        raise RuntimeError("GitHub App private key is not configured")

    def app_jwt(self, connector_id: str | None = None) -> str:
        settings = get_settings()
        configuration = self._app_configuration(connector_id)
        app_id = configuration.app_id if configuration else settings.github_app_id
        if not app_id:
            raise RuntimeError("GitHub App ID is not configured")
        now = int(time.time())
        return jwt.encode(
            {"iat": now - 60, "exp": now + 9 * 60, "iss": app_id},
            self._private_key(connector_id),
            algorithm="RS256",
        )

    def create_manifest_connector(
        self,
        organization_id: str,
        user_id: str,
        name: str,
    ) -> Connector:
        connector = Connector(
            id=f"CON-{secrets.token_hex(12)}",
            organization_id=organization_id,
            created_by=user_id,
            provider="github",
            name=name,
            auth_method="github_app",
            status="REGISTERING",
        )
        with Session(engine) as session:
            session.add(connector)
            session.commit()
            session.refresh(connector)
            return connector

    def complete_manifest(
        self,
        connector_id: str,
        organization_id: str,
        manifest: dict[str, Any],
    ) -> Connector:
        required = ("id", "slug", "client_id", "client_secret", "pem")
        if any(not manifest.get(item) for item in required):
            raise RuntimeError(
                "GitHub returned an incomplete App configuration")
        with Session(engine) as session:
            connector = session.get(Connector, connector_id)
            if not connector or connector.organization_id != organization_id:
                raise RuntimeError("GitHub connector is unavailable")
            configuration = GitHubAppConfiguration(
                connector_id=connector.id,
                organization_id=organization_id,
                app_id=str(manifest["id"]),
                app_slug=str(manifest["slug"]),
                client_id=str(manifest["client_id"]),
                encrypted_client_secret=self._fernet().encrypt(
                    str(manifest["client_secret"]).encode()
                ).decode(),
                encrypted_private_key=self._fernet().encrypt(
                    str(manifest["pem"]).encode()
                ).decode(),
                encrypted_webhook_secret=(
                    self._fernet().encrypt(
                        str(manifest["webhook_secret"]).encode()
                    ).decode()
                    if manifest.get("webhook_secret")
                    else None
                ),
            )
            connector.status = "PENDING_INSTALLATION"
            connector.metadata_ = {
                "app_id": configuration.app_id,
                "app_slug": configuration.app_slug,
            }
            connector.updated_at = datetime.now(UTC)
            session.add(configuration)
            session.add(connector)
            session.commit()
            session.refresh(connector)
            return connector

    def connectors(self, organization_id: str) -> list[Connector]:
        with Session(engine) as session:
            return list(session.exec(
                select(Connector).where(
                    Connector.organization_id == organization_id
                ).order_by(Connector.created_at)
            ).all())

    def get_connector(
        self, connector_id: str, organization_id: str
    ) -> Connector | None:
        with Session(engine) as session:
            connector = session.get(Connector, connector_id)
            if connector and connector.organization_id == organization_id:
                return connector
        return None

    def connector_app(self, connector_id: str, organization_id: str) -> dict[str, str]:
        connector = self.get_connector(connector_id, organization_id)
        configuration = self._app_configuration(connector_id)
        if not connector or not configuration:
            raise RuntimeError("GitHub App registration is incomplete")
        return {
            "app_id": configuration.app_id,
            "app_slug": configuration.app_slug,
            "client_id": configuration.client_id,
            "client_secret": self._fernet().decrypt(
                configuration.encrypted_client_secret.encode()
            ).decode(),
        }

    def set_connector_status(
        self, connector_id: str, organization_id: str, status: str
    ) -> None:
        with Session(engine) as session:
            connector = session.get(Connector, connector_id)
            if connector and connector.organization_id == organization_id:
                connector.status = status
                connector.updated_at = datetime.now(UTC)
                session.add(connector)
                session.commit()

    def delete_connector(self, connector_id: str, organization_id: str) -> bool:
        with Session(engine) as session:
            connector = session.get(Connector, connector_id)
            if not connector or connector.organization_id != organization_id:
                return False
            for installation in session.exec(
                select(GitHubInstallation).where(
                    GitHubInstallation.connector_id == connector_id
                )
            ).all():
                session.delete(installation)
            configuration = session.get(GitHubAppConfiguration, connector_id)
            if configuration:
                session.delete(configuration)
            session.delete(connector)
            session.commit()
            return True

    def create_state(
        self,
        organization_id: str | None = None,
        user_id: str | None = None,
        context: dict[str, Any] | None = None,
        expires_in_seconds: int = 600,
    ) -> str:
        raw = secrets.token_urlsafe(32)
        if organization_id is None or user_id is None:
            self._states[raw] = time.monotonic() + 600
            return raw
        state_id = hashlib.sha256(raw.encode()).hexdigest()
        with Session(engine) as session:
            session.add(OAuthState(
                id=state_id,
                organization_id=organization_id,
                user_id=user_id,
                expires_at=datetime.now(
                    UTC) + timedelta(seconds=expires_in_seconds),
                context=context or {},
            ))
            session.commit()
        return raw

    def consume_state(
        self,
        raw: str,
        organization_id: str | None = None,
        user_id: str | None = None,
    ) -> bool:
        if organization_id is None or user_id is None:
            return self._states.pop(raw, 0) > time.monotonic()
        return self.consume_state_context(raw, organization_id, user_id) is not None

    def consume_state_context(
        self,
        raw: str,
        organization_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        state_id = hashlib.sha256(raw.encode()).hexdigest()
        with Session(engine) as session:
            state = session.get(OAuthState, state_id)
            expires_at = state.expires_at if state else None
            if expires_at and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            valid = bool(
                state
                and state.organization_id == organization_id
                and state.user_id == user_id
                and expires_at
                and expires_at > datetime.now(UTC)
            )
            if state:
                session.delete(state)
                session.commit()
            return dict(state.context) if valid and state else None

    def connect(
        self,
        organization_id: str,
        owner_id: str,
        login: str,
        token: str,
    ) -> None:
        settings = get_settings()
        credential_id = self._credential_id(organization_id, owner_id)
        encrypted_secret = None
        secret_reference = None
        if settings.credential_provider == "azure_key_vault":
            if not settings.azure_key_vault_url:
                raise RuntimeError(
                    "Azure Key Vault credentials require WORKBENCH_AZURE_KEY_VAULT_URL"
                )
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient

            client = SecretClient(
                vault_url=settings.azure_key_vault_url,
                credential=DefaultAzureCredential(),
            )
            secret = client.set_secret(self._secret_name(credential_id), token)
            secret_reference = secret.id
        elif settings.credential_provider == "encrypted_database":
            encrypted_secret = self._fernet().encrypt(token.encode()).decode()
        else:
            raise RuntimeError(
                f"Unknown credential provider: {settings.credential_provider}"
            )
        with Session(engine) as session:
            credential = session.get(ConnectorCredential, credential_id)
            if not credential:
                credential = ConnectorCredential(
                    id=credential_id,
                    organization_id=organization_id,
                    owner_id=owner_id,
                    provider="github",
                )
            credential.login = login
            credential.encrypted_secret = encrypted_secret
            credential.secret_reference = secret_reference
            credential.updated_at = datetime.now(UTC)
            session.add(credential)
            session.commit()

    def connect_installation(
        self,
        organization_id: str,
        owner_id: str,
        installation: dict[str, Any],
        connector_id: str | None = None,
    ) -> GitHubInstallation:
        settings = get_settings()
        configuration = self._app_configuration(connector_id)
        installation_id = int(installation["id"])
        account = installation.get("account") or {}
        account_login = str(account.get("login") or "")
        if not account_login:
            raise RuntimeError("GitHub installation account is unavailable")
        record_id = self._installation_record_id(
            organization_id, owner_id, installation_id
        )
        with Session(engine) as session:
            record = session.get(GitHubInstallation, record_id)
            if not record:
                record = GitHubInstallation(
                    id=record_id,
                    connector_id=connector_id,
                    organization_id=organization_id,
                    owner_id=owner_id,
                    installation_id=installation_id,
                    app_id=str(
                        installation.get("app_id")
                        or (configuration.app_id if configuration else settings.github_app_id)
                    ),
                    app_slug=str(
                        installation.get("app_slug")
                        or (configuration.app_slug if configuration else settings.github_app_slug)
                    ),
                    account_login=account_login,
                )
            record.account_type = str(account.get("type") or "User")
            record.bot_id = (
                int(installation["bot_id"])
                if installation.get("bot_id") is not None
                else record.bot_id
            )
            record.repository_selection = str(
                installation.get("repository_selection") or "selected"
            )
            record.permissions = dict(installation.get("permissions") or {})
            record.connector_id = connector_id or record.connector_id
            record.updated_at = datetime.now(UTC)
            session.add(record)
            if connector_id:
                connector = session.get(Connector, connector_id)
                if connector:
                    connector.account_login = account_login
                    connector.status = "ACTIVE"
                    connector.updated_at = datetime.now(UTC)
                    session.add(connector)
            session.commit()
            session.refresh(record)
            return record

    def installations(
        self,
        organization_id: str,
        owner_id: str | None = None,
        connector_id: str | None = None,
    ) -> list[GitHubInstallation]:
        with Session(engine) as session:
            statement = select(GitHubInstallation).where(
                GitHubInstallation.organization_id == organization_id,
            )
            if connector_id:
                statement = statement.where(
                    GitHubInstallation.connector_id == connector_id
                )
            else:
                statement = statement.where(
                    GitHubInstallation.owner_id == owner_id)
            return list(session.exec(statement).all())

    def get_installation(
        self,
        organization_id: str,
        owner_id: str | None,
        account_login: str,
        connector_id: str | None = None,
    ) -> GitHubInstallation | None:
        return next(
            (
                item
                for item in self.installations(
                    organization_id, owner_id, connector_id
                )
                if item.account_login.casefold() == account_login.casefold()
            ),
            None,
        )

    def commit_identity(
        self,
        organization_id: str,
        owner_id: str | None,
        account_login: str,
        connector_id: str | None = None,
    ) -> tuple[str, str] | None:
        installation = self.get_installation(
            organization_id, owner_id, account_login, connector_id
        )
        if not installation:
            return None
        bot_name = f"{installation.app_slug}[bot]"
        bot_email = (
            f"{installation.bot_id}+{bot_name}@users.noreply.github.com"
            if installation.bot_id is not None
            else f"{bot_name}@users.noreply.github.com"
        )
        return bot_name, bot_email

    async def installation_identity(
        self,
        organization_id: str,
        owner_id: str | None,
        account_login: str,
        repository: str | None = None,
        *,
        write: bool = False,
        connector_id: str | None = None,
    ) -> GitHubIdentity | None:
        installation = self.get_installation(
            organization_id, owner_id, account_login, connector_id
        )
        if not installation:
            return None
        payload: dict[str, Any] = {
            "permissions": {
                "contents": "write" if write else "read",
                "pull_requests": "write" if write else "read",
            }
        }
        for permission in ("actions", "checks"):
            if installation.permissions.get(permission) in {"read", "write"}:
                payload["permissions"][permission] = "read"
        if write and installation.permissions.get("workflows") == "write":
            payload["permissions"]["workflows"] = "write"
        if repository:
            payload["repositories"] = [repository]
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://api.github.com/app/installations/"
                f"{installation.installation_id}/access_tokens",
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {self.app_jwt(connector_id)}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                json=payload,
            )
            response.raise_for_status()
        token = response.json().get("token")
        if not token:
            raise RuntimeError("GitHub did not issue an installation token")
        return GitHubIdentity(
            login=f"{installation.app_slug}[bot]",
            token=str(token),
            method="github_app",
            app_slug=installation.app_slug,
            installation_id=installation.installation_id,
        )

    async def identity_for_repository(
        self,
        organization_id: str,
        owner_id: str | None,
        account_login: str,
        repository: str,
        *,
        write: bool = False,
        connector_id: str | None = None,
    ) -> GitHubIdentity | None:
        identity = await self.installation_identity(
            organization_id,
            owner_id,
            account_login,
            repository,
            write=write,
            connector_id=connector_id,
        )
        if identity:
            return identity
        token = self.get_token(organization_id, owner_id)
        if not token:
            return None
        status = self.status(organization_id, owner_id)
        return GitHubIdentity(
            login=str(status.get("login") or account_login),
            token=token,
            method=str(status.get("method") or "environment"),
        )

    def get_token(self, organization_id: str, owner_id: str | None = None) -> str | None:
        if self._identity:
            return self._identity.token
        credential_id = self._credential_id(organization_id, owner_id)
        with Session(engine) as session:
            credential = session.get(ConnectorCredential, credential_id)
        if not credential:
            return self.token
        if credential.encrypted_secret:
            return self._fernet().decrypt(credential.encrypted_secret.encode()).decode()
        if credential.secret_reference:
            settings = get_settings()
            if not settings.azure_key_vault_url:
                raise RuntimeError("Azure Key Vault URL is not configured")
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient

            client = SecretClient(
                vault_url=settings.azure_key_vault_url,
                credential=DefaultAzureCredential(),
            )
            return client.get_secret(self._secret_name(credential.id)).value
        return None

    def status(self, organization_id: str, owner_id: str | None = None) -> dict:
        installations = self.installations(organization_id, owner_id)
        if installations:
            return {
                "authenticated": True,
                "login": installations[0].account_login,
                "method": "github_app",
                "app_slug": installations[0].app_slug,
                "installations": [
                    {
                        "id": item.installation_id,
                        "account": item.account_login,
                        "repository_selection": item.repository_selection,
                    }
                    for item in installations
                ],
            }
        credential_id = self._credential_id(organization_id, owner_id)
        with Session(engine) as session:
            credential = session.get(ConnectorCredential, credential_id)
        if credential:
            return {
                "authenticated": True,
                "login": credential.login,
                "method": credential.method,
            }
        return {
            "authenticated": bool(self.token),
            "login": self.login,
            "method": self.method,
        }

    def disconnect(self, organization_id: str, owner_id: str | None = None) -> None:
        credential_id = self._credential_id(organization_id, owner_id)
        with Session(engine) as session:
            credential = session.get(ConnectorCredential, credential_id)
            if credential and credential.secret_reference and get_settings().azure_key_vault_url:
                from azure.identity import DefaultAzureCredential
                from azure.keyvault.secrets import SecretClient

                client = SecretClient(
                    vault_url=get_settings().azure_key_vault_url,
                    credential=DefaultAzureCredential(),
                )
                client.begin_delete_secret(
                    self._secret_name(credential.id)).wait()
            if credential:
                session.delete(credential)
            for installation in session.exec(select(GitHubInstallation).where(
                GitHubInstallation.organization_id == organization_id,
                GitHubInstallation.owner_id == owner_id,
            )).all():
                session.delete(installation)
            session.commit()
