from typing import Any

import jwt
from jwt import PyJWKClient

from ..config import Settings


class OIDCAuthenticator:
    def __init__(self, settings: Settings) -> None:
        if not settings.oidc_issuer or not settings.oidc_audience or not settings.oidc_jwks_url:
            raise RuntimeError(
                "OIDC mode requires WORKBENCH_OIDC_ISSUER, OIDC_AUDIENCE, and OIDC_JWKS_URL"
            )
        self.settings = settings
        self.jwks = PyJWKClient(settings.oidc_jwks_url)

    def decode(self, token: str) -> dict[str, Any]:
        key = self.jwks.get_signing_key_from_jwt(token).key
        return jwt.decode(
            token,
            key,
            algorithms=[
                item.strip() for item in self.settings.oidc_algorithms.split(",") if item.strip()
            ],
            audience=self.settings.oidc_audience,
            issuer=self.settings.oidc_issuer,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
