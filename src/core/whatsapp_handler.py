"""
Este módulo define la clase WhatsAppHandler.
Gestiona la integración con la API de WhatsApp Business.
Usa httpx directo a la API de Meta (sin heyoo).
"""

import os
import threading
import time
import httpx
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple, Deque
from collections import deque

from src.core.tenant_context import TenantContextManager, require_tenant
from src.core.logger import logger
from src.core.event_bus import event_bus
from src.core.rate_limiter import rate_limiter
from src.core.database import get_db
from src.repositories.conversation_repo import ConversationRepo
from src.repositories.message_repo import MessageRepo
from src.services.usage_tracker import MessageTracker

META_API_URL = "https://graph.facebook.com/v22.0"


# ============================================
# Parser de payloads de Meta
# ============================================


def parse_meta_payload(data: dict) -> List[Dict[str, Any]]:
    messages_out: List[Dict[str, Any]] = []

    if not isinstance(data, dict) or data.get("object") != "whatsapp_business_account":
        return messages_out

    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            metadata = value.get("metadata", {})
            phone_number_id = metadata.get("phone_number_id", "")

            contacts = {
                c.get("wa_id", ""): c.get("profile", {}).get("name", "")
                for c in value.get("contacts", [])
            }

            for msg in value.get("messages", []):
                msg_type = msg.get("type", "text")
                body = ""

                if msg_type == "text":
                    body = msg.get("text", {}).get("body", "")
                elif msg_type == "image":
                    body = msg.get("image", {}).get("caption", "[imagen]")
                elif msg_type == "audio":
                    body = "[audio]"
                elif msg_type == "document":
                    body = msg.get("document", {}).get("caption", "[documento]")
                elif msg_type == "video":
                    body = msg.get("video", {}).get("caption", "[video]")
                elif msg_type == "location":
                    loc = msg.get("location", {})
                    body = f"[ubicacion: {loc.get('latitude')}, {loc.get('longitude')}]"
                elif msg_type == "interactive":
                    interactive = msg.get("interactive", {})
                    if interactive.get("type") == "button_reply":
                        body = interactive.get("button_reply", {}).get("title", "")
                    elif interactive.get("type") == "list_reply":
                        body = interactive.get("list_reply", {}).get("title", "")

                from_number = msg.get("from", "")
                messages_out.append(
                    {
                        "from": from_number,
                        "name": contacts.get(from_number, ""),
                        "message_id": msg.get("id", ""),
                        "timestamp": msg.get("timestamp", ""),
                        "type": msg_type,
                        "body": body,
                        "phone_number_id": phone_number_id,
                    }
                )

    return messages_out


def has_status_updates(data: dict) -> bool:
    if not isinstance(data, dict):
        return False
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            if value.get("statuses") and not value.get("messages"):
                return True
    return False


# Deduplicación de mensajes
_DEDUP_LIMIT = 500
_DEDUP_TTL_SECONDS = 60 * 60
_seen_messages: Dict[str, Deque[Tuple[str, float]]] = {}
_seen_lock = threading.Lock()


def _is_duplicate(tenant_slug: str, message_id: str) -> bool:
    if not message_id:
        return False
    current_time = time.time()
    with _seen_lock:
        dq = _seen_messages.setdefault(tenant_slug, deque(maxlen=_DEDUP_LIMIT))
        while dq and current_time - dq[0][1] > _DEDUP_TTL_SECONDS:
            dq.popleft()
        if any(mid == message_id for mid, _ in dq):
            return True
        dq.append((message_id, current_time))
    return False


