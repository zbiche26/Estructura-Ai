# -*- coding: utf-8 -*-
"""
permissions.py - Sistema de Roles y Permisos
=============================================
Define roles, permisos por plan y dependencies
de FastAPI para control de acceso.

Roles:
    admin    → acceso total al tenant
    user     → acceso a operaciones normales
    readonly → solo lectura

Planes:
    starter    → funcionalidades básicas
    growth     → funcionalidades avanzadas
    enterprise → acceso completo

Uso:
    from src.auth.permissions import require_permission, Permission

    @app.post("/products")
    async def create(
        tenant = Depends(require_permission(Permission.PRODUCTS_WRITE))
    ):
        ...
"""

from __future__ import annotations

from enum import Enum
from typing import Callable, Set

from fastapi import Depends, HTTPException, status

from src.auth.middleware import TenantAuth, get_current_tenant


# ── Roles ────────────────────────────────────────────────────


class Role(str, Enum):
    ADMIN = "admin"
    USER = "user"
    READONLY = "readonly"


# ── Permisos ─────────────────────────────────────────────────


class Permission(str, Enum):
    """Permisos granulares del sistema."""

    # Productos
    PRODUCTS_READ = "products:read"
    PRODUCTS_WRITE = "products:write"
    PRODUCTS_DELETE = "products:delete"

    # Conversaciones
    CONVERSATIONS_READ = "conversations:read"
    CONVERSATIONS_WRITE = "conversations:write"

    # Analytics
    ANALYTICS_READ = "analytics:read"

    # Excel Import
    EXCEL_IMPORT = "excel:import"

    # Webhooks
    WEBHOOKS_READ = "webhooks:read"
    WEBHOOKS_WRITE = "webhooks:write"

    # Reportes
    REPORTS_READ = "reports:read"
    REPORTS_EXPORT = "reports:export"

    # Configuración del tenant
    SETTINGS_READ = "settings:read"
    SETTINGS_WRITE = "settings:write"

    # Admin
    TENANT_ADMIN = "tenant:admin"


# ── Permisos por Rol ─────────────────────────────────────────

ROLE_PERMISSIONS: dict[str, Set[Permission]] = {
    Role.ADMIN: {
        Permission.PRODUCTS_READ,
        Permission.PRODUCTS_WRITE,
        Permission.PRODUCTS_DELETE,
        Permission.CONVERSATIONS_READ,
        Permission.CONVERSATIONS_WRITE,
        Permission.ANALYTICS_READ,
        Permission.EXCEL_IMPORT,
        Permission.WEBHOOKS_READ,
        Permission.WEBHOOKS_WRITE,
        Permission.REPORTS_READ,
        Permission.REPORTS_EXPORT,
        Permission.SETTINGS_READ,
        Permission.SETTINGS_WRITE,
        Permission.TENANT_ADMIN,
    },
    Role.USER: {
        Permission.PRODUCTS_READ,
        Permission.PRODUCTS_WRITE,
        Permission.CONVERSATIONS_READ,
        Permission.CONVERSATIONS_WRITE,
        Permission.ANALYTICS_READ,
        Permission.EXCEL_IMPORT,
        Permission.WEBHOOKS_READ,
        Permission.REPORTS_READ,
        Permission.SETTINGS_READ,
    },
    Role.READONLY: {
        Permission.PRODUCTS_READ,
        Permission.CONVERSATIONS_READ,
        Permission.ANALYTICS_READ,
        Permission.REPORTS_READ,
        Permission.SETTINGS_READ,
    },
}


# ── Permisos por Plan ─────────────────────────────────────────

PLAN_PERMISSIONS: dict[str, Set[Permission]] = {
    "starter": {
        Permission.PRODUCTS_READ,
        Permission.PRODUCTS_WRITE,
        Permission.CONVERSATIONS_READ,
        Permission.CONVERSATIONS_WRITE,
        Permission.ANALYTICS_READ,
        Permission.EXCEL_IMPORT,
        Permission.REPORTS_READ,
        Permission.SETTINGS_READ,
        Permission.SETTINGS_WRITE,
    },
    "growth": {
        Permission.PRODUCTS_READ,
        Permission.PRODUCTS_WRITE,
        Permission.PRODUCTS_DELETE,
        Permission.CONVERSATIONS_READ,
        Permission.CONVERSATIONS_WRITE,
        Permission.ANALYTICS_READ,
        Permission.EXCEL_IMPORT,
        Permission.WEBHOOKS_READ,
        Permission.WEBHOOKS_WRITE,
        Permission.REPORTS_READ,
        Permission.REPORTS_EXPORT,
        Permission.SETTINGS_READ,
        Permission.SETTINGS_WRITE,
    },
    "enterprise": {p for p in Permission},  # todos los permisos
}


