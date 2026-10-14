"""
Router de Tenants - Endpoints para gestiÃ³n de Tenants

Endpoints:
- POST /tenants/register: Registrar un nuevo tenant

Responsabilidades:
- Validar datos de entrada (schemas Pydantic)
- Hashear contraseÃ±as con bcrypt
- Verificar unicidad de email y slug
- Manejar errores de integridad (400, 409)
- Devolver respuestas sin exponer datos sensibles
"""

from __future__ import annotations

import os
import time
import uuid
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Dict, List

import jwt
from fastapi import APIRouter, HTTPException, status, Request, Depends

# Definir el router para este mÃ³dulo con prefijo
router = APIRouter(prefix="/tenants")
from passlib.context import CryptContext
from postgrest.exceptions import APIError

from src.schemas.tenant_schemas import (
    TenantCreate,
    TenantCreatedResponse,
    TenantResponse,
    TenantLoginRequest,
    TenantLoginResponse,
    ErrorResponse,
    RefreshTokenRequest,
    TenantLogoutRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordRequest,
    MessageResponse,
    TenantUpdateRequest,
    ApiKeyCreateRequest,
    ApiKeyResponse,
    UsageResponse,
    UsageLimits,
    BillingInfoResponse,
)


@router.post(
    "/refresh-token",
    response_model=TenantLoginResponse,
    status_code=status.HTTP_200_OK,
    tags=["Tenants"],
    summary="Refrescar access token",
    description="Devuelve nuevos access y refresh tokens si el refresh_token es vÃ¡lido.",
    responses={
        200: {
            "description": "Tokens refrescados",
            "model": TenantLoginResponse,
        },
        401: {
            "description": "Refresh token invÃ¡lido o expirado",
            "model": ErrorResponse,
        },
        500: {
            "description": "Error interno del servidor",
            "model": ErrorResponse,
        },
    },
)
async def refresh_token(data: RefreshTokenRequest) -> TenantLoginResponse:
    """Endpoint para refrescar access_token usando refresh_token vÃ¡lido."""
    try:
        try:
            payload = jwt.decode(
                data.refresh_token, JWT_REFRESH_SECRET, algorithms=[JWT_ALG]
            )
        except jwt.ExpiredSignatureError:
            logger.warning("âš ï¸ Refresh token expirado")
            raise _error(
                status.HTTP_401_UNAUTHORIZED,
                "REFRESH_TOKEN_EXPIRED",
                "Refresh token expirado",
            )
        except jwt.InvalidTokenError:
            logger.warning("âš ï¸ Refresh token invÃ¡lido")
            raise _error(
                status.HTTP_401_UNAUTHORIZED,
                "REFRESH_TOKEN_INVALID",
                "Refresh token invÃ¡lido",
            )

        tenant_id = payload.get("sub")
        email = payload.get("email")
        plan = payload.get("plan")
        version = payload.get("ver")
        if not tenant_id or not email:
            logger.warning("âš ï¸ Refresh token sin datos requeridos")
            raise _error(
                status.HTTP_401_UNAUTHORIZED,
                "REFRESH_TOKEN_INVALID",
                "Refresh token invÃ¡lido",
            )

        if payload.get("type") != "refresh":
            logger.warning("âš ï¸ Token no es refresh")
            raise _error(
                status.HTTP_401_UNAUTHORIZED,
                "REFRESH_TOKEN_INVALID",
                "Refresh token invÃ¡lido",
            )

        tenant = tenant_repo.find_by_id(tenant_id)
        if not tenant:
            logger.warning("âš ï¸ Tenant no encontrado para refresh")
            raise _error(
                status.HTTP_401_UNAUTHORIZED,
                "REFRESH_TOKEN_INVALID",
                "Refresh token invÃ¡lido",
            )

        if tenant.email.lower() != email.lower():
            logger.warning("âš ï¸ Refresh token no corresponde al email del tenant")
            raise _error(
                status.HTTP_401_UNAUTHORIZED,
                "REFRESH_TOKEN_INVALID",
                "Refresh token invÃ¡lido",
            )

        if not tenant.is_active:
            logger.warning("âš ï¸ Refresh bloqueado: tenant inactivo")
            raise _error(
                status.HTTP_403_FORBIDDEN, "TENANT_INACTIVE", "Tenant inactivo"
            )

        if version and current_session_version(str(tenant.id)) not in (None, version):
            logger.warning("âš ï¸ Refresh token revocado por versiÃ³n")
            raise _error(
                status.HTTP_401_UNAUTHORIZED,
                "REFRESH_TOKEN_INVALID",
                "Refresh token invÃ¡lido",
            )

        if is_refresh_limited(email):
            logger.warning(f"ðŸš¦ LÃ­mite de refresh superado para {email}")
            raise _error(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "REFRESH_RATE_LIMIT",
                "Demasiadas solicitudes de refresh",
            )

        record_refresh(email)

        access_token = create_token(
            sub=str(tenant.id),
            secret=JWT_SECRET,
            expires_in=ACCESS_EXPIRES_SECONDS,
            token_type="access",
            extra={
                "email": tenant.email,
                "plan": tenant.plan,
                "ver": version or current_session_version(str(tenant.id)),
                "slug": tenant.slug,
                "tenant_id": str(tenant.id),
            },
        )

        refresh_token_new = create_token(
            sub=str(tenant.id),
            secret=JWT_REFRESH_SECRET,
            expires_in=REFRESH_EXPIRES_SECONDS,
            token_type="refresh",
            extra={
                "email": tenant.email,
                "plan": tenant.plan,
                "ver": version or current_session_version(str(tenant.id)),
            },
        )

        tenant_response = TenantResponse(
            id=tenant.id,
            name=tenant.name,
            email=tenant.email,
            slug=tenant.slug,
            is_active=tenant.is_active,
            plan=tenant.plan,
            max_products=tenant.max_products,
            max_conversations=tenant.max_conversations,
            whatsapp_phone_number=tenant.whatsapp_phone_number,
            whatsapp_phone_id=tenant.whatsapp_phone_id,
            whatsapp_enabled=tenant.whatsapp_enabled,
            created_at=tenant.created_at,
            updated_at=tenant.updated_at,
        )

        return TenantLoginResponse(
            access_token=access_token,
            refresh_token=refresh_token_new,
            expires_in=ACCESS_EXPIRES_SECONDS,
            tenant=tenant_response,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"âŒ Error inesperado en refresh token: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
    status_code=status.HTTP_200_OK,
    tags=["Tenants"],
    summary="Solicitar recuperaciÃ³n de contraseÃ±a",
    description="Genera un token de recuperaciÃ³n y envÃ­a el enlace por correo (respuesta genÃ©rica para evitar enumeraciÃ³n).",
)
async def forgot_password(data: ForgotPasswordRequest) -> ForgotPasswordResponse:
    # Respuesta genÃ©rica para evitar revelar si el email existe o no
    generic_response = {
        "message": "Si el email existe se enviÃ³ un enlace para restablecer la contraseÃ±a.",
        "reset_token": None,
    }

    tenant = tenant_repo.find_by_email(data.email.lower())
    if not tenant:
        logger.warning("âš ï¸ Solicitud de recuperaciÃ³n para email no registrado")
        return ForgotPasswordResponse(**generic_response)

    token = _create_password_reset_token(str(tenant.id))

    # En dev exponemos el token; en prod enviamos correo real
    # Siempre exponer el token en la respuesta para pruebas (no se envÃ­a correo)
    generic_response["reset_token"] = token

    logger.info(f"âœ‰ï¸ Token de recuperaciÃ³n generado para tenant {tenant.id}")
    return ForgotPasswordResponse(**generic_response)


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    tags=["Tenants"],
    summary="Restablecer contraseÃ±a",
    description="Valida token de recuperaciÃ³n y actualiza la contraseÃ±a del tenant.",
    responses={
        200: {"description": "ContraseÃ±a actualizada", "model": MessageResponse},
        400: {"description": "Token invÃ¡lido o expirado", "model": ErrorResponse},
    },
)
async def reset_password(data: ResetPasswordRequest) -> MessageResponse:
    record = _get_valid_password_reset_token(data.token)
    tenant_id = record.get("tenant_id")

    tenant = tenant_repo.find_by_id(tenant_id)
    if not tenant:
        logger.warning("âš ï¸ Token apunta a tenant inexistente")
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "RESET_TOKEN_INVALID",
            "Token de recuperaciÃ³n invÃ¡lido",
        )

    new_hash = hash_password(data.new_password)
    tenant_repo.update(tenant_id, {"password_hash": new_hash})
    _mark_reset_token_used(record.get("id"))

    logger.info(f"ðŸ”’ ContraseÃ±a restablecida para tenant {tenant_id}")
    return MessageResponse(message="ContraseÃ±a actualizada")


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    tags=["Tenants"],
    summary="Cerrar sesiÃ³n de un tenant",
    description="Invalida el refresh token actual y revoca los access tokens activos al rotar la versiÃ³n de sesiÃ³n.",
    responses={
        200: {
            "description": "Logout exitoso",
        },
        401: {
            "description": "Refresh token invÃ¡lido",
            "model": ErrorResponse,
        },
        500: {
            "description": "Error interno del servidor",
            "model": ErrorResponse,
        },
    },
)
async def logout_tenant(data: TenantLogoutRequest, request: Request) -> dict:
    """Revoca la sesiÃ³n actual usando el refresh token enviado."""
    try:
        # Validar access token del header para confirmar sesiÃ³n activa
        try:
            # Acepta 'authorization' o 'Authorization' para tolerar clientes que no normalizan
            auth_header = request.headers.get("authorization") or request.headers.get(
                "Authorization"
            )
            access_token = _extract_bearer_token(auth_header)
            access_payload = jwt.decode(access_token, JWT_SECRET, algorithms=[JWT_ALG])
        except jwt.ExpiredSignatureError:
            raise _error(
                status.HTTP_401_UNAUTHORIZED,
                "ACCESS_TOKEN_EXPIRED",
                "Access token expirado",
            )
        except jwt.InvalidTokenError:
            raise _error(
                status.HTTP_401_UNAUTHORIZED,
                "ACCESS_TOKEN_INVALID",
                "Access token invÃ¡lido",
            )

        if access_payload.get("type") != "access":
            raise _error(
                status.HTTP_401_UNAUTHORIZED,
                "ACCESS_TOKEN_INVALID",
                "Access token invÃ¡lido",
            )

        try:
            payload = jwt.decode(
                data.refresh_token, JWT_REFRESH_SECRET, algorithms=[JWT_ALG]
            )
        except jwt.ExpiredSignatureError:
            logger.warning("âš ï¸ Refresh token expirado en logout")
            raise _error(
                status.HTTP_401_UNAUTHORIZED,
                "REFRESH_TOKEN_EXPIRED",
                "Refresh token expirado",
            )
        except jwt.InvalidTokenError:
            logger.warning("âš ï¸ Refresh token invÃ¡lido en logout")
            raise _error(
                status.HTTP_401_UNAUTHORIZED,
                "REFRESH_TOKEN_INVALID",
                "Refresh token invÃ¡lido",
            )

        if payload.get("type") != "refresh":
            logger.warning("âš ï¸ Token enviado a logout no es refresh")
            raise _error(
                status.HTTP_401_UNAUTHORIZED,
                "REFRESH_TOKEN_INVALID",
                "Refresh token invÃ¡lido",
            )

        tenant_id = payload.get("sub")
        email = payload.get("email")
        if not tenant_id or not email:
            logger.warning("âš ï¸ Logout sin datos suficientes en token")
            raise _error(
                status.HTTP_401_UNAUTHORIZED,
                "REFRESH_TOKEN_INVALID",
                "Refresh token invÃ¡lido",
            )

        tenant = tenant_repo.find_by_id(tenant_id)
        if not tenant:
            logger.warning("âš ï¸ Tenant no encontrado durante logout")
            raise _error(
                status.HTTP_401_UNAUTHORIZED,
                "REFRESH_TOKEN_INVALID",
                "Refresh token invÃ¡lido",
            )

        if tenant.email.lower() != email.lower():
            logger.warning("âš ï¸ Logout con token que no corresponde al tenant")
            raise _error(
                status.HTTP_401_UNAUTHORIZED,
                "REFRESH_TOKEN_INVALID",
                "Refresh token invÃ¡lido",
            )

        if access_payload.get("sub") != str(tenant.id):
            logger.warning("âš ï¸ Access token no corresponde al tenant del refresh")
            raise _error(
                status.HTTP_401_UNAUTHORIZED,
                "ACCESS_TOKEN_INVALID",
                "Access token invÃ¡lido",
            )

        # Rotar versiÃ³n para invalidar access/refresh anteriores
        bump_session_version(str(tenant.id))

        logger.info(
            "ðŸšª Logout exitoso",
            extra={
                "event": "tenant_logout",
                "tenant_id": str(tenant.id),
                "email": tenant.email,
                "ip": request.client.host if request.client else None,
            },
        )

        return {"detail": "Logout exitoso"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"âŒ Error inesperado en logout: {e}")
        raise _error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "INTERNAL_SERVER_ERROR",
            "Error interno del servidor",
        )


