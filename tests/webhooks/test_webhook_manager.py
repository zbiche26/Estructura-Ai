# -*- coding: utf-8 -*-
"""
test_webhook_manager.py - Tests del WebhookManager
===================================================
Ejecutar: pytest tests/webhooks/test_webhook_manager.py -v
"""

import pytest
from src.webhooks.webhook_manager import (
    WebhookManager,
    WebhookConfig,
    WebhookRecord,
    WEBHOOK_EVENTS,
)


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def manager() -> WebhookManager:
    return WebhookManager(dry_run=True)


@pytest.fixture
def config_ventas() -> WebhookConfig:
    return WebhookConfig(
        name="Notificar ventas",
        url="https://mi-servidor.com/webhooks",
        events=["sale.created", "sale.completed"],
    )


@pytest.fixture
def config_stock() -> WebhookConfig:
    return WebhookConfig(
        name="Alertas stock",
        url="https://otro-servidor.com/hooks",
        events=["product.low_stock", "product.out_of_stock"],
    )


# ── Tests: WebhookConfig.validate ────────────────────────────


class TestWebhookConfigValidate:

    def test_config_valida(self, config_ventas):
        assert config_ventas.validate() == []

    def test_sin_nombre_error(self):
        c = WebhookConfig(name="", url="https://x.com", events=["sale.created"])
        assert any("nombre" in e for e in c.validate())

    def test_sin_url_error(self):
        c = WebhookConfig(name="Test", url="", events=["sale.created"])
        assert any("URL" in e for e in c.validate())

    def test_url_sin_https_error(self):
        c = WebhookConfig(name="T", url="ftp://bad.com", events=["sale.created"])
        assert any("http" in e for e in c.validate())

    def test_sin_eventos_error(self):
        c = WebhookConfig(name="T", url="https://x.com", events=[])
        assert any("evento" in e for e in c.validate())

    def test_evento_invalido_error(self):
        c = WebhookConfig(name="T", url="https://x.com", events=["evento.fake"])
        assert any("inválido" in e for e in c.validate())

    def test_eventos_validos_no_error(self):
        for event in WEBHOOK_EVENTS:
            c = WebhookConfig(name="T", url="https://x.com", events=[event])
            assert c.validate() == []


# ── Tests: WebhookRecord ──────────────────────────────────────


class TestWebhookRecord:

    def test_sign_payload(self):
        w = WebhookRecord(
            id="1",
            tenant_id="t1",
            name="W",
            url="https://x.com",
            secret="test-secret",
            events=["sale.created"],
        )
        sig = w.sign_payload('{"event": "sale.created"}')
        assert sig.startswith("sha256=")
        assert len(sig) > 10

    def test_sign_payload_consistente(self):
        w = WebhookRecord(
            id="1",
            tenant_id="t1",
            name="W",
            url="https://x.com",
            secret="test-secret",
            events=["sale.created"],
        )
        payload = '{"test": "data"}'
        assert w.sign_payload(payload) == w.sign_payload(payload)

    def test_listens_to_true(self, manager, config_ventas):
        w = manager.create("tenant_a", config_ventas)
        assert w.listens_to("sale.created") is True

    def test_listens_to_false(self, manager, config_ventas):
        w = manager.create("tenant_a", config_ventas)
        assert w.listens_to("product.low_stock") is False

    def test_to_dict_tiene_campos(self, manager, config_ventas):
        w = manager.create("tenant_a", config_ventas)
        d = w.to_dict()
        assert "id" in d
        assert "tenant_id" in d
        assert "secret" in d
        assert "events" in d

    def test_repr(self, manager, config_ventas):
        w = manager.create("tenant_a", config_ventas)
        assert "Notificar ventas" in repr(w)


# ── Tests: create ─────────────────────────────────────────────


