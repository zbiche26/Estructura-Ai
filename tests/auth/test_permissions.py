# -*- coding: utf-8 -*-
"""
test_permissions.py - Tests del Sistema de Permisos
====================================================
Ejecutar: pytest tests/auth/test_permissions.py -v
"""

import pytest
from fastapi import HTTPException

from src.auth.middleware import TenantAuth
from src.auth.permissions import (
    Permission,
    PermissionChecker,
    Role,
    ROLE_PERMISSIONS,
    PLAN_PERMISSIONS,
)


# ── Helpers ───────────────────────────────────────────────────

def make_tenant(
    role: str = "admin",
    plan: str = "growth",
) -> TenantAuth:
    return TenantAuth(
        tenant_id    = "tenant-test",
        supabase_uid = "uid-test",
        role         = role,
        plan         = plan,
    )


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def checker() -> PermissionChecker:
    return PermissionChecker()


# ── Tests: Roles ──────────────────────────────────────────────

class TestRoles:

    def test_admin_tiene_todos_los_permisos_de_rol(self):
        assert Permission.TENANT_ADMIN  in ROLE_PERMISSIONS[Role.ADMIN]
        assert Permission.SETTINGS_WRITE in ROLE_PERMISSIONS[Role.ADMIN]
        assert Permission.PRODUCTS_DELETE in ROLE_PERMISSIONS[Role.ADMIN]

    def test_user_no_tiene_admin(self):
        assert Permission.TENANT_ADMIN not in ROLE_PERMISSIONS[Role.USER]

    def test_user_no_puede_borrar_productos(self):
        assert Permission.PRODUCTS_DELETE not in ROLE_PERMISSIONS[Role.USER]

    def test_readonly_solo_lectura(self):
        write_perms = [
            Permission.PRODUCTS_WRITE,
            Permission.CONVERSATIONS_WRITE,
            Permission.SETTINGS_WRITE,
            Permission.EXCEL_IMPORT,
        ]
        for p in write_perms:
            assert p not in ROLE_PERMISSIONS[Role.READONLY]

    def test_readonly_puede_leer(self):
        assert Permission.PRODUCTS_READ      in ROLE_PERMISSIONS[Role.READONLY]
        assert Permission.ANALYTICS_READ     in ROLE_PERMISSIONS[Role.READONLY]
        assert Permission.CONVERSATIONS_READ in ROLE_PERMISSIONS[Role.READONLY]


# ── Tests: Planes ─────────────────────────────────────────────

class TestPlanes:

    def test_starter_no_tiene_webhooks_write(self):
        assert Permission.WEBHOOKS_WRITE not in PLAN_PERMISSIONS["starter"]

    def test_starter_no_tiene_reports_export(self):
        assert Permission.REPORTS_EXPORT not in PLAN_PERMISSIONS["starter"]

    def test_growth_tiene_webhooks(self):
        assert Permission.WEBHOOKS_READ  in PLAN_PERMISSIONS["growth"]
        assert Permission.WEBHOOKS_WRITE in PLAN_PERMISSIONS["growth"]

    def test_growth_tiene_reports_export(self):
        assert Permission.REPORTS_EXPORT in PLAN_PERMISSIONS["growth"]

    def test_enterprise_tiene_todo(self):
        for p in Permission:
            assert p in PLAN_PERMISSIONS["enterprise"]


# ── Tests: PermissionChecker ──────────────────────────────────

class TestPermissionChecker:

    def test_admin_growth_puede_exportar(self, checker):
        tenant = make_tenant(role="admin", plan="growth")
        assert checker.has_permission(tenant, Permission.REPORTS_EXPORT)

    def test_admin_starter_no_puede_exportar(self, checker):
        tenant = make_tenant(role="admin", plan="starter")
        assert not checker.has_permission(tenant, Permission.REPORTS_EXPORT)

    def test_readonly_no_puede_escribir_aunque_sea_enterprise(self, checker):
        tenant = make_tenant(role="readonly", plan="enterprise")
        assert not checker.has_permission(tenant, Permission.PRODUCTS_WRITE)

    def test_user_growth_puede_importar_excel(self, checker):
        tenant = make_tenant(role="user", plan="growth")
        assert checker.has_permission(tenant, Permission.EXCEL_IMPORT)

    def test_has_any_permission(self, checker):
        tenant = make_tenant(role="readonly", plan="starter")
        assert checker.has_any_permission(
            tenant,
            [Permission.PRODUCTS_WRITE, Permission.PRODUCTS_READ]
        )

    def test_has_any_permission_false(self, checker):
        tenant = make_tenant(role="readonly", plan="starter")
        assert not checker.has_any_permission(
            tenant,
            [Permission.PRODUCTS_WRITE, Permission.SETTINGS_WRITE]
        )

    def test_has_all_permissions_true(self, checker):
        tenant = make_tenant(role="admin", plan="growth")
        assert checker.has_all_permissions(
            tenant,
            [Permission.PRODUCTS_READ, Permission.ANALYTICS_READ]
        )

    def test_has_all_permissions_false(self, checker):
        tenant = make_tenant(role="admin", plan="starter")
        assert not checker.has_all_permissions(
            tenant,
            [Permission.PRODUCTS_READ, Permission.REPORTS_EXPORT]
        )

    def test_get_permissions_retorna_set(self, checker):
        tenant = make_tenant(role="admin", plan="growth")
        perms  = checker.get_permissions(tenant)
        assert isinstance(perms, set)
        assert len(perms) > 0

    def test_get_permissions_starter_menor_que_growth(self, checker):
        starter    = make_tenant(role="admin", plan="starter")
        growth     = make_tenant(role="admin", plan="growth")
        perms_s    = checker.get_permissions(starter)
        perms_g    = checker.get_permissions(growth)
        assert len(perms_s) < len(perms_g)

    def test_plan_desconocido_sin_permisos(self, checker):
        tenant = make_tenant(role="admin", plan="plan_inexistente")
        assert not checker.has_permission(tenant, Permission.PRODUCTS_READ)

    def test_rol_desconocido_sin_permisos(self, checker):
        tenant = make_tenant(role="rol_inexistente", plan="growth")
        assert not checker.has_permission(tenant, Permission.PRODUCTS_READ)