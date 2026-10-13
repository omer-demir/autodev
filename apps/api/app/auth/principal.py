from dataclasses import dataclass

from .permissions import ROLE_PERMISSIONS


@dataclass(frozen=True)
class Principal:
    user_id: str
    organization_id: str
    role: str
    email: str | None = None

    def can(self, permission: str) -> bool:
        permissions = ROLE_PERMISSIONS.get(self.role, set())
        return "*" in permissions or permission in permissions