class TestCreate:

    def test_crea_webhook(self, manager, config_ventas):
        w = manager.create("tenant_a", config_ventas)
        assert isinstance(w, WebhookRecord)

    def test_genera_id(self, manager, config_ventas):
        w = manager.create("tenant_a", config_ventas)
        assert w.id != ""

    def test_genera_secret(self, manager, config_ventas):
        w = manager.create("tenant_a", config_ventas)
        assert w.secret.startswith("whsec_")
        assert len(w.secret) > 10

    def test_secret_unico(self, manager, config_ventas):
        w1 = manager.create("tenant_a", config_ventas)
        w2 = manager.create("tenant_a", config_ventas)
        assert w1.secret != w2.secret

    def test_config_invalida_lanza_error(self, manager):
        with pytest.raises(ValueError):
            manager.create("tenant_a", WebhookConfig(name="", url="", events=[]))

    def test_tenant_correcto(self, manager, config_ventas):
        w = manager.create("mi_tenant", config_ventas)
        assert w.tenant_id == "mi_tenant"


# ── Tests: get ────────────────────────────────────────────────


class TestGet:

    def test_get_existente(self, manager, config_ventas):
        w = manager.create("tenant_a", config_ventas)
        result = manager.get(w.id, "tenant_a")
        assert result is not None
        assert result.id == w.id

    def test_get_inexistente_retorna_none(self, manager):
        result = manager.get("id-no-existe", "tenant_a")
        assert result is None

    def test_get_otro_tenant_retorna_none(self, manager, config_ventas):
        w = manager.create("tenant_a", config_ventas)
        result = manager.get(w.id, "tenant_b")
        assert result is None


# ── Tests: list ───────────────────────────────────────────────


class TestList:

    def test_lista_webhooks_del_tenant(self, manager, config_ventas, config_stock):
        manager.create("tenant_a", config_ventas)
        manager.create("tenant_a", config_stock)
        result = manager.list("tenant_a")
        assert len(result) == 2

    def test_lista_aislada_por_tenant(self, manager, config_ventas):
        manager.create("tenant_a", config_ventas)
        manager.create("tenant_b", config_ventas)
        result_a = manager.list("tenant_a")
        result_b = manager.list("tenant_b")
        assert len(result_a) == 1
        assert len(result_b) == 1

    def test_lista_solo_activos(self, manager, config_ventas):
        w = manager.create("tenant_a", config_ventas)
        manager.update(w.id, "tenant_a", {"is_active": False})
        result = manager.list("tenant_a", active_only=True)
        assert len(result) == 0


# ── Tests: update ─────────────────────────────────────────────


class TestUpdate:

    def test_actualiza_nombre(self, manager, config_ventas):
        w = manager.create("tenant_a", config_ventas)
        result = manager.update(w.id, "tenant_a", {"name": "Nuevo nombre"})
        assert result.name == "Nuevo nombre"

    def test_desactiva_webhook(self, manager, config_ventas):
        w = manager.create("tenant_a", config_ventas)
        result = manager.update(w.id, "tenant_a", {"is_active": False})
        assert result.is_active is False

    def test_inexistente_retorna_none(self, manager):
        result = manager.update("id-no-existe", "tenant_a", {"name": "X"})
        assert result is None


# ── Tests: delete ─────────────────────────────────────────────


class TestDelete:

    def test_elimina_webhook(self, manager, config_ventas):
        w = manager.create("tenant_a", config_ventas)
        assert manager.delete(w.id, "tenant_a") is True
        assert manager.get(w.id, "tenant_a") is None

    def test_inexistente_retorna_false(self, manager):
        assert manager.delete("no-existe", "tenant_a") is False

    def test_otro_tenant_no_puede_eliminar(self, manager, config_ventas):
        w = manager.create("tenant_a", config_ventas)
        assert manager.delete(w.id, "tenant_b") is False


# ── Tests: get_listeners ──────────────────────────────────────


class TestGetListeners:

    def test_retorna_webhooks_del_evento(self, manager, config_ventas, config_stock):
        manager.create("tenant_a", config_ventas)
        manager.create("tenant_a", config_stock)
        listeners = manager.get_listeners("tenant_a", "sale.created")
        assert len(listeners) == 1
        assert listeners[0].name == "Notificar ventas"

    def test_sin_listeners_lista_vacia(self, manager):
        result = manager.get_listeners("tenant_a", "sale.created")
        assert result == []

    def test_inactivo_no_aparece(self, manager, config_ventas):
        w = manager.create("tenant_a", config_ventas)
        manager.update(w.id, "tenant_a", {"is_active": False})
        result = manager.get_listeners("tenant_a", "sale.created")
        assert result == []