from src.models import Tenant
from src.schemas.tenant_schemas import TenantPlanEnum
from src.repositories.tenant_repository import tenant_repo
from src.core.logger import logger
from src.core.plans import get_plan_limits
from src.core.database import SupabaseClient, get_db
from src.services.tenant_service import invalidate_cache

# ============================================
# CONFIGURACIÃ“N DE SEGURIDAD
# ============================================

# Configurar bcrypt para hashing de contraseÃ±as
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,  # NÃºmero de rounds para bcrypt (mÃ¡s caro = mÃ¡s seguro)
)

JWT_SECRET = os.getenv("JWT_SECRET")
JWT_REFRESH_SECRET = os.getenv("JWT_REFRESH_SECRET")
if not JWT_SECRET or not JWT_REFRESH_SECRET:
    raise RuntimeError(
        "JWT_SECRET y JWT_REFRESH_SECRET deben estar configurados en entorno"
    )
JWT_ALG = "HS256"
ACCESS_EXPIRES_SECONDS = int(os.getenv("JWT_ACCESS_EXPIRES", "900"))  # 15 minutos
REFRESH_EXPIRES_SECONDS = int(os.getenv("JWT_REFRESH_EXPIRES", "604800"))  # 7 dÃ­as
RESET_TOKEN_EXPIRES_MINUTES = int(os.getenv("PASSWORD_RESET_EXPIRES_MINUTES", "30"))
RESET_TOKEN_TABLE = "password_reset_tokens"