class WhatsAppHandler:
    def __init__(self, token: str = None, phone_id: str = None):
        tenant = TenantContextManager.get_current()

        self.token = token
        self.phone_id = phone_id

        if tenant:
            self.token = self.token or tenant.get_config("whatsapp_token")
            self.phone_id = self.phone_id or tenant.get_config("whatsapp_phone_id")

        # Permite dummy tokens en tests
        if (not self.token or not self.phone_id) and os.getenv("PYTEST_CURRENT_TEST"):
            self.token = "dummy_token"
            self.phone_id = "dummy_phone_id"

        if not self.token or not self.phone_id:
            raise ValueError("WhatsApp token y phone_id son requeridos (multi-tenant)")

        # Cliente httpx (reemplaza heyoo)
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _send_request(self, payload: dict) -> dict:
        """Envía request a la API de Meta."""
        url = f"{META_API_URL}/{self.phone_id}/messages"
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(url, json=payload, headers=self.headers)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Error Meta API: {e.response.status_code} - {e.response.text}"
            )
            raise RuntimeError(f"Error Meta API: {e.response.text}")
        except Exception as e:
            logger.error(f"Error enviando mensaje WhatsApp: {e}")
            raise RuntimeError(f"Error enviando mensaje WhatsApp: {str(e)}")

    @require_tenant
    def send_message(self, to: str, message: str):
        """Envía un mensaje de texto."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": message},
        }
        result = self._send_request(payload)

        try:
            tenant = TenantContextManager.get_current()
            if tenant:
                tracker = MessageTracker()
                tracker.record_message(tenant.tenant_id, direction="outgoing")
        except Exception as track_err:
            logger.warning(f"[USAGE] Error tracking outgoing message: {track_err}")

        return result

    @require_tenant
    def send_template(
        self, to: str, template_name: str, language: str = None, components=None
    ):
        """Envía una plantilla de WhatsApp."""
        tenant = TenantContextManager.get_current()
        lang = (
            language
            or (tenant.get_config("whatsapp_language") if tenant else None)
            or "es"
        )
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": lang},
                "components": components or [],
            },
        }
        return self._send_request(payload)

    def webhook_verify(self, mode: str, token: str, challenge: str):
        tenant = TenantContextManager.get_current()
        verify_token = None
        if tenant:
            verify_token = tenant.get_config("whatsapp_verify_token")
        if not verify_token:
            verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN")

        if mode == "subscribe" and verify_token and token == verify_token:
            return challenge
        return None

    def _persist_conversation(
        self,
        tenant_id: str,
        tenant_slug: str,
        msg: Dict[str, Any],
        now: str,
    ) -> Optional[str]:
        """
        Crea o actualiza la conversación en Supabase y guarda el mensaje entrante.
        Retorna el conversation_id (UUID) de Supabase.
        """
        try:
            from src.core.database import get_db

            db = get_db().client

            phone = msg["from"]
            contact_name = msg.get("name", "")

            # 1. Buscar conversación activa existente por phone + tenant
            existing = (
                db.table("conversations")
                .select("id, unread_count")
                .eq("tenant_id", tenant_id)
                .eq("phone", phone)
                .eq("status", "ACTIVE")
                .limit(1)
                .execute()
            )

            if existing.data:
                # Actualizar conversación existente
                conv_id = existing.data[0]["id"]
                unread = (existing.data[0].get("unread_count") or 0) + 1
                db.table("conversations").update(
                    {
                        "last_message_at": now,
                        "unread_count": unread,
                        "updated_at": now,
                        "contact_name": contact_name
                        or existing.data[0].get("contact_name", ""),
                    }
                ).eq("id", conv_id).execute()
            else:
                # Crear nueva conversación con retry: si una columna falla el check
                # constraint o no existe, la elimina y reintenta.
                new_conv_payload = {
                    "tenant_id": tenant_id,
                    "phone": phone,
                    "contact_name": contact_name,
                    "contact_type": "whatsapp",
                    "status": "ACTIVE",
                    "bot_active": True,
                    "unread_count": 1,
                    "last_message_at": now,
                    "started_at": now,
                    "created_at": now,
                    "updated_at": now,
                }
                conv_id = None
                for _ in range(len(new_conv_payload) + 2):
                    try:
                        result = db.table("conversations").insert(new_conv_payload).execute()
                        conv_id = result.data[0]["id"] if result.data else None
                        break
                    except Exception as col_exc:
                        err_str = str(col_exc)
                        # Detectar columna que viola constraint o no existe y eliminarla
                        bad_col = None
                        for candidate in list(new_conv_payload.keys()):
                            if candidate in err_str:
                                bad_col = candidate
                                break
                        if bad_col and bad_col != "tenant_id":
                            new_conv_payload.pop(bad_col)
                        else:
                            raise

                # Notificar al tenant sobre el nuevo contacto
                if conv_id:
                    from src.services.notification_service import notify_new_conversation
                    notify_new_conversation(
                        db_client=db,
                        tenant_id=tenant_id,
                        customer_phone=phone,
                        customer_name=contact_name or None,
                        conversation_id=str(conv_id),
                    )

            if not conv_id:
                logger.warning(f"[PERSIST] No se pudo obtener conv_id para {phone}")
                return None

            # 2. Guardar mensaje entrante (upsert para tolerar reintentos del worker)
            db.table("messages").upsert(
                {
                    "conversation_id": conv_id,
                    "tenant_id": tenant_id,
                    "sender": "contact",
                    "content": msg["body"],
                    "message_type": msg.get("type", "text"),
                    "whatsapp_message_id": msg.get("message_id", ""),
                    "created_at": now,
                },
                on_conflict="whatsapp_message_id",
            ).execute()

            logger.debug(f"[PERSIST] Conversación {conv_id} persistida para {phone}")
            return str(conv_id)

        except Exception as e:
            logger.error(f"[PERSIST] Error persistiendo conversación: {e}")
            return None

    @require_tenant
    def handle_webhook(self, data: dict):
        """Procesa un payload de webhook de Meta."""
        if not isinstance(data, dict):
            return {"status": "invalid_payload"}

        tenant = TenantContextManager.get_current()
        if not tenant:
            return {"status": "no_tenant_context"}

        tenant_slug = tenant.get_config("slug", "unknown")

        if has_status_updates(data):
            logger.debug(f"[{tenant_slug}] Status update recibido, ignorado")
            return {
                "status": "received",
                "tenant": tenant.tenant_id,
                "messages_processed": 0,
            }

        parsed_messages = parse_meta_payload(data)

        if not parsed_messages:
            logger.debug(f"[{tenant_slug}] Payload sin mensajes procesables")
            return {
                "status": "received",
                "tenant": tenant.tenant_id,
                "messages_processed": 0,
                "data": data,
            }

        processed: List[Dict[str, Any]] = []
        rate_limited_users: List[str] = []
        now = datetime.now(timezone.utc).isoformat()

        conversation_repo: Optional[ConversationRepo] = None
        message_repo: Optional[MessageRepo] = None
        try:
            db = get_db()
            conversation_repo = ConversationRepo(client=db.client)
            message_repo = MessageRepo(client=db.client)
        except Exception as db_err:
            logger.warning(
                f"[{tenant_slug}] Persistencia deshabilitada temporalmente (DB no disponible): {db_err}"
            )

        for msg in parsed_messages:
            conversation_id = f"wa_{tenant_slug}_{msg['from']}"

            if _is_duplicate(tenant_slug, msg["message_id"]):
                logger.info(
                    f"[{tenant_slug}] Mensaje duplicado ignorado: {msg['message_id']}"
                )
                continue

            allowed, limit_message = rate_limiter.check(tenant_slug, msg["from"])
            if not allowed:
                rate_limited_users.append(msg["from"])
                logger.warning(f"[{tenant_slug}] Rate limit excedido por {msg['from']}")
                if limit_message:
                    self._send_rate_limit_notice(msg["from"], limit_message)
                continue

            logger.info(
                f"[{tenant_slug}] Mensaje {msg['type']} de {msg['from']} "
                f"({msg['name']}): {msg['body'][:80]}"
            )

            # Persistencia directa en Supabase
            db_conv_id = self._persist_conversation(
                tenant_id=tenant.tenant_id,
                tenant_slug=tenant_slug,
                msg=msg,
                now=now,
            )

            # Reemplazar el ID temporal por el ID real de Supabase si todo salió bien
            if db_conv_id:
                conversation_id = db_conv_id

            # Armar el paquete para el evento (ya con el ID correcto)
            processed.append(
                {
                    "conversation_id": conversation_id,
                    "from": msg["from"],
                    "name": msg["name"],
                    "type": msg["type"],
                    "body": msg["body"],
                    "message_id": msg["message_id"],
                }
            )

        if processed:
            self._dispatch_agent_events(tenant_slug, processed)

        if processed:
            try:
                message_tracker = MessageTracker()
                for _ in processed:
                    message_tracker.record_message(
                        tenant.tenant_id, direction="incoming"
                    )
            except Exception as e:
                logger.warning(f"[USAGE] Error registrando mensajes: {e}")

        return {
            "status": "received",
            "tenant": tenant.tenant_id,
            "messages_processed": len(processed),
            "messages_rate_limited": len(rate_limited_users),
            "messages": processed,
        }

    def _send_rate_limit_notice(self, phone_number: str, body: str) -> None:
        try:
            self.send_message(phone_number, body)
        except Exception as exc:
            logger.error(
                f"No se pudo enviar aviso de rate limit a {phone_number}: {exc}"
            )

    def _dispatch_agent_events(self, tenant_slug: str, messages: List[Dict[str, Any]]):
        """Publica eventos para que el agente procese y responda."""
        for payload in messages:
            event_bus.publish(
                "whatsapp.message.received",
                {
                    "conversation_id": payload["conversation_id"],
                    "customer_phone": payload["from"],
                    "customer_name": payload["name"],
                    "body": payload["body"],
                    "message_type": payload["type"],
                    "message_id": payload["message_id"],
                },
                metadata={"channel": "whatsapp", "tenant_slug": tenant_slug},
            )

            event_bus.publish(
                "agent.reply.requested",
                {
                    "conversation_id": payload["conversation_id"],
                    "input_text": payload["body"],
                    "customer_phone": payload["from"],
                    "customer_name": payload["name"],
                    "source": "whatsapp",
                    "message_id": payload["message_id"],
                },
                metadata={"tenant_slug": tenant_slug},
            )
