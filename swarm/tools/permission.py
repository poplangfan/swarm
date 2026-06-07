"""Tool permission system — declare and enforce access control."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Permission(Enum):
    """Standard tool permissions."""
    MESSAGE_SEND = "message:send"
    MESSAGE_READ = "message:read"
    FILE_READ = "file:read"
    FILE_WRITE = "file:write"
    WEB_SEARCH = "web:search"
    WEB_FETCH = "web:fetch"
    CRON_MANAGE = "cron:manage"
    SYSTEM_COMMAND = "system:command"
    PLUGIN_USE = "plugin:use"


@dataclass
class PermissionSet:
    """A set of permissions that can be checked against."""
    grants: set[str] = field(default_factory=set)

    def has(self, permission: Permission | str) -> bool:
        perm_str = permission.value if isinstance(permission, Permission) else permission
        return perm_str in self.grants or "*" in self.grants

    def has_all(self, *permissions: Permission | str) -> bool:
        return all(self.has(p) for p in permissions)

    def has_any(self, *permissions: Permission | str) -> bool:
        return any(self.has(p) for p in permissions)

    @classmethod
    def from_list(cls, perms: list[str]) -> PermissionSet:
        return cls(grants=set(perms))

    @classmethod
    def full_access(cls) -> PermissionSet:
        return cls(grants={"*"})


# Default permissions for built-in roles
DEFAULT_PERMISSIONS: dict[str, PermissionSet] = {
    "user": PermissionSet(grants={
        Permission.MESSAGE_SEND.value,
        Permission.MESSAGE_READ.value,
        Permission.WEB_SEARCH.value,
        Permission.WEB_FETCH.value,
        Permission.SYSTEM_COMMAND.value,
    }),
    "admin": PermissionSet.full_access(),
}
