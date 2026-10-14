"""
Servicio de Tenants
===================

Este servicio se encarga de la lógica de negocio relacionada con la identificación
y carga de tenants. Actúa como puente entre la capa de datos (Supabase) y
el núcleo de la aplicación (TenantContext).

Responsabilidades:
- Buscar tenants por ID, Slug o número de WhatsApp.
- Cargar y validar su configuración.
- Construir el objeto TenantContext inmutable.
- Caché en memoria con TTL para evitar queries repetitivas.
"""

import os
import re
import time
import threading
from typing import Optional, Dict, List
from src.core.database import SupabaseClient
from src.core.tenant_context import TenantContext
from src.core.logger import logger

# ============================================
# CACHÉ DE TENANTS (Thread-Safe, con TTL)
# ============================================

_CACHE_TTL_SECONDS = 300  # 5 minutos
_cache: Dict[str, tuple] = {}  # key → (TenantContext, timestamp)
_cache_lock = threading.Lock()

UUID_REGEX = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _cache_get(key: str) -> Optional[TenantContext]:
    """Obtiene del caché si no ha expirado."""
    with _cache_lock:
        entry = _cache.get(key)
        if entry:
            ctx, ts = entry
            if time.time() - ts < _CACHE_TTL_SECONDS:
                return ctx
            del _cache[key]
    return None


def _cache_set(key: str, ctx: TenantContext) -> None:
    """Guarda en caché con timestamp."""
    with _cache_lock:
        _cache[key] = (ctx, time.time())


def invalidate_cache(key: Optional[str] = None) -> None:
    """
    Invalida el caché de un tenant o de todos.

    Args:
        key: Slug, ID o phone. Si es None, limpia todo el caché.
    """
    with _cache_lock:
        if key:
            _cache.pop(key, None)
        else:
            _cache.clear()
    logger.debug(f" Caché de tenants invalidado: {key or 'ALL'}")


# ============================================
# FUNCIONES PRINCIPALES
# ============================================


def _build_tenant_context(tenant_data: dict) -> Optional[TenantContext]:
    """
    Construye un TenantContext a partir de los datos crudos de Supabase.
    Inyecta configuración de WhatsApp y token seguro desde env.
    """
    if not tenant_data.get("is_active", True):
        logger.warning(f"Tenant inactivo: {tenant_data.get('slug')}")
        return None

    config = tenant_data.get("config", {}) or {}
    config["slug"] = tenant_data.get("slug", "")

    # ✅ FIX: Siempre inyectar whatsapp_enabled (true o false)
    config["whatsapp_enabled"] = bool(tenant_data.get("whatsapp_enabled", False))
    if tenant_data.get("whatsapp_enabled"):
        config["whatsapp_phone_number"] = tenant_data.get("whatsapp_phone_number")
        config["whatsapp_phone_id"] = tenant_data.get("whatsapp_phone_id")

        # separar verify_token (handshake) y webhook_secret (firma HMAC)
        verify_token = tenant_data.get("whatsapp_verify_token") or config.get(
            "whatsapp_verify_token"
        )
        webhook_secret = tenant_data.get("whatsapp_webhook_secret") or config.get(
            "whatsapp_webhook_secret"
        )

        # si solo hay webhook_secret, úsalo también como verify_token
        if not verify_token and webhook_secret:
            verify_token = webhook_secret

        if verify_token:
            config["whatsapp_verify_token"] = verify_token
        if webhook_secret:
            config["whatsapp_webhook_secret"] = webhook_secret

        config["whatsapp_enabled"] = True

        # Token seguro desde variable de entorno. Acepta guiones o guiones bajos.
        slug_raw = tenant_data.get("slug", "")
        slug_env = slug_raw.upper().replace("-", "_")
        env_token = os.getenv(f"WHATSAPP_TOKEN_{slug_env}")
        if not env_token and slug_raw:
            env_token = os.getenv(f"WHATSAPP_TOKEN_{slug_raw}")

        if env_token:
            config["whatsapp_token"] = env_token
        else:
            logger.warning(f"Token de entorno no encontrado para tenant {slug_env}")

    return TenantContext(
        tenant_id=tenant_data["id"],
        tenant_name=tenant_data["name"],
        plan=tenant_data.get("plan", "free"),
        features_enabled=config.get("features_enabled", []),
        config=config,
    )