# Rate limiting / lockout en login
FAILED_WINDOW_SECONDS = 900  # ventana de 15 min para contar intentos
LOCKOUT_SECONDS = 900  # bloqueo 15 min
MAX_FAILED_ATTEMPTS = 5
_failed_logins: Dict[str, List[float]] = {}
_refresh_attempts: Dict[str, List[float]] = {}
_session_version: Dict[str, int] = {}


def _extract_bearer_token(authorization: str | None) -> str:
    # Si el header no viene o estÃ¡ vacÃ­o, devolvemos error claro
    if not authorization:
        raise _error(
            status.HTTP_401_UNAUTHORIZED,
            "ACCESS_TOKEN_REQUIRED",
            "Authorization bearer token requerido",
        )

    if not authorization.lower().startswith("bearer "):
        raise _error(
            status.HTTP_401_UNAUTHORIZED,
            "ACCESS_TOKEN_REQUIRED",
            "Authorization bearer token requerido",
        )

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise _error(
            status.HTTP_401_UNAUTHORIZED,
            "ACCESS_TOKEN_REQUIRED",
            "Authorization bearer token requerido",
        )
    return token


def normalize_whatsapp_phone(phone: str | None) -> str | None:
    """
    Normaliza un nÃºmero de WhatsApp removiendo espacios, guiones, parÃ©ntesis
    y estandarizando el formato internacional.

    Ejemplos:
    - "+54 9 11 1234-5678" â†’ "+5491112345678"
    - "(54) 911 123 4567" â†’ "+549111234567"
    - "5491112345678" â†’ "+5491112345678"
    """
    if phone is None:
        return None

    import re

    # Remover todos los caracteres no numÃ©ricos excepto el +
    cleaned = re.sub(r"[^\d+]", "", phone.strip())

    # Si no tiene +, agregarlo al inicio (asumiendo cÃ³digo de paÃ­s)
    if not cleaned.startswith("+"):
        cleaned = "+" + cleaned

    return cleaned


