from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app import registry
from app.auth import OIDCAuthenticator, Principal, current_principal
from app.config import Settings
from app.main import app


def test_role_permissions_are_default_deny():
    developer = Principal("dev", "org", "developer")
    reviewer = Principal("reviewer", "org", "reviewer")
    admin = Principal("admin", "org", "admin")
    unknown = Principal("unknown", "org", "custom")

    assert developer.can("task.create")
    assert developer.can("project.delete")
    assert not developer.can("approval.decide")
    assert not reviewer.can("agent.evaluation_bypass")
    assert admin.can("agent.evaluation_bypass")
    assert not unknown.can("read")


def test_evaluation_bypass_endpoint_requires_admin():
    app.dependency_overrides[current_principal] = lambda: Principal(
        "reviewer", "local", "reviewer"
    )
    try:
        with TestClient(app) as client:
            response = client.put(
                "/api/agents/developer/evaluation-requirement",
                json={
                    "evaluation_required": False,
                    "reason": "Temporary trial",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_admin_can_enable_attributed_evaluation_bypass(tmp_path, monkeypatch):
    agent_id = f"candidate-{uuid4().hex}"
    raw = f"""name: Candidate
version: 1.0.0
status: draft
identity:
  id: did:local:{agent_id}
capabilities: [repository.read]
"""
    with TestClient(app) as client:
        monkeypatch.setitem(registry.REGISTRIES, "agents", tmp_path)
        registry.save_definition("agents", agent_id, raw)
        response = client.put(
            f"/api/agents/{agent_id}/evaluation-requirement",
            json={
                "evaluation_required": False,
                "reason": "Evaluate after a short sandboxed trial",
            },
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "draft"
    assert data["evaluation_required"] is False
    assert data["evaluation_override"]["approved_by"] == "local-admin"
    assert data["evaluation_override"]["reason"] == (
        "Evaluate after a short sandboxed trial"
    )


def test_oidc_authenticator_validates_signature_issuer_and_audience(monkeypatch):
    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    now = datetime.now(UTC)
    settings = Settings(
        auth_mode="oidc",
        oidc_issuer="https://identity.example.test",
        oidc_audience="autodev",
        oidc_jwks_url="https://identity.example.test/keys",
        oidc_algorithms="RS256",
    )
    authenticator = OIDCAuthenticator(settings)
    monkeypatch.setattr(
        authenticator.jwks, "get_signing_key_from_jwt", lambda token: SimpleNamespace(
            key=public_key)
    )
    token = jwt.encode({
        "sub": "user-1",
        "iss": settings.oidc_issuer,
        "aud": settings.oidc_audience,
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "org_id": "engineering",
        "roles": ["developer"],
    }, private_key, algorithm="RS256")

    assert authenticator.decode(token)["sub"] == "user-1"

    wrong_audience = jwt.encode({
        "sub": "user-1", "iss": settings.oidc_issuer, "aud": "other",
        "iat": now, "exp": now + timedelta(minutes=5),
    }, private_key, algorithm="RS256")
    with pytest.raises(jwt.InvalidAudienceError):
        authenticator.decode(wrong_audience)


def test_oidc_browser_login_issues_opaque_server_session():
    settings = Settings(
        auth_mode="oidc",
        oidc_issuer="https://identity.example.test",
        oidc_audience="autodev",
        oidc_jwks_url="https://identity.example.test/keys",
        oidc_authorization_url="https://identity.example.test/authorize",
        oidc_token_url="https://identity.example.test/token",
        oidc_client_id="autodev-web",
        oidc_client_secret="secret",
        oidc_redirect_uri="http://testserver/api/auth/callback",
        session_cookie_secure=False,
        web_app_url="http://testserver/",
    )
    token_response = Mock()
    token_response.raise_for_status.return_value = None
    token_response.json.return_value = {"id_token": "signed-id-token"}
    oidc_client = AsyncMock()
    oidc_client.post.return_value = token_response
    client_context = AsyncMock()
    client_context.__aenter__.return_value = oidc_client

    with TestClient(app) as client, patch("app.main.get_settings", return_value=settings):
        login = client.get("/api/auth/login", follow_redirects=False)
        state = client.cookies.get("workbench_oidc_state")
        nonce = client.cookies.get("workbench_oidc_nonce")
        assert login.status_code == 307
        assert "code_challenge=" in login.headers["location"]

        claims = {
            "sub": f"oidc-{uuid4().hex}",
            "iss": settings.oidc_issuer,
            "org_id": f"org-{uuid4().hex}",
            "roles": ["admin"],
            "email": "operator@example.test",
            "nonce": nonce,
        }
        with (
            patch("app.main.httpx.AsyncClient", return_value=client_context),
            patch("app.main.OIDCAuthenticator") as authenticator,
        ):
            authenticator.return_value.decode.return_value = claims
            callback = client.get(
                "/api/auth/callback",
                params={"code": "authorization-code", "state": state},
                follow_redirects=False,
            )

        assert callback.status_code == 307
        assert client.cookies.get("workbench_session")
        assert "signed-id-token" not in client.cookies.get("workbench_session")
        with patch("app.auth.dependencies.get_settings", return_value=settings):
            me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["role"] == "admin"
        assert me.json()["organization_id"] == claims["org_id"]


def test_admin_membership_api_enforces_role_and_self_protection():
    user_id = f"member-{uuid4().hex}"
    with TestClient(app) as client:
        created = client.post("/api/admin/members", json={
            "user_id": user_id,
            "email": "member@example.test",
            "role": "viewer",
        })
        updated = client.patch(
            f"/api/admin/members/{user_id}", json={"role": "developer"}
        )
        self_removal = client.delete("/api/admin/members/local-admin")
        app.dependency_overrides[current_principal] = lambda: Principal(
            "viewer", "local", "viewer"
        )
        try:
            denied = client.get("/api/admin/members")
        finally:
            app.dependency_overrides.clear()
        removed = client.delete(f"/api/admin/members/{user_id}")

    assert created.status_code == 201
    assert updated.json()["role"] == "developer"
    assert self_removal.status_code == 409
    assert denied.status_code == 403
    assert removed.status_code == 204


@pytest.mark.parametrize("role", ["viewer", "developer", "reviewer", "admin"])
def test_websocket_read_matrix_allows_known_roles(role: str):
    app.dependency_overrides[current_principal] = lambda: Principal(
        f"{role}-user", "local", role
    )
    try:
        with TestClient(app) as client, client.websocket_connect("/api/events/ws") as socket:
            assert socket.receive_json() == {"event": "connected"}
    finally:
        app.dependency_overrides.clear()