def load_tenant_context(tenant_identifier: str) -> Optional[TenantContext]:
    """
    Carga el contexto del tenant desde caché o Supabase.

    Args:
        tenant_identifier: Puede ser ID (UUID) o Slug del tenant.

    Returns:
        TenantContext configurado o None si no existe/inactivo.
    """
    # 1. Buscar en caché
    cached = _cache_get(tenant_identifier)
    if cached:
        logger.debug(f"[CACHE HIT] Tenant: {tenant_identifier}")
        return cached

    # 2. Consultar Supabase
    db = SupabaseClient()

    try:
        # Buscar por slug primero
        response = (
            db.client.table("tenants")
            .select("*")
            .eq("slug", tenant_identifier)
            .execute()
        )
        logger.info(
            f"[DEBUG] Resultado búsqueda por slug='{tenant_identifier}': {response.data}"
        )

        # Si no encontró, intentar por UUID
        if not response.data and UUID_REGEX.match(tenant_identifier):
            response = (
                db.client.table("tenants")
                .select("*")
                .eq("id", tenant_identifier)
                .execute()
            )
            logger.info(
                f"[DEBUG] Resultado búsqueda por id='{tenant_identifier}': {response.data}"
            )

        if not response.data:
            logger.warning(f"Tenant no encontrado: {tenant_identifier}")
            env = (os.getenv("APP_ENV") or "").lower()
            if env in ("dev", "development") or os.getenv("DEBUG") == "true":
                logger.warning(f"[DEV] Usando demo tenant para '{tenant_identifier}'")
                from src.core.tenant_context import TenantContext

                return TenantContext(
                    tenant_id=tenant_identifier,
                    tenant_name=f"Tenant {tenant_identifier} (dev)",
                    plan="free",
                    features_enabled=[
                        "onboarding",
                        "billing",
                        "conversations",
                        "training",
                    ],
                    config={"slug": tenant_identifier},
                )
            return None

        ctx = _build_tenant_context(response.data[0])
        if ctx:
            _cache_set(tenant_identifier, ctx)
            # También cachear por slug si buscamos por ID
            slug = response.data[0].get("slug", "")
            if slug and slug != tenant_identifier:
                _cache_set(slug, ctx)
        return ctx

    except Exception as e:
        logger.error(f"Error cargando tenant context para {tenant_identifier}: {e}")
        return None


def get_tenant_by_phone(phone_number: str) -> Optional[TenantContext]:
    """
    Obtiene el contexto de un tenant por su número de WhatsApp Business.
    Útil cuando Meta envía un webhook y necesitas saber a qué tenant pertenece
    basándote en el número del negocio.

    Args:
        phone_number: Número de WhatsApp del negocio (ej: +573001234567).

    Returns:
        TenantContext o None si no hay tenant con ese número.
    """
    # 1. Buscar en caché
    cache_key = f"phone:{phone_number}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    # 2. Consultar Supabase
    db = SupabaseClient()

    try:
        response = (
            db.client.table("tenants")
            .select("*")
            .eq("whatsapp_phone_number", phone_number)
            .eq("whatsapp_enabled", True)
            .execute()
        )

        if not response.data:
            logger.warning(f"Tenant no encontrado para phone: {phone_number}")
            return None

        ctx = _build_tenant_context(response.data[0])
        if ctx:
            _cache_set(cache_key, ctx)
            _cache_set(response.data[0].get("slug", ""), ctx)
        return ctx

    except Exception as e:
        logger.error(f"Error buscando tenant por phone {phone_number}: {e}")
        return None


def get_all_active_tenants() -> List[TenantContext]:
    """
    Carga todos los tenants activos con WhatsApp habilitado.

    Returns:
        Lista de TenantContext de tenants activos.
    """
    db = SupabaseClient()

    try:
        response = (
            db.client.table("tenants")
            .select("*")
            .eq("is_active", True)
            .eq("whatsapp_enabled", True)
            .execute()
        )

        if not response.data:
            logger.warning(
                "No se encontraron tenants activos con WhatsApp (consulta vacía)"
            )
            return []

        contexts = []
        for tenant_data in response.data:
            ctx = _build_tenant_context(tenant_data)
            if ctx:
                contexts.append(ctx)
                _cache_set(tenant_data.get("slug", ""), ctx)

        logger.info(f"Cargados {len(contexts)} tenants activos con WhatsApp")
        return contexts

    except Exception as e:
        logger.error(f"Error cargando tenants activos: {e}")
        return []


def print_all_active_tenants():
    """
    Imprime por consola todos los tenants activos con WhatsApp habilitado.
    """
    tenants = get_all_active_tenants()
    print(f"Total activos: {len(tenants)}")
    for t in tenants:
        print(
            f"- {t.tenant_id} | {t.tenant_name} | {t.config.get('slug')} | {t.config.get('whatsapp_phone_number')}"
        )