def hash_password(password: str) -> str:
    """
    Hashea una contraseÃ±a usando bcrypt. Bcrypt admite hasta 72 bytes.
    """
    if len(password) > 72:
        raise ValueError(
            "La contraseÃ±a no puede exceder 72 caracteres (lÃ­mite de bcrypt)"
        )
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifica una contraseÃ±a contra su hash bcrypt

    Args:
        plain_password: ContraseÃ±a en texto plano
        hashed_password: Hash bcrypt almacenado

    Returns:
        True si coinciden, False si no
    """
    return pwd_context.verify(plain_password, hashed_password)


def _error(status_code: int, error_code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error_code": error_code, "message": message},
        headers={"X-Error-Code": error_code},
    )


def _is_dev() -> bool:
    env = (os.getenv("APP_ENV") or "").lower()
    debug = os.getenv("DEBUG") == "1"
    return env in ("dev", "development") or debug


def _create_password_reset_token(tenant_id: str) -> str:
    token = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=RESET_TOKEN_EXPIRES_MINUTES
    )

    tenant_repo.client.table(RESET_TOKEN_TABLE).insert(
        {
            "tenant_id": tenant_id,
            "token": token,
            "expires_at": expires_at.isoformat(),
            "used": False,
        }
    ).execute()

    return token


def _parse_dt(dt: str) -> datetime:
    # Maneja formatos con Z o con offset
    if dt.endswith("Z"):
        dt = dt.replace("Z", "+00:00")
    d = datetime.fromisoformat(dt)
    if d.tzinfo is None:
        # Forzar zona UTC si no tiene
        d = d.replace(tzinfo=timezone.utc)
    return d


def _get_valid_password_reset_token(token: str) -> dict:
    res = (
        tenant_repo.client.table(RESET_TOKEN_TABLE)
        .select("*")
        .eq("token", token)
        .eq("used", False)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not res.data:
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "RESET_TOKEN_INVALID",
            "Token de recuperaciÃ³n invÃ¡lido",
        )

    record = res.data[0]
    expires_at = _parse_dt(record["expires_at"])
    if expires_at <= datetime.now(timezone.utc):
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "RESET_TOKEN_EXPIRED",
            "Token de recuperaciÃ³n expirado",
        )

    return record


def _mark_reset_token_used(token_id: str) -> None:
    tenant_repo.client.table(RESET_TOKEN_TABLE).update({"used": True}).eq(
        "id", token_id
    ).execute()


def _api_key_hash(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _get_api_keys(config: dict | None) -> list:
    if not config:
        return []
    return list(config.get("api_keys", []))


def _save_api_keys(tenant_id: str, tenant_config: dict | None, api_keys: list) -> None:
    new_config = dict(tenant_config or {})
    new_config["api_keys"] = api_keys
    tenant_repo.update(tenant_id, {"config": new_config})


def create_token(
    sub: str, secret: str, expires_in: int, token_type: str, extra: dict | None = None
) -> str:
    payload = {
        "sub": sub,
        "type": token_type,
        "exp": int(time.time()) + expires_in,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, secret, algorithm=JWT_ALG)


def is_locked(email: str) -> bool:
    now = time.time()
    attempts = _failed_logins.get(email, [])
    attempts = [t for t in attempts if now - t <= LOCKOUT_SECONDS]
    _failed_logins[email] = attempts
    return (
        len(attempts) >= MAX_FAILED_ATTEMPTS and (now - attempts[-1]) <= LOCKOUT_SECONDS
    )


def record_failed(email: str) -> None:
    now = time.time()
    attempts = _failed_logins.get(email, [])
    attempts = [t for t in attempts if now - t <= FAILED_WINDOW_SECONDS]
    attempts.append(now)
    _failed_logins[email] = attempts


def record_refresh(email: str) -> None:
    now = time.time()
    attempts = _refresh_attempts.get(email, [])
    attempts = [t for t in attempts if now - t <= 60]
    attempts.append(now)
    _refresh_attempts[email] = attempts


def is_refresh_limited(email: str, limit: int = 30) -> bool:
    now = time.time()
    attempts = _refresh_attempts.get(email, [])
    attempts = [t for t in attempts if now - t <= 60]
    _refresh_attempts[email] = attempts
    return len(attempts) >= limit


def bump_session_version(tenant_id: str) -> int:
    ver = int(time.time())
    _session_version[tenant_id] = ver
    return ver


def current_session_version(tenant_id: str) -> int | None:
    return _session_version.get(tenant_id)


@router.get(
    "/{tenant_id}",
    response_model=TenantResponse,
    tags=["Management"],
    summary="Obtener datos del tenant",
)
async def get_tenant(tenant_id: str) -> TenantResponse:
    tenant = tenant_repo.find_by_id(tenant_id)
    if not tenant:
        raise _error(
            status.HTTP_404_NOT_FOUND, "TENANT_NOT_FOUND", "Tenant no encontrado"
        )
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        email=tenant.email,
        slug=tenant.slug,
        is_active=tenant.is_active,
        plan=tenant.plan,
        max_products=tenant.max_products,
        max_conversations=tenant.max_conversations,
        whatsapp_phone_number=tenant.whatsapp_phone_number,
        whatsapp_phone_id=tenant.whatsapp_phone_id,
        whatsapp_enabled=tenant.whatsapp_enabled,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
    )


@router.put(
    "/{tenant_id}",
    response_model=TenantResponse,
    status_code=status.HTTP_200_OK,
    tags=["Management"],
    summary="Actualizar informaciÃ³n del tenant",
    description="Actualiza campos bÃ¡sicos del tenant (name, email, slug, plan, whatsapp).",
    responses={
        200: {"description": "Tenant actualizado", "model": TenantResponse},
        400: {
            "description": "ValidaciÃ³n o formato incorrecto",
            "model": ErrorResponse,
        },
        404: {"description": "Tenant no encontrado", "model": ErrorResponse},
        409: {"description": "Conflicto de unicidad", "model": ErrorResponse},
    },
)
async def update_tenant(tenant_id: str, data: TenantUpdateRequest) -> TenantResponse:
    tenant = tenant_repo.find_by_id(tenant_id)
    if not tenant:
        raise _error(
            status.HTTP_404_NOT_FOUND, "TENANT_NOT_FOUND", "Tenant no encontrado"
        )

    update_data: dict = {}

    if data.name is not None:
        update_data["name"] = data.name.strip()

    if data.email is not None:
        email_normalized = data.email.lower().strip()
        if email_normalized != tenant.email.lower() and tenant_repo.check_email_exists(
            email_normalized
        ):
            raise _error(
                status.HTTP_409_CONFLICT,
                "EMAIL_ALREADY_EXISTS",
                f"El email '{email_normalized}' ya estÃ¡ registrado",
            )
        update_data["email"] = email_normalized

    if data.slug is not None:
        slug_normalized = data.slug.lower().strip()
        if slug_normalized != tenant.slug.lower() and tenant_repo.check_slug_exists(
            slug_normalized
        ):
            raise _error(
                status.HTTP_409_CONFLICT,
                "SLUG_ALREADY_EXISTS",
                f"El slug '{slug_normalized}' ya estÃ¡ en uso",
            )
        update_data["slug"] = slug_normalized

    if data.whatsapp_phone_number is not None:
        whatsapp_normalized = normalize_whatsapp_phone(data.whatsapp_phone_number)
        if (
            whatsapp_normalized != tenant.whatsapp_phone_number
            and tenant_repo.check_whatsapp_phone_exists(whatsapp_normalized)
        ):
            raise _error(
                status.HTTP_409_CONFLICT,
                "WHATSAPP_PHONE_ALREADY_EXISTS",
                "Este nÃºmero de WhatsApp ya estÃ¡ registrado",
            )
        update_data["whatsapp_phone_number"] = whatsapp_normalized

    if data.whatsapp_phone_id is not None:
        if (
            data.whatsapp_phone_id != tenant.whatsapp_phone_id
            and tenant_repo.check_whatsapp_phone_id_exists(data.whatsapp_phone_id)
        ):
            raise _error(
                status.HTTP_409_CONFLICT,
                "WHATSAPP_PHONE_ID_ALREADY_EXISTS",
                "Este WhatsApp Phone ID ya estÃ¡ registrado",
            )
        update_data["whatsapp_phone_id"] = data.whatsapp_phone_id

    if data.plan is not None:
        plan_selected = (
            data.plan.value
            if isinstance(data.plan, TenantPlanEnum)
            else str(data.plan).lower()
        )
        limits = get_plan_limits(plan_selected)
        update_data.update(
            {
                "plan": plan_selected,
                "max_products": limits["max_products"],
                "max_conversations": limits["max_conversations"],
            }
        )

    if not update_data:
        return TenantResponse(**tenant.dict())

    tenant_repo.update(tenant_id, update_data)
    invalidate_cache(tenant.slug)
    invalidate_cache(str(tenant.id))

    updated = tenant_repo.find_by_id(tenant_id)
    return TenantResponse(
        id=updated.id,
        name=updated.name,
        email=updated.email,
        slug=updated.slug,
        is_active=updated.is_active,
        plan=updated.plan,
        max_products=updated.max_products,
        max_conversations=updated.max_conversations,
        whatsapp_phone_number=updated.whatsapp_phone_number,
        whatsapp_phone_id=updated.whatsapp_phone_id,
        whatsapp_enabled=updated.whatsapp_enabled,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
    )


@router.post(
    "/{tenant_id}/api-keys",
    response_model=ApiKeyResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Management"],
    summary="Generar API key",
    description="Crea y devuelve una nueva API key para el tenant (solo visible al momento de creaciÃ³n).",
)
async def generate_api_key(
    tenant_id: str, payload: ApiKeyCreateRequest | None = None
) -> ApiKeyResponse:
    tenant = tenant_repo.find_by_id(tenant_id)
    if not tenant:
        raise _error(
            status.HTTP_404_NOT_FOUND, "TENANT_NOT_FOUND", "Tenant no encontrado"
        )

    raw_key = secrets.token_urlsafe(32)
    key_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    api_keys = _get_api_keys(tenant.config)
    api_keys.append(
        {
            "id": key_id,
            "name": payload.name if payload else None,
            "created_at": now.isoformat(),
            "revoked_at": None,
            "key_hash": _api_key_hash(raw_key),
        }
    )

    _save_api_keys(str(tenant.id), tenant.config, api_keys)

    return ApiKeyResponse(
        id=key_id,
        api_key=raw_key,
        name=payload.name if payload else None,
        created_at=now,
        revoked_at=None,
    )


@router.delete(
    "/{tenant_id}/api-keys/{key_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    tags=["Management"],
    summary="Revocar API key",
    description="Revoca una API key existente del tenant.",
)
async def revoke_api_key(tenant_id: str, key_id: str) -> MessageResponse:
    tenant = tenant_repo.find_by_id(tenant_id)
    if not tenant:
        raise _error(
            status.HTTP_404_NOT_FOUND, "TENANT_NOT_FOUND", "Tenant no encontrado"
        )

    api_keys = _get_api_keys(tenant.config)
    found = False
    for item in api_keys:
        if item.get("id") == key_id:
            found = True
            if item.get("revoked_at"):
                raise _error(
                    status.HTTP_400_BAD_REQUEST,
                    "API_KEY_ALREADY_REVOKED",
                    "API key ya estÃ¡ revocada",
                )
            item["revoked_at"] = datetime.now(timezone.utc).isoformat()
            break

    if not found:
        raise _error(
            status.HTTP_404_NOT_FOUND, "API_KEY_NOT_FOUND", "API key no encontrada"
        )

    _save_api_keys(str(tenant.id), tenant.config, api_keys)
    return MessageResponse(message="API key revocada")


def _billing_period_bounds(now: datetime) -> tuple[datetime, datetime]:
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    next_month = datetime(
        now.year + (1 if now.month == 12 else 0),
        1 if now.month == 12 else now.month + 1,
        1,
        tzinfo=timezone.utc,
    )
    end = next_month - timedelta(seconds=1)
    return start, end


def _count_tenant_products(db: SupabaseClient, tenant_id: str) -> int:
    result = (
        db.client.table("products")
        .select("id", count="exact")
        .eq("tenant_id", tenant_id)
        .limit(0)
        .execute()
    )
    return int(result.count or 0)


@router.get(
    "/{tenant_id}/usage",
    response_model=UsageResponse,
    status_code=status.HTTP_200_OK,
    tags=["Management"],
    summary="Ver uso actual",
    description="Devuelve uso de mensajes y almacenamiento del tenant para el perÃ­odo actual.",
)
async def get_usage(
    tenant_id: str,
    db: SupabaseClient = Depends(get_db),
) -> UsageResponse:
    tenant = tenant_repo.find_by_id(tenant_id)
    if not tenant:
        raise _error(
            status.HTTP_404_NOT_FOUND, "TENANT_NOT_FOUND", "Tenant no encontrado"
        )

    plan_limits = get_plan_limits(tenant.plan)
    messages_limit = plan_limits.get("max_conversations", tenant.max_conversations)
    products_limit = plan_limits.get("max_products", tenant.max_products)

    storage_limits_mb = {
        "starter": 1024,
        "growth": 5120,
        "enterprise": 20480,
    }

    storage_limit_mb = storage_limits_mb.get(
        str(tenant.plan), storage_limits_mb["starter"]
    )

    usage_config = (tenant.config or {}).get("usage", {})
    messages_used = int(usage_config.get("messages_used", 0))
    storage_used_mb = int(usage_config.get("storage_used_mb", 0))
    products_count = _count_tenant_products(db, str(tenant.id))

    now = datetime.now(timezone.utc)
    period_start, period_end = _billing_period_bounds(now)

    return UsageResponse(
        messages_used=messages_used,
        messages_limit=messages_limit,
        storage_used_mb=storage_used_mb,
        storage_limit_mb=storage_limit_mb,
        period_start=period_start,
        period_end=period_end,
        products_count=products_count,
        conversations_month_count=messages_used,
        limits=UsageLimits(
            products=int(products_limit),
            conversations_month=int(messages_limit),
        ),
    )


@router.get(
    "/{tenant_id}/billing",
    response_model=BillingInfoResponse,
    status_code=status.HTTP_200_OK,
    tags=["Management"],
    summary="InformaciÃ³n de facturaciÃ³n",
    description="Devuelve informaciÃ³n bÃ¡sica de facturaciÃ³n para el tenant.",
)
async def get_billing_info(tenant_id: str) -> BillingInfoResponse:
    tenant = tenant_repo.find_by_id(tenant_id)
    if not tenant:
        raise _error(
            status.HTTP_404_NOT_FOUND, "TENANT_NOT_FOUND", "Tenant no encontrado"
        )

    now = datetime.now(timezone.utc)
    period_start, period_end = _billing_period_bounds(now)

    return BillingInfoResponse(
        plan=str(tenant.plan),
        status="active" if tenant.is_active else "paused",
        cycle="monthly",
        next_billing_date=period_end,
        current_period_start=period_start,
        current_period_end=period_end,
    )


@router.post(
    "/register",
    response_model=TenantCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Tenants"],
    summary="Registrar un nuevo tenant",
    description="""
    Crea y registra un nuevo tenant en el sistema.
    
    Validaciones automÃ¡ticas:
    - Email debe ser Ãºnico y en formato vÃ¡lido
    - Slug debe ser Ãºnico y contener solo a-z, 0-9, guiones
    - ContraseÃ±a: mÃ­n 8 caracteres, 1 mayÃºscula, 1 nÃºmero, 1 carÃ¡cter especial
    - Nombre: entre 1 y 255 caracteres
    
    Respuesta:
    - Incluye todos los datos del tenant creado
    - NO incluye el password_hash (seguridad)
    - Status: 201 Created
    
    Errores:
    - 400: ValidaciÃ³n fallida (contraseÃ±a dÃ©bil, email invÃ¡lido, etc)
    - 409: Conflict - Email o slug ya existen
    - 500: Error interno del servidor
    """,
    responses={
        201: {
            "description": "Tenant creado exitosamente",
            "model": TenantCreatedResponse,
        },
        400: {
            "description": "Error de validaciÃ³n en los datos",
            "model": ErrorResponse,
        },
        409: {
            "description": "Conflict - Email, slug o nÃºmero de WhatsApp ya existen",
            "model": ErrorResponse,
        },
        500: {
            "description": "Error interno del servidor",
            "model": ErrorResponse,
        },
    },
)
async def register_tenant(data: TenantCreate) -> TenantCreatedResponse:
    """
    Registra un nuevo tenant

    Proceso:
    1. Valida datos con Pydantic (schemas)
    2. Verifica unicidad de email y slug
    3. Hashea la contraseÃ±a con bcrypt
    4. Crea el registro en la BD
    5. Devuelve respuesta sin incluir password_hash

    Args:
        data: Datos del tenant a crear (validado por TenantCreate schema)

    Returns:
        TenantCreatedResponse con los datos del tenant creado

    Raises:
        HTTPException 400: Si hay errores de validaciÃ³n
        HTTPException 409: Si email o slug ya existen
        HTTPException 500: Si hay error en la BD
    """

    try:
        # ============================================
        # PASO 1: NORMALIZAR DATOS
        # ============================================

        email_normalized = data.email.lower().strip()
        slug_normalized = data.slug.lower().strip()
        whatsapp_normalized = normalize_whatsapp_phone(data.whatsapp_phone_number)

        logger.debug(f"ðŸ“ Iniciando registro de tenant: {slug_normalized}")

        # ============================================
        # PASO 2: VERIFICAR UNICIDAD DE EMAIL
        # ============================================

        if tenant_repo.check_email_exists(email_normalized):
            logger.warning(
                f"âš ï¸  Intento de registrar email duplicado: {email_normalized}"
            )
            raise _error(
                status.HTTP_409_CONFLICT,
                "EMAIL_ALREADY_EXISTS",
                f"El email '{email_normalized}' ya estÃ¡ registrado en el sistema",
            )

        # ============================================
        # PASO 3: VERIFICAR UNICIDAD DE SLUG
        # ============================================

        if tenant_repo.check_slug_exists(slug_normalized):
            logger.warning(
                f"âš ï¸  Intento de registrar slug duplicado: {slug_normalized}"
            )
            raise _error(
                status.HTTP_409_CONFLICT,
                "SLUG_ALREADY_EXISTS",
                f"El slug '{slug_normalized}' ya estÃ¡ en uso",
            )
        # ============================================
        # PASO 3.1: VERIFICAR UNICIDAD DE WHATSAPP PHONE
        # ============================================
        if whatsapp_normalized and tenant_repo.check_whatsapp_phone_exists(
            whatsapp_normalized
        ):
            logger.warning(
                f"âš ï¸  Intento de registrar whatsapp_phone_number duplicado: {whatsapp_normalized}"
            )
            raise _error(
                status.HTTP_409_CONFLICT,
                "WHATSAPP_PHONE_ALREADY_EXISTS",
                "Este nÃºmero de WhatsApp ya estÃ¡ registrado",
            )

        # ============================================
        # PASO 3.2: VERIFICAR UNICIDAD DE WHATSAPP PHONE ID
        # ============================================
        if data.whatsapp_phone_id and tenant_repo.check_whatsapp_phone_id_exists(
            data.whatsapp_phone_id
        ):
            logger.warning(
                f"âš ï¸  Intento de registrar whatsapp_phone_id duplicado: {data.whatsapp_phone_id}"
            )
            raise _error(
                status.HTTP_409_CONFLICT,
                "WHATSAPP_PHONE_ID_ALREADY_EXISTS",
                "Este WhatsApp Phone ID ya estÃ¡ registrado",
            )

        # ============================================
        # PASO 4: HASHEAR CONTRASEÃ‘A
        # ============================================

        password_hash = hash_password(data.password)
        logger.debug(f"ðŸ” ContraseÃ±a hasheada con bcrypt (rounds=12)")

        # ============================================
        # PASO 5: CREAR OBJETO TENANT
        # ============================================

        plan_selected = (
            data.plan.value
            if isinstance(data.plan, TenantPlanEnum)
            else str(data.plan).lower()
        )
        limits = get_plan_limits(plan_selected)

        tenant_dict = {
            "name": data.name,
            "email": email_normalized,
            "password_hash": password_hash,
            "slug": slug_normalized,
            "is_active": True,
            "whatsapp_phone_number": whatsapp_normalized,
            "whatsapp_phone_id": data.whatsapp_phone_id,
            "whatsapp_enabled": False,  # Por defecto deshabilitado
            "plan": plan_selected,
            "max_products": limits["max_products"],
            "max_conversations": limits["max_conversations"],
        }

        tenant = Tenant(**tenant_dict)

        logger.debug(f"âœ“ Objeto Tenant creado: {tenant.slug}")

        # ============================================
        # PASO 6: GUARDAR EN BASE DE DATOS
        # ============================================

        created_tenant = tenant_repo.create(tenant_dict)

        logger.info(
            f"âœ… Tenant registrado exitosamente: {created_tenant.slug} (ID: {created_tenant.id})"
        )

        # ============================================
        # PASO 7: DEVOLVER RESPUESTA
        # ============================================
        # Nota: TenantCreatedResponse NO incluye password_hash automÃ¡ticamente

        response = TenantCreatedResponse(
            id=created_tenant.id,
            name=created_tenant.name,
            email=created_tenant.email,
            slug=created_tenant.slug,
            is_active=created_tenant.is_active,
            plan=created_tenant.plan,
            max_products=created_tenant.max_products,
            max_conversations=created_tenant.max_conversations,
            whatsapp_phone_number=created_tenant.whatsapp_phone_number,
            whatsapp_phone_id=created_tenant.whatsapp_phone_id,
            whatsapp_enabled=created_tenant.whatsapp_enabled,
            created_at=created_tenant.created_at,
            updated_at=created_tenant.updated_at,
        )

        return response

    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"âš ï¸  Error de validaciÃ³n: {str(e)}")
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
            f"Error de validaciÃ³n: {str(e)}",
        )


@router.post(
    "/login",
    response_model=TenantLoginResponse,
    status_code=status.HTTP_200_OK,
    tags=["Tenants"],
    summary="Autenticar un tenant (login)",
    description="Valida credenciales de tenant y devuelve sus datos pÃºblicos (sin password_hash).",
    responses={
        200: {
            "description": "Login exitoso",
            "model": TenantResponse,
        },
        401: {
            "description": "Credenciales invÃ¡lidas",
            "model": ErrorResponse,
        },
        403: {
            "description": "Tenant inactivo",
            "model": ErrorResponse,
        },
        500: {
            "description": "Error interno del servidor",
            "model": ErrorResponse,
        },
    },
)
async def login_tenant(
    data: TenantLoginRequest, request: Request
) -> TenantLoginResponse:
    """Login de tenant usando email y contraseÃ±a con tokens y bloqueo bÃ¡sico."""
    try:
        _ = request  # placeholder si se necesita IP para rate limiting futuro
        email_normalized = data.email.lower().strip()

        if is_locked(email_normalized):
            logger.warning(
                f"ðŸš« Login bloqueado por demasiados intentos: {email_normalized}"
            )
            raise _error(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "LOGIN_LOCKED",
                "Demasiados intentos fallidos. Intenta nuevamente en unos minutos.",
            )

        tenant = tenant_repo.find_by_email(email_normalized)
        if not tenant:
            logger.warning(
                f"âš ï¸  Login fallido: email no encontrado {email_normalized}"
            )
            record_failed(email_normalized)
            raise _error(
                status.HTTP_401_UNAUTHORIZED,
                "INVALID_CREDENTIALS",
                "Credenciales invÃ¡lidas",
            )

        if not tenant.is_active:
            logger.warning(
                f"âš ï¸  Login bloqueado: tenant inactivo {email_normalized}"
            )
            raise _error(
                status.HTTP_403_FORBIDDEN, "TENANT_INACTIVE", "Tenant inactivo"
            )

        if not verify_password(data.password, tenant.password_hash):
            logger.warning(
                f"âš ï¸  Login fallido: contraseÃ±a incorrecta {email_normalized}"
            )
            record_failed(email_normalized)
            raise _error(
                status.HTTP_401_UNAUTHORIZED,
                "INVALID_CREDENTIALS",
                "Credenciales invÃ¡lidas",
            )

        # Login exitoso: limpiar intentos
        _failed_logins[email_normalized] = []

        logger.info(f"âœ… Login exitoso para tenant: {tenant.slug}")

        session_ver = bump_session_version(str(tenant.id))

        access_token = create_token(
            sub=str(tenant.id),
            secret=JWT_SECRET,
            expires_in=ACCESS_EXPIRES_SECONDS,
            token_type="access",
            extra={"email": tenant.email, "plan": tenant.plan, "ver": session_ver},
        )

        refresh_token = create_token(
            sub=str(tenant.id),
            secret=JWT_REFRESH_SECRET,
            expires_in=REFRESH_EXPIRES_SECONDS,
            token_type="refresh",
            extra={"email": tenant.email, "plan": tenant.plan, "ver": session_ver},
        )

        tenant_response = TenantResponse(
            id=tenant.id,
            name=tenant.name,
            email=tenant.email,
            slug=tenant.slug,
            is_active=tenant.is_active,
            plan=tenant.plan,
            max_products=tenant.max_products,
            max_conversations=tenant.max_conversations,
            whatsapp_phone_number=tenant.whatsapp_phone_number,
            whatsapp_phone_id=tenant.whatsapp_phone_id,
            whatsapp_enabled=tenant.whatsapp_enabled,
            created_at=tenant.created_at,
            updated_at=tenant.updated_at,
        )

        return TenantLoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=ACCESS_EXPIRES_SECONDS,
            tenant=tenant_response,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"âŒ Error inesperado en login: {e}")
        raise _error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "INTERNAL_SERVER_ERROR",
            "Error interno del servidor",
        )
    except APIError as e:
        # Errores provenientes de Supabase/Postgrest
        details = e.details or e.message or str(e) or "Error de base de datos"
        lower = details.lower()
        if "whatsapp_phone_number" in lower:
            conflict_detail = "El nÃºmero de WhatsApp ya estÃ¡ registrado en el sistema"
            error_code = "WHATSAPP_PHONE_ALREADY_EXISTS"
        elif "slug" in lower:
            conflict_detail = "El slug ya estÃ¡ en uso"
            error_code = "SLUG_ALREADY_EXISTS"
        elif "email" in lower:
            conflict_detail = "El email ya estÃ¡ registrado en el sistema"
            error_code = "EMAIL_ALREADY_EXISTS"
        else:
            conflict_detail = "Conflicto de integridad en la base de datos"
            error_code = "INTEGRITY_ERROR"

        if e.code == "23505":
            logger.warning(f"âš ï¸  Error de integridad (duplicado): {details}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=conflict_detail,
                headers={"X-Error-Code": error_code},
            )

        logger.error(f"âŒ Error de base de datos al registrar tenant: {details}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al registrar el tenant. Por favor, intenta mÃ¡s tarde.",
            headers={"X-Error-Code": "INTERNAL_SERVER_ERROR"},
        )
    except Exception:
        logger.exception("âŒ Error inesperado al registrar tenant")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al registrar el tenant. Por favor, intenta mÃ¡s tarde.",
            headers={"X-Error-Code": "INTERNAL_SERVER_ERROR"},
        )
