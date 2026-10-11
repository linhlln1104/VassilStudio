"""Stable identities and permissions shared by HTTP and background admission."""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass


ALL_SCOPES = frozenset({
    "production:read", "production:write", "production:review",
    "tts:read", "tts:write", "asr:read", "asr:write", "voices:read", "voices:write",
    "models:read", "models:manage", "system:read", "iam:manage", "audit:read",
})
ROLE_SCOPES: dict[str, frozenset[str]] = {
    "owner": frozenset({"*"}),
    "admin": frozenset({"*"}),
    "operator": ALL_SCOPES - {"iam:manage", "audit:read", "production:review"},
    "editor": frozenset({
        "production:read", "production:write", "voices:read", "tts:read", "tts:write",
        "models:read",
    }),
    "reviewer": frozenset({
        "production:read", "production:review", "voices:read", "tts:read", "asr:read",
        "models:read",
    }),
}


@dataclass(frozen=True)
class Principal:
    principal_id: str
    name: str
    kind: str
    role: str
    scopes: tuple[str, ...]

    def has_scope(self, scope: str) -> bool:
        return "*" in self.scopes or scope in self.scopes

    @property
    def is_admin(self) -> bool:
        # A role whose key has been narrowed must not bypass project ACLs.
        return "*" in self.scopes


_principal: ContextVar[Principal | None] = ContextVar("vassil_principal", default=None)


def current_principal() -> Principal | None:
    return _principal.get()


def current_actor_id() -> str | None:
    principal = current_principal()
    return principal.principal_id if principal else None


def set_current_principal(principal: Principal | None):
    return _principal.set(principal)


def reset_current_principal(token) -> None:
    _principal.reset(token)
