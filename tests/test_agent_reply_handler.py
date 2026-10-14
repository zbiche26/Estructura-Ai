"""
Guard de idempotencia en agent_reply_handler — evita mensajes dobles.

Contexto del bug (ver spec/01-produccion-mvp.md, incidentes 2026-07-07
19:51 y 19:52 UTC): dos disparos de `agent.reply.requested` para el mismo
`whatsapp_message_id` terminaban generando y enviando dos respuestas
distintas al mismo cliente. La causa raíz exacta de por qué el handler se
ejecuta dos veces no se identificó; este guard protege al cliente sin
depender de encontrarla: reclama el derecho a responder con un UPDATE
condicional (`message_jobs.replied_at IS NULL`) antes de llamar al agente,
así que sin importar cuántas veces se dispare el handler, solo el primero
en llegar a la base de datos manda el mensaje.

test_sin_guard_dos_llamadas_concurrentes_mandan_dos_mensajes
    RED — caracteriza el bug: si nada bloquea, dos ejecuciones concurrentes
    del handler para el mismo whatsapp_message_id sí mandan 2 mensajes.

test_guard_bloquea_segundo_envio_duplicado
    GREEN — con el guard real activo, solo se manda 1 mensaje y el segundo
    intento queda bloqueado y logueado con el tag [GUARD].
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.event_bus import Event
from src.services import agent_reply_handler as handler_module

SAME_MESSAGE_ID = "wamid.TEST_DUPLICATE_MESSAGE_ID"


class _FakeMessageJobsTable:
    """Simula el UPDATE condicional WHERE replied_at IS NULL de message_jobs."""

    def __init__(self, claimed: set):
        self._claimed = claimed
        self._eq_value = None

    def update(self, _values):
        return self

    def eq(self, _col, value):
        self._eq_value = value
        return self

    def is_(self, _col, _value):
        return self

    def execute(self):
        if self._eq_value in self._claimed:
            return SimpleNamespace(data=[])
        self._claimed.add(self._eq_value)
        return SimpleNamespace(
            data=[{"id": "job-1", "whatsapp_message_id": self._eq_value}]
        )


class _FakeGenericTable:
    """Para otras tablas (conversations) que el handler toca de paso."""

    def update(self, _values):
        return self

    def eq(self, _col, _value):
        return self

    def execute(self):
        return SimpleNamespace(data=[])


class _FakeDbClient:
    def __init__(self, claimed: set):
        self._claimed = claimed

    def table(self, name):
        if name == "message_jobs":
            return _FakeMessageJobsTable(self._claimed)
        return _FakeGenericTable()


def _make_event() -> Event:
    return Event(
        event_type="agent.reply.requested",
        data={
            "conversation_id": "11111111-1111-1111-1111-111111111111",
            "input_text": "perfecto gracias.",
            "customer_phone": "573152172817",
            "customer_name": "Cliente Test",
            "source": "whatsapp",
            "message_id": SAME_MESSAGE_ID,
        },
        tenant_id="tenant-abc",
        metadata={"tenant_slug": "eje-inmobiliario"},
    )


def _make_tenant() -> SimpleNamespace:
    return SimpleNamespace(tenant_id="tenant-abc", tenant_name="Test Tenant")


def _make_orchestrator_mock() -> MagicMock:
    orchestrator = MagicMock()
    orchestrator.process_message = AsyncMock(
        return_value={
            "message": "Con gusto, que tengas buen día.",
            "intent": {"type": "farewell"},
        }
    )
    return orchestrator


@pytest.mark.asyncio
async def test_sin_guard_dos_llamadas_concurrentes_mandan_dos_mensajes():
    """RED: sin guard (_claim_reply siempre deja pasar), 2 disparos concurrentes
    para el mismo whatsapp_message_id mandan 2 mensajes por WhatsApp."""
    claimed: set = set()
    fake_db = _FakeDbClient(claimed)
    tenant = _make_tenant()
    orchestrator = _make_orchestrator_mock()

    with patch.object(handler_module, "_claim_reply", return_value=True), \
         patch.object(handler_module, "get_db", return_value=SimpleNamespace(client=fake_db)), \
         patch.object(handler_module, "load_tenant_context", return_value=tenant), \
         patch.object(handler_module, "get_agent_config", return_value={}), \
         patch.object(handler_module, "get_agent_name", return_value="Celeste"), \
         patch.object(handler_module, "create_agent_orchestrator", return_value=orchestrator), \
         patch.object(handler_module, "WhatsAppHandler") as mock_whatsapp_cls, \
         patch.object(handler_module, "MessageRepo"):

        event_a = _make_event()
        event_b = _make_event()

        await asyncio.gather(
            handler_module.handle_agent_reply(event_a),
            handler_module.handle_agent_reply(event_b),
        )

        assert mock_whatsapp_cls.return_value.send_message.call_count == 2


@pytest.mark.asyncio
async def test_guard_bloquea_segundo_envio_duplicado():
    """GREEN: con el guard real, 2 disparos concurrentes para el mismo
    whatsapp_message_id solo mandan 1 mensaje; el segundo queda bloqueado
    y logueado con el tag [GUARD]."""
    claimed: set = set()
    fake_db = _FakeDbClient(claimed)
    tenant = _make_tenant()
    orchestrator = _make_orchestrator_mock()

    with patch.object(handler_module, "get_db", return_value=SimpleNamespace(client=fake_db)), \
         patch.object(handler_module, "load_tenant_context", return_value=tenant), \
         patch.object(handler_module, "get_agent_config", return_value={}), \
         patch.object(handler_module, "get_agent_name", return_value="Celeste"), \
         patch.object(handler_module, "create_agent_orchestrator", return_value=orchestrator), \
         patch.object(handler_module, "WhatsAppHandler") as mock_whatsapp_cls, \
         patch.object(handler_module, "MessageRepo"), \
         patch.object(handler_module.logger, "warning") as mock_warning:

        event_a = _make_event()
        event_b = _make_event()

        await asyncio.gather(
            handler_module.handle_agent_reply(event_a),
            handler_module.handle_agent_reply(event_b),
        )

        assert mock_whatsapp_cls.return_value.send_message.call_count == 1

        guard_logs = [
            call.args[0]
            for call in mock_warning.call_args_list
            if call.args and "[GUARD] Envío duplicado bloqueado" in call.args[0]
        ]
        assert len(guard_logs) == 1
        assert SAME_MESSAGE_ID in guard_logs[0]


@pytest.mark.asyncio
async def test_claim_reply_gana_el_primero_y_bloquea_el_segundo():
    """Unidad: _claim_reply devuelve True una sola vez para el mismo id."""
    claimed: set = set()
    fake_db = _FakeDbClient(claimed)

    first = handler_module._claim_reply(SAME_MESSAGE_ID, fake_db)
    second = handler_module._claim_reply(SAME_MESSAGE_ID, fake_db)

    assert first is True
    assert second is False


def test_claim_reply_sin_message_id_no_bloquea():
    """Si no hay whatsapp_message_id (mensaje sintético), no se puede
    deduplicar — el guard debe dejar pasar en vez de bloquear todo."""
    fake_db = _FakeDbClient(set())

    assert handler_module._claim_reply("", fake_db) is True


def test_claim_reply_incluye_replied_by_en_el_update():
    """El claim de replied_at también debe guardar quién lo reclamó
    (hostname:pid) -- necesario para diagnosticar si dos procesos
    compiten por la misma cola (ver
    spec/07-investigacion-mensajes-duplicados-2026-07-07.md)."""
    captured: dict = {}

    class _CapturingTable:
        def update(self, values):
            captured.update(values)
            return self

        def eq(self, _col, _value):
            return self

        def is_(self, _col, _value):
            return self

        def execute(self):
            return SimpleNamespace(data=[{"id": "job-1"}])

    class _CapturingDb:
        def table(self, _name):
            return _CapturingTable()

    handler_module._claim_reply(SAME_MESSAGE_ID, _CapturingDb())

    assert "replied_by" in captured
    assert ":" in captured["replied_by"]
