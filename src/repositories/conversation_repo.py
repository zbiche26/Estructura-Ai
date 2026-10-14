from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional

from supabase import Client

from src.core.logger import logger


class ConversationRepo:
    """Repositorio para listado de conversaciones orientado al contrato HTTP."""

    _PHONE_COLUMNS = ("contact_phone", "phone", "phone_number", "user_phone")

    def __init__(self, client: Client):
        self.client = client

    def list_conversations(
        self,
        *,
        tenant_id: str,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        contact_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Lista conversaciones paginadas con filtros opcionales."""
        safe_page = max(1, page)
        safe_page_size = max(1, min(page_size, 100))
        start = (safe_page - 1) * safe_page_size
        end = start + safe_page_size - 1

        try:
            response = self._execute_query(
                tenant_id=tenant_id,
                status=status,
                contact_type=contact_type,
                start=start,
                end=end,
            )
        except Exception as exc:
            logger.error(f"Error listando conversaciones: {exc}")
            return {
                "data": [],
                "total": 0,
                "page": safe_page,
                "page_size": safe_page_size,
            }

        rows = response.data or []
        items = [self._map_row(row) for row in rows]

        return {
            "data": items,
            "total": int(getattr(response, "count", 0) or 0),
            "page": safe_page,
            "page_size": safe_page_size,
        }

    def update_conversation(
        self,
        *,
        tenant_id: str,
        conversation_id: str,
        updates: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Actualiza campos editables de una conversación y retorna el objeto completo."""
        try:
            ownership = (
                self.client.table("conversations")
                .select("id")
                .eq("id", conversation_id)
                .eq("tenant_id", tenant_id)
                .limit(1)
                .execute()
            )
            if not ownership.data:
                return None

            safe_updates = self._sanitize_updates(updates)
            if safe_updates:
                self._execute_update(
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    updates=safe_updates,
                )

            return self._get_conversation_by_id(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
            )
        except Exception as exc:
            logger.error(f"Error actualizando conversación {conversation_id}: {exc}")
            raise

    def mark_as_read(
        self,
        *,
        tenant_id: str,
        conversation_id: str,
    ) -> bool:
        """Marca una conversación como leída (unread_count=0) para el tenant indicado."""
        try:
            response = (
                self.client.table("conversations")
                .update({"unread_count": 0})
                .eq("id", conversation_id)
                .eq("tenant_id", tenant_id)
                .execute()
            )
            return bool(response.data)
        except Exception as exc:
            logger.error(
                f"Error marcando conversación como leída {conversation_id}: {exc}"
            )
            raise

    def get_or_create_active_conversation(
        self,
        *,
        tenant_id: str,
        contact_phone: str,
        contact_name: str = "",
        contact_type: str = "whatsapp",
    ) -> Optional[Dict[str, Any]]:
        """
        Obtiene conversación activa por teléfono o crea una nueva.

        Se adapta a esquemas con columnas de teléfono legacy/nuevo.
        """
        normalized_phone = str(contact_phone or "").strip()
        if not normalized_phone:
            return None

        existing = self._find_active_by_phone(
            tenant_id=tenant_id,
            contact_phone=normalized_phone,
        )
        if existing:
            return existing

        return self._create_conversation(
            tenant_id=tenant_id,
            contact_phone=normalized_phone,
            contact_name=(contact_name or "").strip(),
            contact_type=(contact_type or "whatsapp").strip() or "whatsapp",
        )

    def increment_unread_count(
        self,
        *,
        tenant_id: str,
        conversation_id: str,
        increment_by: int = 1,
        contact_name: str = "",
    ) -> None:
        """
        Incrementa unread_count y actualiza last_message_at.
        """
        if increment_by <= 0:
            return

        row = (
            self.client.table("conversations")
            .select("*")
            .eq("id", conversation_id)
            .eq("tenant_id", tenant_id)
            .limit(1)
            .execute()
        )
        rows = row.data or []
        if not rows:
            return

        current = rows[0]
        current_unread = self._non_negative_int(current.get("unread_count"), default=0)
        updates: Dict[str, Any] = {
            "unread_count": current_unread + increment_by,
            "last_message_at": self._format_datetime(datetime.now(timezone.utc)),
        }

        normalized_name = (contact_name or "").strip()
        if normalized_name:
            updates["contact_name"] = normalized_name
            updates["customer_name"] = normalized_name
            updates["user_name"] = normalized_name

        self._safe_update_conversation(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            updates=updates,
        )

    def _execute_update(
        self,
        *,
        tenant_id: str,
        conversation_id: str,
        updates: Dict[str, Any],
    ) -> None:
        update_query = (
            self.client.table("conversations")
            .update(updates)
            .eq("id", conversation_id)
            .eq("tenant_id", tenant_id)
        )

        try:
            update_query.execute()
            return
        except Exception as exc:
            if "contact_type" not in updates:
                raise
            if not self._is_missing_column_error(exc, "contact_type"):
                raise

            legacy_updates = dict(updates)
            legacy_updates["platform"] = legacy_updates.pop("contact_type")
            (
                self.client.table("conversations")
                .update(legacy_updates)
                .eq("id", conversation_id)
                .eq("tenant_id", tenant_id)
                .execute()
            )

    def _find_active_by_phone(
        self,
        *,
        tenant_id: str,
        contact_phone: str,
    ) -> Optional[Dict[str, Any]]:
        for phone_col in self._PHONE_COLUMNS:
            row = self._find_by_phone_column(
                tenant_id=tenant_id,
                contact_phone=contact_phone,
                phone_column=phone_col,
            )
            if row:
                return row
        return None

    def _find_by_phone_column(
        self,
        *,
        tenant_id: str,
        contact_phone: str,
        phone_column: str,
    ) -> Optional[Dict[str, Any]]:
        base = (
            self.client.table("conversations")
            .select("*")
            .eq("tenant_id", tenant_id)
            .eq(phone_column, contact_phone)
            .limit(1)
        )

        try:
            response = (
                base.eq("status", "active")
                .order("last_message_at", desc=True)
                .execute()
            )
        except Exception as exc:
            missing_col = self._extract_missing_column(exc)
            if missing_col in {phone_column, "status", "last_message_at"}:
                try:
                    response = base.order("created_at", desc=True).execute()
                except Exception:
                    return None
            else:
                return None

        rows = response.data or []
        if rows:
            return rows[0]
        return None

    def _create_conversation(
        self,
        *,
        tenant_id: str,
        contact_phone: str,
        contact_name: str,
        contact_type: str,
    ) -> Optional[Dict[str, Any]]:
        payload: Dict[str, Any] = {
            "tenant_id": tenant_id,
            "status": "active",
            "bot_active": True,
            "unread_count": 0,
            "last_message_at": self._format_datetime(datetime.now(timezone.utc)),
            "contact_type": contact_type,
            "platform": contact_type,
            "contact_name": contact_name,
            "customer_name": contact_name,
            "user_name": contact_name,
        }

        for phone_column in self._PHONE_COLUMNS:
            payload[phone_column] = contact_phone
            created = self._safe_insert_conversation(payload)
            payload.pop(phone_column, None)
            if created:
                return created

        logger.error(
            "No se pudo crear conversación: no se encontró columna de teléfono compatible"
        )
        return None

    def _safe_insert_conversation(
        self, payload: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        working_payload = dict(payload)
        max_attempts = len(working_payload) + 2

        for _ in range(max_attempts):
            try:
                response = (
                    self.client.table("conversations").insert(working_payload).execute()
                )
                rows = response.data or []
                if rows:
                    return rows[0]
                return None
            except Exception as exc:
                missing_col = self._extract_missing_column(exc)
                if not missing_col or missing_col not in working_payload:
                    logger.warning(f"Error insertando conversación: {exc}")
                    return None
                working_payload.pop(missing_col, None)

        return None

    def _safe_update_conversation(
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
                    logger.warning(
                        f"Error actualizando conversación {conversation_id}: {exc}"
                    )
                    return
                working_updates.pop(missing_col, None)

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

    @staticmethod
    def _is_missing_column_error(error: Exception, column: str) -> bool:
        raw = str(error).lower()
        target = f"'{column.lower()}'"
        return "pgrst204" in raw and "could not find" in raw and target in raw

    def _get_conversation_by_id(
        self,
        *,
        tenant_id: str,
        conversation_id: str,
    ) -> Optional[Dict[str, Any]]:
        response = (
            self.client.table("conversations")
            .select("*,messages(content,created_at)")
            .eq("id", conversation_id)
            .eq("tenant_id", tenant_id)
            .order("created_at", desc=True, foreign_table="messages")
            .limit(1, foreign_table="messages")
            .limit(1)
            .execute()
        )

        rows = response.data or []
        if not rows:
            return None

        return self._map_row(rows[0])

    @staticmethod
    def _sanitize_updates(updates: Dict[str, Any]) -> Dict[str, Any]:
        allowed = {"bot_active", "contact_type", "contact_name", "status"}
        safe_updates: Dict[str, Any] = {}

        for key, value in updates.items():
            if key not in allowed:
                continue
            if isinstance(value, str):
                safe_updates[key] = value.strip()
            else:
                safe_updates[key] = value

        return safe_updates

    def _execute_query(
        self,
        *,
        tenant_id: str,
        status: Optional[str],
        contact_type: Optional[str],
        start: int,
        end: int,
    ):
        query = (
            self.client.table("conversations")
            .select("*,messages(content,created_at)", count="exact")
            .eq("tenant_id", tenant_id)
        )

        if status:
            query = query.eq("status", status)
        if contact_type:
            # Filtro principal según el contrato de datos.
            query = query.eq("contact_type", contact_type)

        query = query.order("last_message_at", desc=True)
        query = (
            query.order("created_at", desc=True)
            .order("created_at", desc=True, foreign_table="messages")
            .limit(1, foreign_table="messages")
            .range(start, end)
        )

        try:
            return query.execute()
        except Exception:
            # Fallback por compatibilidad cuando last_message_at no existe.
            query_without_last_message = (
                self.client.table("conversations")
                .select("*,messages(content,created_at)", count="exact")
                .eq("tenant_id", tenant_id)
            )

            if status:
                query_without_last_message = query_without_last_message.eq(
                    "status", status
                )
            if contact_type:
                query_without_last_message = query_without_last_message.eq(
                    "contact_type", contact_type
                )

            query_without_last_message = (
                query_without_last_message.order("created_at", desc=True)
                .order("created_at", desc=True, foreign_table="messages")
                .limit(1, foreign_table="messages")
                .range(start, end)
            )

            try:
                return query_without_last_message.execute()
            except Exception:
                pass

            # Fallback por compatibilidad con esquemas legacy donde se usa "platform".
            if not contact_type:
                raise

            fallback_query = (
                self.client.table("conversations")
                .select("*,messages(content,created_at)", count="exact")
                .eq("tenant_id", tenant_id)
                .eq("platform", contact_type)
            )

            if status:
                fallback_query = fallback_query.eq("status", status)

            fallback_query = (
                fallback_query.order("created_at", desc=True)
                .order("created_at", desc=True, foreign_table="messages")
                .limit(1, foreign_table="messages")
                .range(start, end)
            )
            return fallback_query.execute()

    @classmethod
    def _map_row(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        latest_message = cls._latest_message(row.get("messages"))
        last_message_at = cls._resolve_last_message_at(row, latest_message)

        return {
            "id": str(row.get("id", "")),
            "phone": row.get("phone")
            or row.get("contact_phone")
            or row.get("phone_number")
            or row.get("user_phone")
            or "",
            "contact_name": row.get("contact_name")
            or row.get("customer_name")
            or row.get("user_name")
            or "",
            "contact_type": row.get("contact_type") or row.get("platform") or "unknown",
            "status": row.get("status") or "",
            "bot_active": cls._coerce_bool(row.get("bot_active"), default=True),
            "last_message": latest_message.get("content", "") if latest_message else "",
            "last_message_at": last_message_at,
            "unread_count": cls._non_negative_int(row.get("unread_count"), default=0),
        }

    @classmethod
    def _latest_message(cls, raw_messages: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(raw_messages, list) or not raw_messages:
            return None

        return max(
            raw_messages,
            key=lambda msg: cls._parse_datetime(msg.get("created_at"))
            or datetime.min.replace(tzinfo=timezone.utc),
        )

    @classmethod
    def _resolve_last_message_at(
        cls,
        row: Dict[str, Any],
        latest_message: Optional[Dict[str, Any]],
    ) -> datetime:
        candidates = [
            latest_message.get("created_at") if latest_message else None,
            row.get("last_message_at"),
            row.get("updated_at"),
            row.get("created_at"),
        ]

        for candidate in candidates:
            parsed = cls._parse_datetime(candidate)
            if parsed is not None:
                return parsed

        return datetime.now(timezone.utc)

    @staticmethod
    def _coerce_bool(value: Any, *, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "t", "yes", "y", "on"}
        return bool(value)

    @staticmethod
    def _non_negative_int(value: Any, *, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return max(0, parsed)

    @staticmethod
    def _parse_datetime(value: Any) -> Optional[datetime]:
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
