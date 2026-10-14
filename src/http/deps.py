from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from fastapi import Header, HTTPException, status
from supabase import create_client, Client

from .schemas.common import TenantInfo, UserInfo
from src.services.auth import parse_bearer_token
from src.config import settings
from src.repositories.tenant_repository import tenant_repo
from src.core.logger import logger
from src.http.routers.tenants import JWT_SECRET, JWT_ALG


def is_dev() -> bool:
    """Dev mode flag"""
    env = (os.getenv("APP_ENV") or "").lower()
    debug = os.getenv("DEBUG") == "1"
    return env in ("dev", "development") or debug


def get_tenant_id(
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-Id"),
) -> str:
    """Obtiene tenant_id del header o usa default en dev"""
    if x_tenant_id:
        return x_tenant_id
    if is_dev():
        return "demo-tenant"
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Missing X-Tenant-Id header",
    )


@dataclass(frozen=True)
class CurrentUser:
    user: UserInfo
    tenant: TenantInfo
    plan: str


def verify_tenant_access(
    tenant_from_jwt_id: str, tenant_from_jwt_slug: str, tenant_id_from_header: str
) -> bool:
    """
    ✅ FIX 3: Verifica que el tenant del JWT coincide con el X-Tenant-Id header.
    Antes siempre retornaba True — ahora falla cerrado si no coinciden.

    Args:
        tenant_from_jwt_id:   UUID del tenant extraído del JWT
        tenant_from_jwt_slug: Slug del tenant extraído del JWT
        tenant_id_from_header: Valor del header X-Tenant-Id (puede ser UUID o slug)

    Returns:
        True si coincide, False si no
    """
    return (
        str(tenant_from_jwt_id) == tenant_id_from_header
        or tenant_from_jwt_slug == tenant_id_from_header
    )


def get_current_user(
    tenant_id: str,
    authorization: Optional[str] = None,
) -> CurrentUser:
    """
    Autentica usuario:
    - demo-token → stub (dev/testing)
    - token real → JWT propio (generado por /tenants/login)
    - sin token en dev → demo user
    - sin token en prod → error 401
    """
    token = parse_bearer_token(authorization)

    # Con token
    if token:
        # Stub para testing
        if token == "demo-token":
            return CurrentUser(
                user=UserInfo(id="demo-user", email="demo@local.com", name="Demo User"),
                tenant=TenantInfo(id=tenant_id, name="Demo Tenant"),
                plan="trial",
            )

        # Auth real con JWT propio
        result = verify_access_token(authorization)
        tenant = result["tenant"]

        # ✅ FIX 3: Verificar ownership — el tenant del JWT debe coincidir con el header
        if not verify_tenant_access(
            tenant_from_jwt_id=str(tenant.id),
            tenant_from_jwt_slug=str(tenant.slug),
            tenant_id_from_header=tenant_id,
        ):
            logger.warning(
                f"[AUTH] Acceso denegado: JWT tenant={tenant.id} "
                f"no coincide con header tenant={tenant_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes acceso a este tenant",
            )

        return CurrentUser(
            user=UserInfo(id=str(tenant.id), email=tenant.email, name=tenant.name),
            tenant=TenantInfo(id=str(tenant.id), name=tenant.name),
            plan=str(tenant.plan),
        )

    # Sin token en dev
    if is_dev():
        return CurrentUser(
            user=UserInfo(id="demo-user", email="demo@local.com", name="Demo User"),
            tenant=TenantInfo(id=tenant_id, name="Demo Tenant"),
            plan="trial",
        )

    # Sin token en prod
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header"
    )


# --------------------------------------
# Access token verification (local JWT)
# --------------------------------------


def verify_access_token(authorization: Optional[str]) -> dict:
    import jwt

    token = parse_bearer_token(authorization)
    if not token:
        logger.warning("[AUTH] verify_access_token: header Authorization ausente o vacío")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    # Log del token truncado para diagnóstico (nunca loguear el token completo)
    token_preview = token[:20] + "..." if len(token) > 20 else token
    logger.debug(f"[AUTH] Validando token: {token_preview}")
    logger.debug(f"[AUTH] JWT_SECRET configurado: {bool(JWT_SECRET)}, longitud={len(JWT_SECRET) if JWT_SECRET else 0}")

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        logger.debug(f"[AUTH] Token decodificado OK — sub={payload.get('sub')}, type={payload.get('type')}, exp={payload.get('exp')}")
    except jwt.ExpiredSignatureError as e:
        logger.warning(f"[AUTH] Token expirado: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Access token expirado"
        )
    except jwt.InvalidSignatureError as e:
        logger.warning(f"[AUTH] Firma inválida (JWT_SECRET no coincide): {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Access token inválido — firma incorrecta"
        )
    except jwt.DecodeError as e:
        logger.warning(f"[AUTH] Error decodificando token (malformado?): {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Access token malformado"
        )
    except jwt.InvalidTokenError as e:
        logger.warning(f"[AUTH] Token inválido ({type(e).__name__}): {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Access token inválido"
        )

    if payload.get("type") != "access":
        logger.warning(f"[AUTH] Tipo de token incorrecto: '{payload.get('type')}' (esperado: 'access')")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido (tipo)"
        )

    tenant_id = payload.get("sub")
    if not tenant_id:
        logger.warning("[AUTH] Token sin campo 'sub' (subject)")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token sin subject"
        )

    tenant = tenant_repo.find_by_id(tenant_id)
    if not tenant:
        logger.warning(f"[AUTH] Tenant no encontrado en DB: sub={tenant_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Tenant no encontrado"
        )
    if not tenant.is_active:
        logger.warning(f"[AUTH] Tenant inactivo: {tenant_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Tenant inactivo"
        )

    logger.debug(f"[AUTH] Autenticación exitosa: tenant={tenant_id}")
    return {
        "tenant": tenant,
        "payload": payload,
    }


def get_supabase_client() -> Client:
    """Retorna cliente de Supabase"""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
