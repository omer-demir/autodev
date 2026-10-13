from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.config import Settings
from app.database import create_db_and_tables
from app.github_auth import GitHubCredentialStore
from app.main import app


def github_app_settings(private_key: str) -> Settings:
    return Settings(
        github_app_id="12345",
        github_app_slug="autodev-test",
        github_app_client_id="client-id",
        github_app_client_secret="client-secret",
        github_app_private_key=private_key,
        github_app_private_key_file=None,
        github_token=None,
        web_app_url="http://localhost:3000",
    )


@pytest.mark.asyncio
async def test_installation_token_is_scoped_and_attributed():
    create_db_and_tables()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_key = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    organization_id = f"org-{uuid4().hex}"
    owner_id = f"user-{uuid4().hex}"
    store = GitHubCredentialStore()
    installation = {
        "id": 9876,
        "app_id": 12345,
        "app_slug": "autodev-test",
        "bot_id": 4567,
        "account": {"login": "acme", "type": "Organization"},
        "repository_selection": "selected",
        "permissions": {"contents": "write", "pull_requests": "write"},
    }
    request: httpx.Request | None = None

    async def handler(value: httpx.Request) -> httpx.Response:
        nonlocal request
        request = value
        return httpx.Response(
            201,
            json={
                "token": "short-lived-token",
                "expires_at": "2026-10-12T14:00:00Z",
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = github_app_settings(private_key)
    with (
        patch("app.github_auth.store.get_settings", return_value=settings),
        patch("app.github_auth.store.httpx.AsyncClient", return_value=client),
    ):
        record = store.connect_installation(
            organization_id, owner_id, installation
        )
        identity = await store.identity_for_repository(
            organization_id,
            owner_id,
            "acme",
            "repository",
            write=True,
        )
        app_jwt = store.app_jwt()

    decoded = jwt.decode(
        app_jwt,
        key.public_key(),
        algorithms=["RS256"],
        options={"verify_aud": False},
    )
    assert decoded["iss"] == "12345"
    assert record.bot_id == 4567
    assert store.commit_identity(organization_id, owner_id, "acme") == (
        "autodev-test[bot]",
        "4567+autodev-test[bot]@users.noreply.github.com",
    )
    assert identity is not None
    assert identity.login == "autodev-test[bot]"
    assert identity.token == "short-lived-token"
    assert identity.method == "github_app"
    assert identity.installation_id == 9876
    assert request is not None
    assert request.url.path == "/app/installations/9876/access_tokens"
    assert request.headers["authorization"].startswith("Bearer ")
    assert request.read().decode() == (
        '{"permissions":{"contents":"write","pull_requests":"write"},'
        '"repositories":["repository"]}'
    )
    assert "short-lived-token" not in str(store.status(organization_id, owner_id))


def test_installation_callback_verifies_user_access_before_binding():
    settings = github_app_settings("private-key")
    async_client = httpx.AsyncClient

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login/oauth/access_token":
            return httpx.Response(200, json={"access_token": "temporary-user-token"})
        if request.url.path == "/user/installations":
            assert request.headers["authorization"] == "Bearer temporary-user-token"
            return httpx.Response(200, json={"installations": [{
                "id": 9876,
                "app_id": 12345,
                "app_slug": "autodev-test",
                "account": {"login": "acme", "type": "Organization"},
                "repository_selection": "selected",
                "permissions": {"contents": "write", "pull_requests": "write"},
            }]})
        if request.url.path == "/users/autodev-test[bot]":
            assert request.headers["authorization"] == "Bearer temporary-user-token"
            return httpx.Response(200, json={"id": 4567})
        raise AssertionError(f"Unexpected GitHub request: {request.method} {request.url}")

    def client_factory(*args, **kwargs):
        return async_client(transport=httpx.MockTransport(handler))

    with (
        patch("app.main.get_settings", return_value=settings),
        patch("app.github_auth.store.get_settings", return_value=settings),
        patch("app.main.httpx.AsyncClient", side_effect=client_factory),
        TestClient(app) as client,
    ):
        start = client.get("/api/connectors/github/app/start", follow_redirects=False)
        assert start.status_code in {302, 307}
        state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
        callback = client.get(
            "/api/connectors/github/app/callback",
            params={"code": "temporary-code", "installation_id": 9876, "state": state},
            follow_redirects=False,
        )

    assert callback.status_code == 303
    assert callback.headers["location"] == "http://localhost:3000?github=app-installed"
