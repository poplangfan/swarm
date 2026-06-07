"""Tests for tool permission system."""

import pytest
from tools.permission import Permission, PermissionSet


class TestPermissionSet:
    def test_has_permission(self):
        ps = PermissionSet(grants={"web:search", "message:send"})
        assert ps.has("web:search")
        assert ps.has(Permission.WEB_SEARCH)
        assert not ps.has("admin:delete")

    def test_has_all(self):
        ps = PermissionSet(grants={"web:search", "web:fetch", "message:send"})
        assert ps.has_all("web:search", "web:fetch")
        assert not ps.has_all("web:search", "admin:delete")

    def test_has_any(self):
        ps = PermissionSet(grants={"web:search"})
        assert ps.has_any("web:search", "admin:delete")
        assert not ps.has_any("admin:delete", "file:write")

    def test_wildcard_grant(self):
        ps = PermissionSet(grants={"*"})
        assert ps.has("anything")
        assert ps.has("literally.anything.at.all")
        assert ps.has_all("a", "b", "c")

    def test_full_access(self):
        ps = PermissionSet.full_access()
        assert ps.has("any.permission")

    def test_from_list(self):
        ps = PermissionSet.from_list(["a", "b", "c"])
        assert ps.has("a")
        assert ps.has("b")
        assert not ps.has("d")

    def test_default_permissions_exist(self):
        from tools.permission import DEFAULT_PERMISSIONS
        assert "user" in DEFAULT_PERMISSIONS
        assert "admin" in DEFAULT_PERMISSIONS
        user_perms = DEFAULT_PERMISSIONS["user"]
        assert user_perms.has(Permission.WEB_SEARCH)
        assert user_perms.has(Permission.MESSAGE_SEND)
        assert not user_perms.has("admin:delete")
        admin_perms = DEFAULT_PERMISSIONS["admin"]
        assert admin_perms.has("anything")


class TestPermissionEnum:
    def test_all_values_unique(self):
        values = [p.value for p in Permission]
        assert len(values) == len(set(values))

    def test_standard_permissions(self):
        assert Permission.MESSAGE_SEND.value == "message:send"
        assert Permission.FILE_READ.value == "file:read"
        assert Permission.WEB_SEARCH.value == "web:search"
        assert Permission.CRON_MANAGE.value == "cron:manage"
