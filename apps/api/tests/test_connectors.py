import html
import json
import re
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.config import Settings
from app.database import create_db_and_tables, engine
from app.main import app
from app.models import Connector, GitHubAppConfiguration, Project


def connector_settings() -> Settings:
    return Settings(
        api_url="http://testserver",
        web_app_url="http://localhost:3000",
        session_cookie_secure=False,
        credential_master_key=f"test-{uuid4().hex}",
        github_token=None,
    )


def state_from_location(location: str) -> str:
    return parse_qs(urlparse(location).query)["state"][0]


def test_manifest_connection_installation_and_repository_binding():
    create_db_and_tables()
    settings = connector_settings()
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    real_async_client = httpx.AsyncClient

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/app-manifests/"):
            return httpx.Response(201, json={
                "id": 24680,
                "slug": "autodev-manifest-test",
                "client_id": "manifest-client-id",
                "client_secret": "manifest-client-secret",
                "pem": pem,
                "webhook_secret": "manifest-webhook-secret",
            })
        if request.url.path == "/login/oauth/access_token":
            return httpx.Response(200, json={"access_token": "temporary-user-token"})
        if request.url.path == "/user/installations":
            assert request.headers["authorization"] == "Bearer temporary-user-token"
            return httpx.Response(200, json={"installations": [{
                "id": 97531,
                "app_id": 24680,
                "app_slug": "autodev-manifest-test",
                "account": {"login": "acme", "type": "Organization"},
                "repository_selection": "selected",
                "permissions": {
                    "actions": "read",
                    "checks": "read",
                    "contents": "write",
                    "metadata": "read",
                    "pull_requests": "write",
                    "workflows": "write",
                },
            }]})
        if request.url.path == "/users/autodev-manifest-test[bot]":
            return httpx.Response(200, json={"id": 86420})
        if request.url.path == "/app/installations/97531/access_tokens":
            return httpx.Response(201, json={"token": "short-lived-installation-token"})
        if request.url.path == "/installation/repositories":
            assert request.headers["authorization"] == (
                "Bearer short-lived-installation-token"
            )
            return httpx.Response(200, json={"repositories": [{
                "name": "repository",
                "full_name": "acme/repository",
                "private": True,
                "clone_url": "https://github.com/acme/repository.git",
                "ssh_url": "git@github.com:acme/repository.git",
                "html_url": "https://github.com/acme/repository",
                "default_branch": "main",
                "updated_at": "2026-10-12T12:00:00Z",
                "owner": {"login": "acme"},
            }]})
        raise AssertionError(f"Unexpected GitHub request: {request.method} {request.url}")

    def client_factory(*args, **kwargs):
        return real_async_client(transport=httpx.MockTransport(handler))

    from unittest.mock import patch

    with (
        patch("app.main.get_settings", return_value=settings),
        patch("app.github_auth.store.get_settings", return_value=settings),
        patch("app.main.httpx.AsyncClient", side_effect=client_factory),
        TestClient(app) as client,
    ):
        start = client.get(
            "/api/connectors/github/manifest/start",
            params={"name": "AutoDev Test"},
        )
        assert start.status_code == 200
        action = html.unescape(re.search(r'action="([^"]+)"', start.text).group(1))
        state = state_from_location(action)
        manifest_value = html.unescape(
            re.search(r'name="manifest" value="([^"]+)"', start.text).group(1)
        )
        manifest = json.loads(manifest_value)
        assert manifest["name"].startswith("AutoDevTest-")
        assert manifest["name"] != "AutoDev Test"
        assert len(manifest["name"].rsplit("-", 1)[1]) == 12
        assert manifest["redirect_url"] == (
            "http://localhost:3000/api/connectors/github/manifest/callback"
        )
        assert manifest["callback_urls"] == [
            "http://localhost:3000/api/connectors/github/install/callback"
        ]
        assert manifest["request_oauth_on_install"] is True
        assert manifest["default_permissions"] == {
            "actions": "read",
            "checks": "read",
            "contents": "write",
            "metadata": "read",
            "pull_requests": "write",
            "workflows": "write",
        }

        registered = client.get(
            "/api/connectors/github/manifest/callback",
            params={"code": "manifest-code", "state": state},
            follow_redirects=False,
        )
        assert registered.status_code == 303
        connector_id = parse_qs(
            urlparse(registered.headers["location"]).query
        )["connector"][0]

        with Session(engine) as session:
            connector = session.get(Connector, connector_id)
            configuration = session.get(GitHubAppConfiguration, connector_id)
            assert connector is not None
            assert connector.status == "PENDING_INSTALLATION"
            assert configuration is not None
            assert configuration.encrypted_client_secret != "manifest-client-secret"
            assert configuration.encrypted_private_key != pem
            assert "manifest-client-secret" not in configuration.encrypted_client_secret

        install = client.get(
            f"/api/connectors/{connector_id}/github/install",
            follow_redirects=False,
        )
        assert install.status_code in {302, 307}
        install_state = state_from_location(install.headers["location"])
        installed = client.get(
            "/api/connectors/github/install/callback",
            params={
                "code": "install-code",
                "installation_id": 97531,
                "state": install_state,
            },
            follow_redirects=False,
        )
        assert installed.status_code == 303

        connections = client.get("/api/connectors")
        assert connections.status_code == 200
        selected = next(item for item in connections.json() if item["id"] == connector_id)
        assert selected["status"] == "ACTIVE"
        assert selected["account_login"] == "acme"
        assert "client_secret" not in json.dumps(selected)
        assert "private_key" not in json.dumps(selected)

        accounts = client.get(f"/api/connectors/{connector_id}/accounts")
        assert accounts.status_code == 200
        assert accounts.json()["accounts"] == [{
            "login": "acme",
            "type": "Organization",
            "installation_id": 97531,
            "repository_selection": "selected",
        }]

        discovery = client.get(
            f"/api/connectors/{connector_id}/repositories",
            params={"account": "acme", "query": "repo"},
        )
        assert discovery.status_code == 200
        assert discovery.json()["repositories"] == [{
            "name": "repository",
            "full_name": "acme/repository",
            "private": True,
            "clone_url": "https://github.com/acme/repository.git",
            "ssh_url": "git@github.com:acme/repository.git",
            "html_url": "https://github.com/acme/repository",
            "owner": "acme",
            "default_branch": "main",
            "updated_at": "2026-10-12T12:00:00Z",
        }]

        project = client.post("/api/projects", json={
            "name": "acme/repository",
            "repository_path": "acme/repository",
            "source_type": "github",
            "repository_url": "https://github.com/acme/repository.git",
            "default_branch": "main",
            "connector_id": connector_id,
            "transport": "ssh",
        })
        assert project.status_code == 201
        assert project.json()["connector_id"] == connector_id
        assert project.json()["transport"] == "ssh"

        blocked_delete = client.delete(f"/api/connectors/{connector_id}")
        assert blocked_delete.status_code == 409

    with Session(engine) as session:
        stored_project = session.exec(select(Project).where(
            Project.connector_id == connector_id
        )).first()
        assert stored_project is not None
