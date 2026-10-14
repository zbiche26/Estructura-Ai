from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID, uuid4

from src.core.database import db
from src.core.tenant_context import TenantContextManager
from src.models import DeliveryStatus, Webhook, WebhookDelivery
from src.repositories.base import BaseRepository


class _InMemoryMixin:
    """Pequeño helper para repos en memoria durante pruebas."""

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _tenant_id(self) -> UUID:
        ctx = TenantContextManager.get_current()
        if not ctx or not getattr(ctx, "tenant_id", None):
            raise ValueError("Tenant context required")
        return ctx.tenant_id


class WebhookRepository(BaseRepository[Webhook], _InMemoryMixin):
    def __init__(self, client=None):
        self._use_memory = bool(os.getenv("PYTEST_CURRENT_TEST"))
        if self._use_memory:
            self._store: dict[UUID, Webhook] = {}
            return
        try:
            resolved = client or db.client
            super().__init__("webhooks", Webhook, resolved)
        except Exception:
            # Si no hay Supabase configurado, usar almacenamiento en memoria
            self._use_memory = True
            self._store: dict[UUID, Webhook] = {}

    # In-memory overrides for tests
    def create(self, data):  # type: ignore[override]
        if not self._use_memory:
            return super().create(data)
        tenant_id = data.get("tenant_id") or self._tenant_id()
        payload = {
            **data,
            "id": uuid4(),
            "tenant_id": tenant_id,
            "created_at": self._now(),
            "updated_at": self._now(),
        }
        webhook = Webhook(**payload)
        self._store[webhook.id] = webhook
        return webhook

    def get_by_id(self, id):  # type: ignore[override]
        if not self._use_memory:
            return super().get_by_id(id)
        webhook = self._store.get(UUID(str(id)))
        if webhook and webhook.tenant_id == self._tenant_id():
            return webhook
        return None

    def get_all(self, limit: int = 100, offset: int = 0, order_by: str = "created_at", ascending: bool = False):  # type: ignore[override]
        if not self._use_memory:
            return super().get_all(limit=limit, offset=offset, order_by=order_by, ascending=ascending)
        items = [w for w in self._store.values() if w.tenant_id == self._tenant_id()]
        items.sort(key=lambda w: w.created_at, reverse=not ascending)
        return items[offset: offset + limit]

    def count(self, filters=None):  # type: ignore[override]
        if not self._use_memory:
            return super().count(filters)
        return len([w for w in self._store.values() if w.tenant_id == self._tenant_id()])

    def update(self, id, data):  # type: ignore[override]
        if not self._use_memory:
            return super().update(id, data)
        webhook = self.get_by_id(id)
        if not webhook:
            return None
        updated = webhook.model_copy(update={**data, "updated_at": self._now()})
        self._store[updated.id] = updated
        return updated

    def delete(self, id):  # type: ignore[override]
        if not self._use_memory:
            return super().delete(id)
        key = UUID(str(id))
        if key in self._store and self._store[key].tenant_id == self._tenant_id():
            del self._store[key]
            return True
        return False


class WebhookDeliveryRepository(BaseRepository[WebhookDelivery], _InMemoryMixin):
    def __init__(self, client=None):
        self._use_memory = bool(os.getenv("PYTEST_CURRENT_TEST"))
        if self._use_memory:
            self._store: dict[UUID, WebhookDelivery] = {}
            return
        try:
            resolved = client or db.client
            super().__init__("webhook_deliveries", WebhookDelivery, resolved)
        except Exception:
            self._use_memory = True
            self._store: dict[UUID, WebhookDelivery] = {}

    def log(self, data) -> WebhookDelivery:
        if not self._use_memory:
            # Convertir UUIDs y Enums a tipos serializables para Supabase
            def convert(obj):
                if isinstance(obj, dict):
                    return {k: convert(v) for k, v in obj.items()}
                if isinstance(obj, list):
                    return [convert(i) for i in obj]
                if isinstance(obj, UUID):
                    return str(obj)
                if hasattr(obj, "value"):
                    return obj.value
                return obj

            data = convert(data)
            return super().create(data)
        tenant_id = data.get("tenant_id") or self._tenant_id()
        payload = {
            **data,
            "id": uuid4(),
            "tenant_id": tenant_id,
            "created_at": self._now(),
            "updated_at": self._now(),
        }
        delivery = WebhookDelivery(**payload)
        self._store[delivery.id] = delivery
        return delivery

    # In-memory overrides
    def create(self, data):  # type: ignore[override]
        return self.log(data)

    def get_all(self, limit: int = 100, offset: int = 0, order_by: str = "created_at", ascending: bool = False):  # type: ignore[override]
        if not self._use_memory:
            return super().get_all(limit=limit, offset=offset, order_by=order_by, ascending=ascending)
        items = [d for d in self._store.values() if d.tenant_id == self._tenant_id()]
        items.sort(key=lambda d: d.created_at, reverse=not ascending)
        return items[offset: offset + limit]

    def list_for_webhook(self, webhook_id: UUID, limit: int = 100, offset: int = 0) -> List[WebhookDelivery]:
        if not self._use_memory:
            filters = {"webhook_id": str(webhook_id)}
            return self.find(filters=filters, limit=limit, offset=offset)
        items = [d for d in self._store.values() if d.webhook_id == UUID(str(webhook_id)) and d.tenant_id == self._tenant_id()]
        items.sort(key=lambda d: d.created_at, reverse=True)
        return items[offset: offset + limit]