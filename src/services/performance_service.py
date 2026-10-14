import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from src.repositories.conversation_repository import ConversationRepository
from src.repositories.error_log_repository import ErrorLogRepository
from src.core.database import SupabaseClient
from src.core.logger import logger

# Límites configurables (origen único de verdad)
PERFORMANCE_WINDOW_MINUTES = int(os.getenv("PERFORMANCE_WINDOW_MINUTES", 60))
PERFORMANCE_MAX_PAIRS = int(os.getenv("PERFORMANCE_MAX_PAIRS", 1000))

# Uptime: preferimos APP_START_TIME (mismo valor para todos los workers del contenedor)
_env_start = os.getenv("APP_START_TIME")
_parsed_env_start = None
if _env_start:
    try:
        _parsed_env_start = datetime.fromisoformat(_env_start)
    except Exception:
        _parsed_env_start = None

# Momento en que se cargó el proceso (fallback per worker)
PROCESS_START_TIME = datetime.now(timezone.utc)
START_TIME = _parsed_env_start or PROCESS_START_TIME
START_SOURCE = "env" if _parsed_env_start else "process"


def get_agent_response_time(
    *,
    tenant_id: str,
    window_minutes: int,
    db: SupabaseClient,
) -> Dict[str, Any]:
    """Promedio de tiempo de respuesta del agente basado en conversaciones recientes."""
    # Validación estricta de parámetros
    if not (1 <= window_minutes <= 720):
        logger.warning(f"window_minutes fuera de rango: {window_minutes}")
        raise ValueError("window_minutes fuera de rango permitido (1-720)")
    repo = ConversationRepository(client=db.client)
    safe_window = window_minutes
    max_pairs = min(safe_window * 10, PERFORMANCE_MAX_PAIRS)
    try:
        avg_seconds = repo.get_average_response_time(
            window_minutes=safe_window,
            max_pairs=max_pairs,
        )
        if avg_seconds is None:
            avg_seconds = None
    except Exception as exc:
        logger.error(f"Agent response time error: {type(exc).__name__}")
        avg_seconds = None
    return {
        "tenant_id": tenant_id,
        "avg_response_time_seconds": avg_seconds,
        "window_minutes": safe_window,
        "calculated_at": datetime.now(timezone.utc).isoformat(),
    }


def get_agent_uptime() -> Dict[str, Any]:
    """Retorna uptime; usa APP_START_TIME si existe para homogeneizar workers."""
    now = datetime.now(timezone.utc)
    uptime_seconds = int((now - START_TIME).total_seconds())
    return {
        "uptime_seconds": uptime_seconds,
        "started_at": START_TIME.isoformat(),
        "started_source": START_SOURCE,
        "process_id": os.getpid(),
        "calculated_at": now.isoformat(),
    }


def get_error_logs(
    *,
    tenant_id: str,
    limit: int,
    db: SupabaseClient,
) -> Dict[str, Any]:
    # Validación estricta de parámetros
    if not (1 <= limit <= 100):
        logger.warning(f"limit fuera de rango: {limit}")
        raise ValueError("limit fuera de rango permitido (1-100)")
    repo = ErrorLogRepository(client=db.client)
    try:
        # Timeout simulado/documentado (Supabase-py no soporta timeout nativo, pero aquí se documenta)
        # items = repo.get_recent_errors(tenant_id=tenant_id, limit=limit, timeout=3)
        items = repo.get_recent_errors(tenant_id=tenant_id, limit=limit)
    except Exception as exc:
        logger.error(f"Error logs fetch error: {type(exc).__name__}")
        items = []
    return {
        "tenant_id": tenant_id,
        "items": items,
        "limit": limit,
        "calculated_at": datetime.now(timezone.utc).isoformat(),
    }
