"""
Usage Tracker Service - Sistema de tracking de uso por tenant

Este servicio gestiona el seguimiento de:
- Mensajes entrantes y salientes
- Storage usado (Supabase + Qdrant)
- Llamadas a APIs externas

Autores: EstructuraAI
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from src.core.database import get_db, SupabaseClient
from src.core.logger import logger
from src.config import settings


# ============================================
# Data Classes
# ============================================


@dataclass
class StorageBreakdown:
    """Desglose de almacenamiento por tipo"""

    products_mb: float = 0.0
    conversations_mb: float = 0.0
    messages_mb: float = 0.0
    vectors_mb: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        return {
            "products": self.products_mb,
            "conversations": self.conversations_mb,
            "messages": self.messages_mb,
            "vectors": self.vectors_mb,
        }


@dataclass
class UsageRecord:
    """Registro de uso para un día específico"""

    tenant_id: str
    record_date: date
    messages_count: int = 0
    messages_limit: int = 0
    storage_used_mb: float = 0.0
    storage_limit_mb: float = 0.0
    api_calls_count: int = 0
    api_calls_limit: int = 0
    storage_breakdown: Dict[str, float] = None

    def __post_init__(self):
        if self.storage_breakdown is None:
            self.storage_breakdown = {}


@dataclass
class MessageUsage:
    """Resumen de uso de mensajes"""

    total: int
    limit: int
    remaining: int
    percent_used: float


@dataclass
class StorageUsage:
    """Resumen de uso de storage"""

    total_mb: float
    limit_mb: float
    remaining_mb: float
    percent_used: float
    breakdown: Optional[Dict[str, float]] = None


# ============================================
# Message Tracker
# ============================================


class MessageTracker:
    """
    Tracker de mensajes de WhatsApp y otros canales.

    Usage:
        tracker = MessageTracker()
        tracker.record_message(tenant_id, direction="incoming")
        usage = tracker.get_message_usage(tenant_id, days=30)
    """

    def __init__(self, db: Optional[SupabaseClient] = None):
        self.db = db or get_db()

    def record_message(self, tenant_id: str, direction: str = "incoming") -> bool:
        today = date.today()

        try:
            existing = (
                self.db.client.table("usage_records")
                .select("messages_count")
                .eq("tenant_id", tenant_id)
                .eq("record_date", today.isoformat())
                .execute()
            )

            if existing.data and len(existing.data) > 0:
                current_count = existing.data[0].get("messages_count", 0) or 0
                self.db.client.table("usage_records").update(
                    {
                        "messages_count": current_count + 1,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                ).eq("tenant_id", tenant_id).eq(
                    "record_date", today.isoformat()
                ).execute()
            else:
                self.db.client.table("usage_records").insert(
                    {
                        "tenant_id": tenant_id,
                        "record_date": today.isoformat(),
                        "messages_count": 1,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                ).execute()

            logger.debug(f"Mensaje registrado para tenant {tenant_id}: {direction}")
            return True

        except Exception as e:
            # La tabla usage_records puede tener un esquema diferente en este entorno.
            # El tracking de uso es no crítico — no interrumpe el flujo principal.
            logger.debug(f"[USAGE] Tracking omitido para tenant {tenant_id}: {e}")
            return False

    def get_message_usage(self, tenant_id: str, days: int = 30) -> MessageUsage:
        from datetime import timedelta

        start_date = (date.today() - timedelta(days=days)).isoformat()

        try:
            # ✅ FIX 1: Corregido bug de string — coma estaba dentro del nombre del campo
            # ANTES (buggeado): .eq('tenant_id, tenant_id', tenant_id)
            # DESPUÉS (correcto): .eq('tenant_id', tenant_id)
            result = (
                self.db.client.table("usage_records")
                .select("messages_count, messages_limit, record_date")
                .eq("tenant_id", tenant_id)
                .gte("record_date", start_date)
                .execute()
            )

            if not result.data:
                return MessageUsage(total=0, limit=0, remaining=0, percent_used=0.0)

            total = sum(r.get("messages_count", 0) or 0 for r in result.data)

            latest = result.data[-1] if result.data else {}
            limit = latest.get("messages_limit", 0) or 0

            remaining = max(0, limit - total) if limit > 0 else -1
            percent = (total / limit * 100) if limit > 0 else 0.0

            return MessageUsage(
                total=total,
                limit=limit,
                remaining=remaining,
                percent_used=round(percent, 2),
            )

        except Exception as e:
            logger.error(
                f"Error obteniendo uso de mensajes para tenant {tenant_id}: {e}"
            )
            return MessageUsage(total=0, limit=0, remaining=0, percent_used=0.0)

    def get_today_count(self, tenant_id: str) -> int:
        today = date.today().isoformat()

        try:
            result = (
                self.db.client.table("usage_records")
                .select("messages_count")
                .eq("tenant_id", tenant_id)
                .eq("record_date", today)
                .execute()
            )

            if result.data and len(result.data) > 0:
                return result.data[0].get("messages_count", 0) or 0
            return 0

        except Exception as e:
            logger.error(
                f"Error obteniendo mensajes de hoy para tenant {tenant_id}: {e}"
            )
            return 0


# ============================================
# Storage Tracker
# ============================================


class StorageTracker:

    def __init__(self, db: Optional[SupabaseClient] = None):
        self.db = db or get_db()

    async def calculate_storage(self, tenant_id: str) -> Dict[str, Any]:
        breakdown = StorageBreakdown()

        breakdown.products_mb = await self._get_products_storage(tenant_id)
        breakdown.conversations_mb = await self._get_conversations_storage(tenant_id)
        breakdown.messages_mb = await self._get_messages_storage(tenant_id)

        supabase_total = (
            breakdown.products_mb + breakdown.conversations_mb + breakdown.messages_mb
        )

        breakdown.vectors_mb = await self._get_qdrant_storage(tenant_id)

        total = supabase_total + breakdown.vectors_mb

        return {
            "supabase_mb": round(supabase_total, 2),
            "qdrant_mb": round(breakdown.vectors_mb, 2),
            "total_mb": round(total, 2),
            "breakdown": breakdown.to_dict(),
        }

    async def _get_products_storage(self, tenant_id: str) -> float:
        try:
            result = (
                self.db.client.table("products")
                .select("id", count="exact")
                .eq("tenant_id", tenant_id)
                .execute()
            )
            count = result.count or 0
            return (count * 2) / 1024
        except Exception as e:
            logger.warning(f"Error calculando storage de productos: {e}")
            return 0.0

    async def _get_conversations_storage(self, tenant_id: str) -> float:
        try:
            result = (
                self.db.client.table("conversations")
                .select("id", count="exact")
                .eq("tenant_id", tenant_id)
                .execute()
            )
            count = result.count or 0
            return (count * 1) / 1024
        except Exception as e:
            logger.warning(f"Error calculando storage de conversaciones: {e}")
            return 0.0

    async def _get_messages_storage(self, tenant_id: str) -> float:
        try:
            result = (
                self.db.client.table("messages")
                .select("id", count="exact")
                .eq("tenant_id", tenant_id)
                .execute()
            )
            count = result.count or 0
            return (count * 0.5) / 1024
        except Exception as e:
            logger.warning(f"Error calculando storage de mensajes: {e}")
            return 0.0

    async def _get_qdrant_storage(self, tenant_id: str) -> float:
        try:
            from qdrant_client import QdrantClient
            from src.config import settings

            if settings.QDRANT_MODE == "memory":
                client = QdrantClient()
            elif settings.QDRANT_MODE == "grpc":
                client = QdrantClient(
                    host=settings.QDRANT_HOST or "localhost",
                    port=settings.QDRANT_GRPC_PORT or 6334,
                )
            else:
                client = QdrantClient(
                    url=settings.QDRANT_URL or "http://localhost:6333"
                )

            collection_name = f"products_{tenant_id}"

            try:
                info = client.get_collection(collection_name)
                vectors_count = info.vectors_count
                vector_dim = info.config.params.size
                size_bytes = vectors_count * vector_dim * 4
                size_mb = size_bytes / (1024 * 1024)
                return round(size_mb, 2)
            except Exception:
                return 0.0

        except ImportError:
            logger.warning("qdrant_client no instalado, saltando cálculo de vectors")
            return 0.0
        except Exception as e:
            logger.warning(f"Error calculando storage de Qdrant: {e}")
            return 0.0

    def record_storage(self, tenant_id: str, storage_data: Dict[str, Any]):
        today = date.today()
        try:
            self.db.client.table("usage_records").upsert(
                {
                    "tenant_id": tenant_id,
                    "record_date": today.isoformat(),
                    "storage_used_mb": storage_data.get("total_mb", 0),
                    "storage_breakdown": storage_data.get("breakdown", {}),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="tenant_id,record_date",
            ).execute()
            logger.debug(f"Storage registrado para tenant {tenant_id}")
        except Exception as e:
            logger.error(f"Error registrando storage para tenant {tenant_id}: {e}")


# ============================================
# API Call Tracker
# ============================================


class APICallTracker:

    def __init__(self, db: Optional[SupabaseClient] = None):
        self.db = db or get_db()

    def record_api_call(
        self,
        tenant_id: str,
        api_provider: str,
        endpoint: str,
        tokens_used: int = 0,
        cost: float = 0.0,
    ) -> bool:
        today = date.today()

        try:
            self.db.client.table("api_call_logs").insert(
                {
                    "tenant_id": tenant_id,
                    "api_provider": api_provider,
                    "endpoint": endpoint,
                    "tokens_used": tokens_used,
                    "cost_usd": cost,
                    "called_at": datetime.now(timezone.utc).isoformat(),
                }
            ).execute()

            existing = (
                self.db.client.table("usage_records")
                .select("api_calls_count")
                .eq("tenant_id", tenant_id)
                .eq("record_date", today.isoformat())
                .execute()
            )

            if existing.data and len(existing.data) > 0:
                current_count = existing.data[0].get("api_calls_count", 0) or 0
                self.db.client.table("usage_records").update(
                    {
                        "api_calls_count": current_count + 1,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                ).eq("tenant_id", tenant_id).eq(
                    "record_date", today.isoformat()
                ).execute()
            else:
                self.db.client.table("usage_records").insert(
                    {
                        "tenant_id": tenant_id,
                        "record_date": today.isoformat(),
                        "api_calls_count": 1,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                ).execute()

            logger.debug(
                f"API call registrada: {api_provider} {endpoint} para tenant {tenant_id}"
            )
            return True

        except Exception as e:
            logger.error(f"Error registrando API call para tenant {tenant_id}: {e}")
            return False

    def get_api_usage(self, tenant_id: str, days: int = 30) -> Dict[str, Any]:
        from datetime import timedelta

        start_date = (date.today() - timedelta(days=days)).isoformat()

        try:
            result = (
                self.db.client.table("usage_records")
                .select("api_calls_count, api_calls_limit")
                .eq("tenant_id", tenant_id)
                .gte("record_date", start_date)
                .execute()
            )

            total_calls = sum(r.get("api_calls_count", 0) or 0 for r in result.data)
            latest = result.data[-1] if result.data else {}
            limit = latest.get("api_calls_limit", 0) or 0

            provider_result = (
                self.db.client.table("api_call_logs")
                .select("api_provider")
                .eq("tenant_id", tenant_id)
                .gte("called_at", start_date)
                .execute()
            )

            by_provider: Dict[str, int] = {}
            for row in provider_result.data:
                provider = row.get("api_provider", "unknown")
                by_provider[provider] = by_provider.get(provider, 0) + 1

            tokens_result = (
                self.db.client.table("api_call_logs")
                .select("tokens_used")
                .eq("tenant_id", tenant_id)
                .gte("called_at", start_date)
                .execute()
            )

            total_tokens = sum(r.get("tokens_used", 0) or 0 for r in tokens_result.data)

            return {
                "total_calls": total_calls,
                "limit": limit,
                "remaining": max(0, limit - total_calls) if limit > 0 else -1,
                "by_provider": by_provider,
                "total_tokens": total_tokens,
            }

        except Exception as e:
            logger.error(f"Error obteniendo uso de API para tenant {tenant_id}: {e}")
            return {
                "total_calls": 0,
                "limit": 0,
                "remaining": 0,
                "by_provider": {},
                "total_tokens": 0,
            }

    def get_today_count(self, tenant_id: str) -> int:
        today = date.today().isoformat()
        try:
            result = (
                self.db.client.table("usage_records")
                .select("api_calls_count")
                .eq("tenant_id", tenant_id)
                .eq("record_date", today)
                .execute()
            )
            if result.data and len(result.data) > 0:
                return result.data[0].get("api_calls_count", 0) or 0
            return 0
        except Exception as e:
            logger.error(
                f"Error obteniendo API calls de hoy para tenant {tenant_id}: {e}"
            )
            return 0


# ============================================
# Daily Aggregation Job
# ============================================


async def aggregate_daily_usage():
    from src.services.tenant_service import get_all_active_tenants

    logger.info("Iniciando agregación diaria de uso...")

    db = get_db()
    message_tracker = MessageTracker(db)
    storage_tracker = StorageTracker(db)
    api_tracker = APICallTracker(db)
    today = date.today()

    try:
        tenants = get_all_active_tenants()
        logger.info(f"Procesando {len(tenants)} tenants")

        for tenant in tenants:
            tenant_id = tenant.tenant_id
            try:
                messages_count = message_tracker.get_today_count(tenant_id)
                storage = await storage_tracker.calculate_storage(tenant_id)
                api_calls = api_tracker.get_today_count(tenant_id)

                messages_limit = 100
                storage_limit_mb = 100.0
                api_calls_limit = 500

                db.client.table("usage_records").upsert(
                    {
                        "tenant_id": tenant_id,
                        "record_date": today.isoformat(),
                        "messages_count": messages_count,
                        "messages_limit": messages_limit,
                        "storage_used_mb": storage.get("total_mb", 0),
                        "storage_limit_mb": storage_limit_mb,
                        "api_calls_count": api_calls,
                        "api_calls_limit": api_calls_limit,
                        "storage_breakdown": storage.get("breakdown", {}),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                    on_conflict="tenant_id,record_date",
                ).execute()

                logger.debug(f"Uso registrado para tenant {tenant_id}")

            except Exception as e:
                logger.error(f"Error procesando tenant {tenant_id}: {e}")
                continue

        logger.info("Agregación diaria de uso completada")

    except Exception as e:
        logger.error(f"Error en agregación diaria de uso: {e}")


# ============================================
# Helper Functions
# ============================================


def get_usage_tracker() -> "UsageTracker":
    return UsageTracker()


class UsageTracker:

    def __init__(self):
        self.message = MessageTracker()
        self.storage = StorageTracker()
        self.api = APICallTracker()

    def record_message(self, tenant_id: str, direction: str = "incoming"):
        return self.message.record_message(tenant_id, direction)

    async def calculate_storage(self, tenant_id: str) -> Dict[str, Any]:
        return await self.storage.calculate_storage(tenant_id)

    def record_api_call(
        self, tenant_id: str, api_provider: str, endpoint: str, tokens_used: int = 0
    ):
        return self.api.record_api_call(tenant_id, api_provider, endpoint, tokens_used)

    def get_full_usage(self, tenant_id: str) -> Dict[str, Any]:
        messages = self.message.get_message_usage(tenant_id)
        api = self.api.get_api_usage(tenant_id)

        return {
            "messages": {
                "total": messages.total,
                "limit": messages.limit,
                "remaining": messages.remaining,
                "percent_used": messages.percent_used,
            },
            "api_calls": {
                "total": api["total_calls"],
                "limit": api["limit"],
                "remaining": api["remaining"],
                "by_provider": api["by_provider"],
                "total_tokens": api["total_tokens"],
            },
        }
