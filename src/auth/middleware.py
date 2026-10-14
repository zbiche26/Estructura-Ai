# -*- coding: utf-8 -*-
"""
middleware.py - Wrapper de Autenticación
=========================================
Este módulo es un WRAPPER sobre src.http.deps (fuente de verdad de auth).

Mantiene compatibilidad con permissions.py que usa TenantAuth y
get_current_tenant — pero la autenticación real ocurre en deps.py
usando JWT propio (generado por /tenants/login).

Flujo unificado:
    1. Frontend hace login con /tenants/login
    2. Backend devuelve JWT propio firmado con JWT_SECRET
    3. Frontend envía: Authorization: Bearer <jwt>
    4. deps.py valida el token y popula TenantContextManager
    5. Este wrapper adapta CurrentUser → TenantAuth para permissions.py

NO usar este módulo directamente en routers nuevos.
Usar get_current_user de src.http.deps en su lugar.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.core.logger import logger
from src.http.deps import CurrentUser, get_current_user, get_tenant_id

security = HTTPBearer(auto_error=False)


# ── Value Object ─────────────────────────────────────────────


@dataclass
class TenantAuth:
    """
    Contexto de autenticación compatible con permissions.py.

    Se construye a partir de CurrentUser (deps.py).
    """

    tenant_id: str
    supabase_uid: str
    email: str = ""
    role: str = "admin"
    plan: str = "starter"

    def is_admin(self) -> bool:
        return self.role == "admin"

    def __repr__(self) -> str:
        return (
            f"TenantAuth(tenant='{self.tenant_id}', "
            f"role='{self.role}', plan='{self.plan}')"
        )


# ── Adaptador CurrentUser → TenantAuth ───────────────────────


def _to_tenant_auth(current_user: CurrentUser) -> TenantAuth:
    """Convierte CurrentUser (deps.py) en TenantAuth (permissions.py)."""
    return TenantAuth(
        tenant_id=str(current_user.tenant.id),
        supabase_uid=str(current_user.user.id),
        email=current_user.user.email,
        role="admin",  # Todos los tenants son admin de su propio espacio
        plan=current_user.plan,
    )


# ── Dependencies de FastAPI ───────────────────────────────────


async def get_current_tenant(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-Id"),
) -> TenantAuth:
    """
    Dependency compatible con permissions.py.

    Delega la autenticación real a deps.get_current_user (JWT propio).
    Retorna TenantAuth para compatibilidad con permissions.py.
    """
    authorization = None
    if credentials:
        authorization = f"Bearer {credentials.credentials}"

    tenant_id = get_tenant_id(x_tenant_id)

    current_user = get_current_user(
        tenant_id=tenant_id,
        authorization=authorization,
    )

    tenant_auth = _to_tenant_auth(current_user)
    logger.debug(f"[AUTH WRAPPER] TenantAuth construido: {tenant_auth}")
    return tenant_auth


async def get_current_tenant_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-Id"),
) -> Optional[TenantAuth]:
    """Versión opcional — retorna None si no hay token."""
    try:
        return await get_current_tenant(request, credentials, x_tenant_id)
    except Exception:
        return None


async def require_admin(
    tenant: TenantAuth = Depends(get_current_tenant),
) -> TenantAuth:
    """Dependency que requiere rol admin."""
    if not tenant.is_admin():
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere rol de administrador",
        )
    return tenant
