"""OIDC authentication, organization membership, and role authorization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Depends, HTTPException
from jwt import PyJWKClient
from sqlmodel import Session
from starlette.requests import HTTPConnection

from .config import Settings, get_settings
from .database import get_session
from .models import Membership, Organization, User


ROLE_PERMISSIONS = {
    "viewer": {"read"},
    "developer": {"read", "project.create", "task.create", "task.operate", "sandbox.operate"},
    "reviewer": {"read", "approval.decide", "evaluation.manage"},
    "admin": {"*"},
}
ROLE_PRIORITY = ("admin", "reviewer", "developer", "viewer")


@dataclass(frozen=True)
class Principal:
    user_id: str
    organization_id: str
    role: str
    email: str | None = None

    def can(self, permission: str) -> bool:
        permissions = ROLE_PERMISSIONS.get(self.role, set())
        return "*" in permissions or permission in permissions


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


def _bearer_token(request: HTTPConnection) -> str:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    token = token if scheme.casefold() == "bearer" else request.cookies.get(
        "workbench_access_token", ""
    )
    if not token:
        raise HTTPException(401, "Bearer authentication is required")
    return token


def _claim_roles(claims: dict[str, Any], claim_name: str) -> list[str]:
    value = claims.get(claim_name, [])
    if isinstance(value, str):
        return value.replace(",", " ").split()
    return [str(item) for item in value] if isinstance(value, list) else []


def _provision_oidc_principal(
    session: Session, claims: dict[str, Any], settings: Settings, requested_org: str | None
) -> Principal:
    user_id = str(claims["sub"])
    claim_org = claims.get(settings.oidc_organization_claim)
    organization_id = requested_org or (str(claim_org) if claim_org else None)
    if not organization_id:
        raise HTTPException(403, "OIDC token has no active organization")
    membership = session.get(Membership, (user_id, organization_id))
    if membership is None:
        if not settings.oidc_auto_provision or str(claim_org or "") != organization_id:
            raise HTTPException(
                403, "User is not a member of this organization")
        roles = _claim_roles(claims, settings.oidc_roles_claim)
        role = next(
            (candidate for candidate in ROLE_PRIORITY if candidate in roles), "viewer")
        if session.get(Organization, organization_id) is None:
            session.add(Organization(
                id=organization_id,
                name=str(claims.get("org_name") or organization_id),
            ))
        if session.get(User, user_id) is None:
            session.add(User(
                id=user_id,
                email=str(claims.get("email")) if claims.get(
                    "email") else None,
                display_name=str(claims.get("name")) if claims.get(
                    "name") else None,
                issuer=str(claims["iss"]),
            ))
        membership = Membership(
            user_id=user_id, organization_id=organization_id, role=role
        )
        session.add(membership)
        session.commit()
        session.refresh(membership)
    return Principal(
        user_id=user_id,
        organization_id=organization_id,
        role=membership.role,
        email=str(claims.get("email")) if claims.get("email") else None,
    )


def current_principal(
    request: HTTPConnection, session: Session = Depends(get_session)
) -> Principal:
    settings = get_settings()
    requested_org = request.headers.get("x-organization-id")
    if settings.auth_mode == "local":
        organization_id = requested_org or settings.local_organization_id
        membership = session.get(
            Membership, (settings.local_user_id, organization_id))
        if membership is None:
            raise HTTPException(
                403, "Local user is not a member of this organization")
        return Principal(settings.local_user_id, organization_id, membership.role)
    if settings.auth_mode != "oidc":
        raise HTTPException(
            503, f"Unsupported authentication mode: {settings.auth_mode}")
    try:
        claims = OIDCAuthenticator(settings).decode(_bearer_token(request))
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "OIDC token is invalid") from exc
    return _provision_oidc_principal(session, claims, settings, requested_org)


def require_permission(permission: str):
    def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        if not principal.can(permission):
            raise HTTPException(
                403, f"Role {principal.role} cannot perform {permission}")
        return principal

    return dependency
