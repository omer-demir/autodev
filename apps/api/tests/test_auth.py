from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.auth import OIDCAuthenticator, Principal
from app.config import Settings


def test_role_permissions_are_default_deny():
    developer = Principal("dev", "org", "developer")
    unknown = Principal("unknown", "org", "custom")

    assert developer.can("task.create")
    assert not developer.can("approval.decide")
    assert not unknown.can("read")


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
