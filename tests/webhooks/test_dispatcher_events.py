# -*- coding: utf-8 -*-
"""
test_dispatcher_events.py - Tests del Dispatcher y Events
==========================================================
Ejecutar: pytest tests/webhooks/test_dispatcher_events.py -v
"""

import pytest
from src.webhooks.webhook_manager import WebhookManager, WebhookConfig, WebhookRecord
from src.webhooks.dispatcher import WebhookDispatcher, DeliveryResult
from src.webhooks.events import EventEmitter, EventType


# ── Helpers ───────────────────────────────────────────────────


def make_webhook(
    tenant_id: str = "tenant_a",
    events: list = None,
) -> WebhookRecord:
    manager = WebhookManager(dry_run=True)
    return manager.create(
        tenant_id,
        WebhookConfig(
            name="Test Webhook",
            url="https://ejemplo.com/webhook",
            events=events or ["sale.created"],
        ),
    )


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def dispatcher() -> WebhookDispatcher:
    return WebhookDispatcher(dry_run=True)


@pytest.fixture
def manager() -> WebhookManager:
    return WebhookManager(dry_run=True)


@pytest.fixture
def emitter(manager, dispatcher) -> EventEmitter:
    return EventEmitter(manager=manager, dispatcher=dispatcher)


# ── Tests: DeliveryResult ─────────────────────────────────────


class TestDeliveryResult:

    def test_repr_contiene_event(self):
        r = DeliveryResult(event_type="sale.created", success=True)
        assert "sale.created" in repr(r)

    def test_success_false_por_defecto(self):
        r = DeliveryResult()
        assert r.success is False


# ── Tests: WebhookDispatcher ──────────────────────────────────


class TestWebhookDispatcher:

    def test_dispatch_dry_run_exitoso(self, dispatcher):
        webhook = make_webhook()
        result = dispatcher.dispatch(webhook, "sale.created", {"total": 100})
        assert result.success is True
        assert result.status_code == 200
        assert result.attempts == 1

    def test_dispatch_registra_delivery_id(self, dispatcher):
        webhook = make_webhook()
        result = dispatcher.dispatch(webhook, "sale.created", {})
        assert result.delivery_id != ""

    def test_dispatch_registra_tenant_id(self, dispatcher):
        webhook = make_webhook(tenant_id="mi_tenant")
        result = dispatcher.dispatch(webhook, "sale.created", {})
        assert result.tenant_id == "mi_tenant"

    def test_dispatch_mide_duracion(self, dispatcher):
        webhook = make_webhook()
        result = dispatcher.dispatch(webhook, "sale.created", {})
        assert result.duration_ms >= 0

    def test_dispatch_to_all(self, dispatcher):
        webhooks = [make_webhook(), make_webhook()]
        results = dispatcher.dispatch_to_all(webhooks, "sale.created", {"total": 100})
        assert len(results) == 2
        assert all(r.success for r in results)

    def test_delivery_log_acumula(self, dispatcher):
        webhook = make_webhook()
        dispatcher.dispatch(webhook, "sale.created", {})
        dispatcher.dispatch(webhook, "sale.completed", {})
        log = dispatcher.get_delivery_log()
        assert len(log) == 2

    def test_delivery_log_filtrado_por_webhook(self, dispatcher):
        w1 = make_webhook()
        w2 = make_webhook()
        dispatcher.dispatch(w1, "sale.created", {})
        dispatcher.dispatch(w2, "sale.created", {})
        log = dispatcher.get_delivery_log(webhook_id=w1.id)
        assert len(log) == 1

    def test_get_stats_exitosos(self, dispatcher):
        webhook = make_webhook()
        dispatcher.dispatch(webhook, "sale.created", {})
        dispatcher.dispatch(webhook, "sale.created", {})
        stats = dispatcher.get_stats()
        assert stats["total"] == 2
        assert stats["successful"] == 2
        assert stats["failed"] == 0

    def test_build_payload_tiene_campos(self, dispatcher):
        payload = dispatcher._build_payload(
            event_type="sale.created",
            data={"total": 100},
            delivery_id="test-id",
            tenant_id="tenant_a",
        )
        assert payload["event"] == "sale.created"
        assert payload["tenant_id"] == "tenant_a"
        assert payload["id"] == "test-id"
        assert "timestamp" in payload
        assert payload["data"]["total"] == 100

    def test_build_headers_tiene_firma(self, dispatcher):
        webhook = make_webhook()
        headers = dispatcher._build_headers(webhook, '{"test": 1}')
        assert "X-Signature-256" in headers
        assert headers["X-Signature-256"].startswith("sha256=")

    def test_firma_hmac_consistente(self, dispatcher):
        webhook = make_webhook()
        payload = '{"event": "sale.created"}'
        headers1 = dispatcher._build_headers(webhook, payload)
        headers2 = dispatcher._build_headers(webhook, payload)
        assert headers1["X-Signature-256"] == headers2["X-Signature-256"]


