"""
Handler del evento `agent.reply.requested`.

Consume el evento publicado por WhatsAppHandler._dispatch_agent_events,
genera la respuesta con el agente y la envía por WhatsApp.

Extraído de src/http/app.py (antes vivía como función anidada dentro de
create_app().startup_event) para que sea importable y testeable de forma
aislada — necesario para el test de concurrencia del guard de idempotencia
(ver tests/test_agent_reply_handler.py).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from src.core.database import get_db
from src.core.event_bus import Event
from src.core.logger import logger
from src.core.process_identity import get_process_identity
from src.core.tenant_context import TenantContextManager
from src.core.whatsapp_handler import WhatsAppHandler
from src.repositories.message_repo import MessageRepo
from src.services.agent_config_service import get_agent_config, get_agent_name
from src.services.agent_orchestrator import create_agent_orchestrator
from src.services.tenant_service import load_tenant_context

_UUID_RE = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


def _resolve_conversation_id(
    *,
    tenant_id: str,
    raw_conv_id: str,
    customer_phone: str,
    customer_name: str,
    db_client,
) -> str:
    if not customer_phone:
        return raw_conv_id

    now = datetime.now(timezone.utc).isoformat()
    try:
        existing = (
            db_client.table("conversations")
            .select("id")
            .eq("tenant_id", tenant_id)
            .eq("phone", customer_phone)
            .eq("status", "ACTIVE")
            .limit(1)
            .execute()
        )
        if existing.data:
            return str(existing.data[0]["id"])
        result = (
            db_client.table("conversations")
            .insert({
                "tenant_id": tenant_id,
                "phone": customer_phone,
                "contact_name": customer_name or "",
                "status": "ACTIVE",
                "unread_count": 0,
                "last_message_at": now,
                "created_at": now,
                "updated_at": now,
            })
            .execute()
        )
        if result.data:
            return str(result.data[0]["id"])
    except Exception as exc:
        logger.error(f"[AGENT] _resolve_conversation_id error: {exc}")
    return raw_conv_id


def _claim_reply(whatsapp_message_id: str, db_client) -> bool:
    """
    Reclama atómicamente el derecho a responder a este mensaje.

    Usa un UPDATE condicional (WHERE replied_at IS NULL) sobre message_jobs
    en vez de un lock en memoria: sobrevive restarts/redeploys y es correcto
    incluso si en el futuro hay más de una réplica del servicio corriendo.

    Devuelve True si esta llamada ganó el reclamo (debe continuar y enviar
    la respuesta), False si alguien ya lo reclamó antes (debe abortar).
    """
    if not whatsapp_message_id:
        # Sin id no hay forma de deduplicar — dejar pasar para no bloquear
        # flujos legítimos (p.ej. mensajes sintéticos sin wamid real).
        return True

    result = (
        db_client.table("message_jobs")
        .update(
            {
                "replied_at": datetime.now(timezone.utc).isoformat(),
                "replied_by": get_process_identity(),
            }
        )
        .eq("whatsapp_message_id", whatsapp_message_id)
        .is_("replied_at", "null")
        .execute()
    )
    return bool(result.data)


async def handle_agent_reply(event: Event) -> None:
    try:
        data: dict[str, Any] = event.data
        tenant_slug = event.metadata.get("tenant_slug", "")

        whatsapp_message_id = data.get("message_id", "")
        if not _claim_reply(whatsapp_message_id, get_db().client):
            logger.warning(
                f"[GUARD] Envío duplicado bloqueado para "
                f"whatsapp_message_id={whatsapp_message_id}"
            )
            return

        # Cargar contexto del tenant
        tenant = load_tenant_context(tenant_slug)
        if not tenant:
            logger.error(f"[AGENT] Tenant no encontrado: {tenant_slug}")
            return

        TenantContextManager.set_current(tenant)

        raw_conv_id = data.get("conversation_id", "")
        if raw_conv_id.startswith("wa_"):
            resolved_id = _resolve_conversation_id(
                tenant_id=tenant.tenant_id,
                raw_conv_id=raw_conv_id,
                customer_phone=data.get("customer_phone", ""),
                customer_name=data.get("customer_name", ""),
                db_client=get_db().client,
            )
            logger.info(f"[AGENT] conversation_id traducido: {raw_conv_id} → {resolved_id}")
            data = dict(data)
            data["conversation_id"] = resolved_id

        logger.info(
            f"[AGENT] Procesando mensaje de {data.get('customer_phone')} "
            f"en conversación {data.get('conversation_id')}"
        )

        # ✅ C03: Cargar configuración del agente desde agent_config
        agent_config = get_agent_config(tenant.tenant_id)
        system_prompt = agent_config.get("system_prompt") or None
        temperatura = float(agent_config.get("temperatura") or 0.7)

        # ✅ C02: Nombre del agente para el prompt por defecto
        nombre_agente = get_agent_name(agent_config)

        if system_prompt:
            logger.debug(
                f"[AGENT] Usando system_prompt personalizado — agente: {nombre_agente}"
            )
        else:
            logger.debug(
                f"[AGENT] Usando system_prompt default — agente: {nombre_agente}"
            )

        # Crear orquestador del agente
        orchestrator = create_agent_orchestrator(
            tenant_id=tenant.tenant_id,
            use_mock_llm=False,
            use_local_embeddings=False,
        )

        # Procesar mensaje y generar respuesta
        result = await orchestrator.process_message(
            message=data["input_text"],
            conversation_id=data["conversation_id"],
            tenant_id=tenant.tenant_id,
            system_prompt=system_prompt,       # ✅ C03
            temperatura=temperatura,            # ✅ C03
            customer_phone=data.get("customer_phone"),  # ✅ C06
            customer_name=data.get("customer_name"),    # ✅ C06
            nombre_agente=nombre_agente,        # ✅ C02
        )

        # Enviar respuesta por WhatsApp
        whatsapp = WhatsAppHandler()
        whatsapp.send_message(
            to=data["customer_phone"], message=result["message"]
        )

        # Persistir respuesta del bot en historial de conversación
        conv_id = data.get("conversation_id", "")
        if re.match(_UUID_RE, conv_id, re.IGNORECASE):
            try:
                msg_repo = MessageRepo(client=get_db().client)
                msg_repo.persist_bot_reply_message(
                    tenant_id=tenant.tenant_id,
                    conversation_id=conv_id,
                    content=result["message"],
                )
            except Exception as persist_err:
                logger.warning(
                    f"[AGENT] No se pudo persistir respuesta del bot en "
                    f"{conv_id}: {persist_err}"
                )
            # Persistir intent en conversations.context para analytics
            try:
                intent_type = result.get("intent", {}).get("type")
                if intent_type:
                    get_db().client.table("conversations").update(
                        {"context": {"intent": intent_type}}
                    ).eq("id", conv_id).execute()
                    logger.debug(f"[AGENT] Intent '{intent_type}' guardado en conversación {conv_id}")
            except Exception as intent_err:
                logger.warning(f"[AGENT] No se pudo actualizar intent en conversación {conv_id}: {intent_err}")
        else:
            logger.warning(
                f"[AGENT] conversation_id no es UUID, persistencia omitida: {conv_id}"
            )

        logger.success(
            f"[AGENT] Respuesta enviada a {data['customer_phone']}: "
            f"{result['message'][:80]}"
        )

    except Exception as e:
        logger.error(f"[AGENT] Error procesando agent reply: {e}")
    finally:
        TenantContextManager.clear()