# ── Checker de Permisos ──────────────────────────────────────


class PermissionChecker:
    """
    Verifica si un tenant tiene un permiso específico.

    Un tenant tiene un permiso si:
    1. Su ROL lo permite, Y
    2. Su PLAN lo permite

    Ambas condiciones deben cumplirse.
    """

    def has_permission(
        self,
        tenant: TenantAuth,
        permission: Permission,
    ) -> bool:
        """
        Verifica si el tenant tiene el permiso.

        Args:
            tenant:     TenantAuth con rol y plan
            permission: Permiso a verificar

        Returns:
            True si tiene el permiso
        """
        role_perms = ROLE_PERMISSIONS.get(tenant.role, set())
        plan_perms = PLAN_PERMISSIONS.get(tenant.plan, set())

        return permission in role_perms and permission in plan_perms

    def has_any_permission(
        self,
        tenant: TenantAuth,
        permissions: list[Permission],
    ) -> bool:
        """Retorna True si tiene AL MENOS uno de los permisos."""
        return any(self.has_permission(tenant, p) for p in permissions)

    def has_all_permissions(
        self,
        tenant: TenantAuth,
        permissions: list[Permission],
    ) -> bool:
        """Retorna True si tiene TODOS los permisos."""
        return all(self.has_permission(tenant, p) for p in permissions)

    def get_permissions(self, tenant: TenantAuth) -> Set[Permission]:
        """Retorna todos los permisos del tenant."""
        role_perms = ROLE_PERMISSIONS.get(tenant.role, set())
        plan_perms = PLAN_PERMISSIONS.get(tenant.plan, set())
        return role_perms & plan_perms


checker = PermissionChecker()


# ── Dependencies de FastAPI ───────────────────────────────────


def require_permission(permission: Permission) -> Callable:
    """
    Dependency factory que requiere un permiso específico.

    Uso:
        @app.post("/products")
        async def create(
            tenant = Depends(require_permission(Permission.PRODUCTS_WRITE))
        ):
            ...
    """

    async def _check(
        tenant: TenantAuth = Depends(get_current_tenant),
    ) -> TenantAuth:
        if not checker.has_permission(tenant, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Permiso requerido: {permission.value} — "
                    f"tu plan '{tenant.plan}' o rol '{tenant.role}' "
                    f"no incluye este permiso"
                ),
            )
        return tenant

    return _check


def require_plan(plan: str) -> Callable:
    """
    Dependency que requiere un plan mínimo.

    Orden: starter < growth < enterprise

    Uso:
        @app.get("/reports/export")
        async def export(
            tenant = Depends(require_plan("growth"))
        ):
            ...
    """
    PLAN_ORDER = {"starter": 0, "growth": 1, "enterprise": 2}

    async def _check(
        tenant: TenantAuth = Depends(get_current_tenant),
    ) -> TenantAuth:
        tenant_level = PLAN_ORDER.get(tenant.plan, 0)
        required_level = PLAN_ORDER.get(plan, 0)

        if tenant_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Se requiere plan '{plan}' o superior — "
                    f"tu plan actual es '{tenant.plan}'"
                ),
            )
        return tenant

    return _check


def require_role(role: Role) -> Callable:
    """
    Dependency que requiere un rol específico.

    Uso:
        @app.delete("/tenant/{id}")
        async def delete(
            tenant = Depends(require_role(Role.ADMIN))
        ):
            ...
    """

    async def _check(
        tenant: TenantAuth = Depends(get_current_tenant),
    ) -> TenantAuth:
        if tenant.role != role.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Se requiere rol '{role.value}'",
            )
        return tenant

    return _check