# ── Tests: EventType ──────────────────────────────────────────


class TestEventType:

    def test_all_retorna_8_eventos(self):
        assert len(EventType.all()) == 8

    def test_contiene_sale_created(self):
        assert "sale.created" in EventType.all()

    def test_contiene_import_completed(self):
        assert "import.completed" in EventType.all()

    def test_todos_los_eventos_tienen_punto(self):
        for event in EventType.all():
            assert "." in event


# ── Tests: EventEmitter ───────────────────────────────────────


class TestEventEmitter:

    def _setup_webhook(self, manager: WebhookManager, events: list) -> WebhookRecord:
        return manager.create(
            "tenant_a", WebhookConfig(name="W", url="https://x.com/hook", events=events)
        )

    def test_sale_created_notifica(self, emitter, manager):
        self._setup_webhook(manager, ["sale.created"])
        results = emitter.sale_created("tenant_a", {"total": 180_000})
        assert len(results) == 1
        assert results[0].success is True

    def test_sale_completed_notifica(self, emitter, manager):
        self._setup_webhook(manager, ["sale.completed"])
        results = emitter.sale_completed("tenant_a", {"sale_id": "123"})
        assert len(results) == 1

    def test_product_low_stock_notifica(self, emitter, manager):
        self._setup_webhook(manager, ["product.low_stock"])
        results = emitter.product_low_stock("tenant_a", {"product_name": "Cam"})
        assert len(results) == 1

    def test_product_out_of_stock_notifica(self, emitter, manager):
        self._setup_webhook(manager, ["product.out_of_stock"])
        results = emitter.product_out_of_stock("tenant_a", {"product_id": "p1"})
        assert len(results) == 1

    def test_conversation_started_notifica(self, emitter, manager):
        self._setup_webhook(manager, ["conversation.started"])
        results = emitter.conversation_started("tenant_a", {"phone": "+57300"})
        assert len(results) == 1

    def test_conversation_closed_notifica(self, emitter, manager):
        self._setup_webhook(manager, ["conversation.closed"])
        results = emitter.conversation_closed("tenant_a", {"duration_min": 5})
        assert len(results) == 1

    def test_import_completed_notifica(self, emitter, manager):
        self._setup_webhook(manager, ["import.completed"])
        results = emitter.import_completed(
            "tenant_a", {"saved_count": 25, "file_name": "props.xlsx"}
        )
        assert len(results) == 1

    def test_import_failed_notifica(self, emitter, manager):
        self._setup_webhook(manager, ["import.failed"])
        results = emitter.import_failed("tenant_a", {"error": "columna faltante"})
        assert len(results) == 1

    def test_sin_listeners_retorna_vacio(self, emitter):
        results = emitter.sale_created("tenant_sin_webhooks", {"total": 100})
        assert results == []

    def test_webhook_inactivo_no_notifica(self, emitter, manager):
        w = self._setup_webhook(manager, ["sale.created"])
        manager.update(w.id, "tenant_a", {"is_active": False})
        results = emitter.sale_created("tenant_a", {"total": 100})
        assert results == []

    def test_agrega_timestamp_si_falta(self, emitter, manager):
        self._setup_webhook(manager, ["sale.created"])
        data = {"total": 100}
        emitter.sale_created("tenant_a", data)
        assert "timestamp" in data

    def test_multiples_webhooks_mismo_evento(self, emitter, manager):
        manager.create(
            "tenant_a",
            WebhookConfig(name="W1", url="https://a.com", events=["sale.created"]),
        )
        manager.create(
            "tenant_a",
            WebhookConfig(name="W2", url="https://b.com", events=["sale.created"]),
        )
        results = emitter.sale_created("tenant_a", {"total": 100})
        assert len(results) == 2
