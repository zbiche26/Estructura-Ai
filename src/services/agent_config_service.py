"""
Agent Config Service
====================
Carga la configuración del agente desde la tabla agent_config en Supabase.
Permite que cada tenant configure su propio agente desde el dashboard.

Columnas: id, tenant_id, nombre_agente, system_prompt, welcome_message,
          temperatura, idioma, created_at, updated_at, owner_phone

Usado por: src/http/app.py → handle_agent_reply()
"""

from typing import Optional, Dict, Any
from src.core.logger import logger


def get_agent_config(tenant_id: str) -> Dict[str, Any]:
    """
    Carga la configuración del agente para un tenant desde Supabase.

    Returns:
        Dict con la configuración del agente. Si no existe, retorna defaults.
    """
    try:
        from src.core.database import get_db

        db = get_db().client

        result = (
            db.table("agent_config")
            .select(
                "nombre_agente, system_prompt, welcome_message, "
                "temperatura, idioma, owner_phone"
            )
            .eq("tenant_id", tenant_id)
            .limit(1)
            .execute()
        )

        if result.data:
            config = result.data[0]
            logger.debug(
                f"[AGENT_CONFIG] Config cargada para tenant {tenant_id}: "
                f"agente={config.get('nombre_agente')}"
            )
            return config

        logger.debug(
            f"[AGENT_CONFIG] Sin config para tenant {tenant_id} — usando defaults"
        )
        return {}

    except Exception as e:
        logger.error(f"[AGENT_CONFIG] Error cargando config para {tenant_id}: {e}")
        return {}


def get_agent_name(config: Dict[str, Any]) -> str:
    """
    Retorna el nombre del agente desde la config.
    Fallback: 'Asistente'
    """
    return config.get("nombre_agente") or "Asistente"


def build_system_prompt_from_config(
    config: Dict[str, Any],
    context_text: str = "",
) -> Optional[str]:
    """
    Construye el system prompt desde agent_config si el dueño lo configuró.

    - Si tiene system_prompt en BD → lo usa, reemplazando placeholders
    - Si NO tiene → retorna None (el RAG construye el default con nombre_agente)

    Placeholders soportados en el system_prompt del dueño:
        {catalogo}      → se reemplaza con el catálogo formateado
        {nombre_agente} → se reemplaza con el nombre del agente
    """
    system_prompt = config.get("system_prompt")

    if not system_prompt:
        return None

    # Reemplazar {catalogo} con el catálogo formateado
    if "{catalogo}" in system_prompt and context_text:
        system_prompt = system_prompt.replace("{catalogo}", context_text)

    # Reemplazar {nombre_agente} con el nombre real
    nombre_agente = get_agent_name(config)
    if "{nombre_agente}" in system_prompt:
        system_prompt = system_prompt.replace("{nombre_agente}", nombre_agente)

    return system_prompt