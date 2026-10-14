from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any, Dict, Optional

from supabase import Client
from src.core.logger import logger


class MessageRepo:
    """Repositorio para lectura de mensajes de conversación con aislamiento tenant."""

    _VALID_SENDERS = {"bot", "agent", "contact", "imported"}
    _VALID_STATUSES = {"sent", "delivered", "read"}

    def __init__(self, client: Client):
        self.client = client

    def get_messages_by_conversation(
        self,
        *,
        tenant_id: str,
        conversation_id: str,
        limit: int = 50,
        before: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Retorna mensajes paginados (cursor backwards) para una conversación del tenant.

        Devuelve None cuando la conversación no existe o no pertenece al tenant.
        """
        safe_limit = max(1, min(limit, 100))
        normalized_before = self._normalize_datetime(before) if before else None

        if not self._conversation_belongs_to_tenant(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
        ):
            return None

        query = (
            self.client.table("messages")
            .select("id,content,sender,status,created_at")
            .eq("conversation_id", conversation_id)
            .order("created_at", desc=True)
            .limit(safe_limit + 1)
        )

        if normalized_before is not None:
            query = query.lt("created_at", self._format_datetime(normalized_before))

        try:
            response = query.execute()
        except Exception:
            legacy_query = (
                self.client.table("messages")
                .select("id,content,sender,created_at")
                .eq("conversation_id", conversation_id)
                .order("created_at", desc=True)
                .limit(safe_limit + 1)
            )
            if normalized_before is not None:
                legacy_query = legacy_query.lt(
                    "created_at", self._format_datetime(normalized_before)
                )
            response = legacy_query.execute()

        rows = response.data or []

        has_more = len(rows) > safe_limit
        visible_rows = rows[:safe_limit]
        items = [self._map_row(row) for row in visible_rows]

        return {
            "data": items,
            "has_more": has_more,
            "oldest_cursor": items[-1]["sent_at"] if items else None,
        }

    def get_conversation_for_tenant(
        self,
        *,
        tenant_id: str,
        conversation_id: str,
    ) -> Optional[Dict[str, Any]]:
        response = (
            self.client.table("conversations")
            .select("*")
            .eq("id", conversation_id)
            .eq("tenant_id", tenant_id)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if not rows:
            return None
        return rows[0]

    def get_last_contact_message_at(
        self,
        *,
        conversation_id: str,
    ) -> Optional[datetime]:
        """Retorna la fecha del último mensaje del contacto (sender='contact')."""
        query = (
            self.client.table("messages")
            .select("created_at")
            .eq("conversation_id", conversation_id)
            .eq("sender", "contact")
            .order("created_at", desc=True)
            .limit(1)
        )

        try:
            response = query.execute()
            rows = response.data or []
            if not rows:
                return None
            return self._normalize_datetime(rows[0].get("created_at"))
        except Exception:
            # Fallback para esquemas con columna "sender".
            legacy_query = (
                self.client.table("messages")
                .select("created_at")
                .eq("conversation_id", conversation_id)
                .eq("sender", "contact")
                .order("created_at", desc=True)
                .limit(1)
            )
            legacy_response = legacy_query.execute()
            legacy_rows = legacy_response.data or []
            if not legacy_rows:
                return None
            return self._normalize_datetime(legacy_rows[0].get("created_at"))

    @staticmethod
    def is_manual_window_open(last_contact_message_at: Optional[datetime]) -> bool:
        if last_contact_message_at is None:
            return False
        now = datetime.now(timezone.utc)
        return now - last_contact_message_at <= timedelta(hours=24)

    @staticmethod
    def is_bot_active(conversation_row: Dict[str, Any]) -> bool:
        value = conversation_row.get("bot_active")
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "t", "yes", "y", "on"}
        return bool(value)

    @staticmethod
    def extract_conversation_phone(conversation_row: Dict[str, Any]) -> str:
        return str(
            conversation_row.get("phone")
            or conversation_row.get("contact_phone")
            or conversation_row.get("phone_number")
            or conversation_row.get("user_phone")
            or ""
        ).strip()

    def persist_incoming_contact_message(
        self,
        *,
        tenant_id: str,
        conversation_id: str,
        content: str,
        whatsapp_message_id: str = "",
        message_type: str = "text",
    ) -> Dict[str, Any]:
        """
        Persiste un mensaje entrante del contacto.
        """
        normalized_content = content.strip()
        payload = {
            "conversation_id": conversation_id,
            "tenant_id": tenant_id,
            "sender": "contact",
            "status": "delivered",
            "content": normalized_content,
            "message_type": message_type,
            "whatsapp_message_id": whatsapp_message_id or None,
        }

        message_row = self._insert_message_with_fallback(payload)
        created_at = self._normalize_datetime(message_row.get("created_at"))
        if created_at is None:
            created_at = datetime.now(timezone.utc)

        self._execute_conversation_update_with_fallback(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            updates={
                "last_message_at": self._format_datetime(created_at),
            },
        )

        mapped = self._map_row(message_row)
        mapped["sender"] = "contact"
        mapped["status"] = "delivered"
        return mapped

    def persist_bot_reply_message(
        self,
        *,
        tenant_id: str,
        conversation_id: str,
        content: str,
    ) -> Dict[str, Any]:
        """
        Persiste un mensaje saliente automático del bot IA.
        """
        normalized_content = content.strip()
        payload = {
            "conversation_id": conversation_id,
            "tenant_id": tenant_id,
            "sender": "bot",
            "content": normalized_content,
            "message_type": "text",
            "status": "sent",
        }

        message_row = self._insert_message_with_fallback(payload)
        sent_at_dt = self._normalize_datetime(message_row.get("created_at"))
        if sent_at_dt is None:
            sent_at_dt = datetime.now(timezone.utc)

        self._execute_conversation_update_with_fallback(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            updates={
                "last_message_at": self._format_datetime(sent_at_dt),
            },
        )

        mapped = self._map_row(message_row)
        mapped["sender"] = "bot"
        mapped["status"] = "sent"
        return mapped

    def persist_manual_agent_message(
        self,
        *,
        tenant_id: str,
        conversation_id: str,
        content: str,
    ) -> Dict[str, Any]:
        """
        Persiste mensaje de agente y actualiza metadatos de conversación.

        Debe ejecutarse únicamente después de confirmación de WhatsApp.
        Incluye deduplicación: si en los últimos 3 segundos se guardó un mensaje
        idéntico del agente, devuelve ese mensaje sin insertar uno nuevo.
        """
        normalized_content = content.strip()

        # ── Deduplicación ─────────────────────────────────────────────────────
        duplicate = self._find_recent_duplicate(
            conversation_id=conversation_id,
            content=normalized_content,
            sender="agent",
            window_seconds=3,
        )
        if duplicate is not None:
            logger.debug(
                f"[MSG_REPO] Duplicado detectado para conversation={conversation_id} "
                f"— devolviendo mensaje existente id={duplicate.get('id')}"
            )
            mapped = self._map_row(duplicate)
            mapped["sender"] = "agent"
            mapped["status"] = "sent"
            return mapped
        # ──────────────────────────────────────────────────────────────────────

        message_row = self._insert_agent_message(
            conversation_id=conversation_id,
            content=normalized_content,
            tenant_id=tenant_id,
        )

        sent_at_dt = self._normalize_datetime(message_row.get("created_at"))
        if sent_at_dt is None:
            sent_at_dt = datetime.now(timezone.utc)

        (
            self.client.table("conversations")
            .update(
                {
                    "last_message_at": self._format_datetime(sent_at_dt),
                    "unread_count": 0,
                }
            )
            .eq("id", conversation_id)
            .eq("tenant_id", tenant_id)
            .execute()
        )

        mapped = self._map_row(message_row)
        mapped["sender"] = "agent"
        mapped["status"] = "sent"
        return mapped

    def _insert_agent_message(self, *, conversation_id: str, content: str, tenant_id: str = "") -> Dict[str, Any]:
        payload = {
            "conversation_id": conversation_id,
            "tenant_id": tenant_id or None,
            "sender": "agent",
            "content": content,
            "status": "sent",
            "message_type": "text",
        }
        return self._insert_message_with_fallback(payload)

    def _insert_message_with_fallback(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        working_payload = dict(payload)
        max_attempts = len(working_payload) + 2
        inserted = False

        for _ in range(max_attempts):
            try:
                (
                    self.client.table("messages")
                    .insert(working_payload)
                    .execute()
                )
                inserted = True
                break
            except Exception as exc:
                err_str = str(exc)
                # Duplicate key — mensaje ya existe, simplemente lo devolvemos
                if "23505" in err_str or "duplicate key" in err_str.lower():
                    logger.debug(
                        f"[MSG_REPO] Mensaje duplicado detectado para "
                        f"conversation={working_payload.get('conversation_id')} — devolviendo existente"
                    )
                    latest = self._fetch_latest_message(
                        conversation_id=str(working_payload.get("conversation_id", ""))
                    )
                    if latest:
                        return latest
                    break
                missing_col = self._extract_missing_column(exc)
                if not missing_col or missing_col not in working_payload:
                    logger.error(f"[MSG_REPO] Error inesperado en insert de messages: {exc}")
                    raise
                logger.debug(f"[MSG_REPO] Columna '{missing_col}' no existe, reintentando sin ella")
                working_payload.pop(missing_col, None)

        if inserted:
            latest = self._fetch_latest_message(
                conversation_id=str(payload.get("conversation_id", ""))
            )
            if latest:
                return latest

        return {
            "id": "",
            "content": str(payload.get("content") or ""),
            "sender": str(payload.get("sender") or "imported"),
            "status": str(payload.get("status") or "sent"),
            "created_at": datetime.now(timezone.utc),
        }

    def _fetch_latest_message(self, *, conversation_id: str) -> Optional[Dict[str, Any]]:
        select_candidates = [
            "id,content,sender,status,created_at",
            "id,content,sender,created_at",
            "*",
        ]

        for select_stmt in select_candidates:
            try:
                response = (
                    self.client.table("messages")
                    .select(select_stmt)
                    .eq("conversation_id", conversation_id)
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute()
                )
                rows = response.data or []
                if rows:
                    return rows[0]
            except Exception:
                continue

        return None

    def _execute_conversation_update_with_fallback(
        self,
        *,
        tenant_id: str,
        conversation_id: str,
        updates: Dict[str, Any],
    ) -> None:
        working_updates = dict(updates)
        max_attempts = len(working_updates) + 2

        for _ in range(max_attempts):
            try:
                (
                    self.client.table("conversations")
                    .update(working_updates)
                    .eq("id", conversation_id)
                    .eq("tenant_id", tenant_id)
                    .execute()
                )
                return
            except Exception as exc:
                missing_col = self._extract_missing_column(exc)
                if not missing_col or missing_col not in working_updates:
                    return
                working_updates.pop(missing_col, None)

    def _find_recent_duplicate(
        self,
        *,
        conversation_id: str,
        content: str,
        sender: str,
        window_seconds: int = 3,
    ) -> Optional[Dict[str, Any]]:
        """
        Busca el último mensaje del sender en la conversación y comprueba si
        tiene el mismo contenido y fue creado hace menos de window_seconds.
        Devuelve la fila si es duplicado, None en caso contrario.
        """
        try:
            response = (
                self.client.table("messages")
                .select("id,content,sender,status,created_at")
                .eq("conversation_id", conversation_id)
                .eq("sender", sender)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            rows = response.data or []
            if not rows:
                return None

            last = rows[0]
            if last.get("content", "").strip() != content:
                return None

            created_at = self._normalize_datetime(last.get("created_at"))
            if created_at is None:
                return None

            age = (datetime.now(timezone.utc) - created_at).total_seconds()
            if age <= window_seconds:
                return last

        except Exception as exc:
            logger.debug(f"[MSG_REPO] No se pudo verificar duplicado: {exc}")

        return None

    @staticmethod
    def _extract_missing_column(error: Exception) -> Optional[str]:
        raw = str(error)
        patterns = [
            r"'([a-zA-Z_][a-zA-Z0-9_]*)'",
            r'column\s+"([a-zA-Z_][a-zA-Z0-9_]*)"\s+does not exist',
        ]
        for pattern in patterns:
            match = re.search(pattern, raw, flags=re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def _conversation_belongs_to_tenant(self, *, tenant_id: str, conversation_id: str) -> bool:
        response = (
            self.client.table("conversations")
            .select("id")
            .eq("id", conversation_id)
            .eq("tenant_id", tenant_id)
            .limit(1)
            .execute()
        )
        return bool(response.data)

    @classmethod
    def _map_row(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        sent_at = cls._normalize_datetime(row.get("created_at"))
        if sent_at is None:
            sent_at = datetime.now(timezone.utc)

        return {
            "id": str(row.get("id", "")),
            "content": str(row.get("content") or ""),
            "sender": cls._normalize_sender(row.get("sender")),
            "status": cls._normalize_status(row.get("status")),
            "sent_at": cls._format_datetime(sent_at),
        }

    @classmethod
    def _normalize_sender(cls, value: Any) -> str:
        sender = str(value or "").strip().lower()

        if sender in cls._VALID_SENDERS:
            return sender
        if sender in {"assistant", "ai"}:
            return "bot"
        if sender in {"user", "customer", "cliente"}:
            return "contact"

        return "imported"

    @classmethod
    def _normalize_status(cls, value: Any) -> str:
        status = str(value or "").strip().lower()

        if status in cls._VALID_STATUSES:
            return status
        if status in {"received", "recv"}:
            return "delivered"

        return "sent"

    @staticmethod
    def _normalize_datetime(value: Any) -> Optional[datetime]:
        if value is None:
            return None

        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, str):
            raw = value.strip()
            if raw.endswith("Z"):
                raw = raw[:-1] + "+00:00"
            try:
                dt = datetime.fromisoformat(raw)
            except ValueError:
                return None
        else:
            return None

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)

        return dt

    @staticmethod
    def _format_datetime(value: datetime) -> str:
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
