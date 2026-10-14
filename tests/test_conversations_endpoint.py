from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from src.core.tenant_context import TenantContext
from src.http.app import app


client = TestClient(app)


def _auth_headers() -> dict[str, str]:
    return {
        "X-Tenant-Id": "tenant-test-123",
        "Authorization": "Bearer demo-token",
    }


def _stub_tenant_context(monkeypatch) -> None:
    def fake_load_tenant_context(identifier: str) -> TenantContext:
        return TenantContext(
            tenant_id=str(identifier),
            tenant_name="Tenant Test",
            plan="trial",
            features_enabled=[],
            config={},
        )

    monkeypatch.setattr(
        "src.services.tenant_service.load_tenant_context",
        fake_load_tenant_context,
    )
    monkeypatch.setattr(
        "src.http.app.load_tenant_context",
        fake_load_tenant_context,
    )


class TestConversationsEndpoint:
    def test_get_conversations_contract_and_filters(self, monkeypatch):
        _stub_tenant_context(monkeypatch)
        captured: dict[str, object] = {}

        def _fake_list_conversations(self, **kwargs):
            captured.update(kwargs)
            return {
                "data": [
                    {
                        "id": "d14f713d-1f08-4f8a-87d5-59ec9ff3f37d",
                        "phone": "+573001234567",
                        "contact_name": "Juan Perez",
                        "contact_type": "whatsapp",
                        "status": "active",
                        "bot_active": True,
                        "last_message": "Hola, necesito ayuda",
                        "last_message_at": datetime(2026, 4, 14, 18, 30, tzinfo=timezone.utc),
                        "unread_count": 0,
                    }
                ],
                "total": 100,
                "page": kwargs["page"],
                "page_size": kwargs["page_size"],
            }

        monkeypatch.setattr(
            "src.http.routers.conversations.ConversationRepo.list_conversations",
            _fake_list_conversations,
        )

        response = client.get(
            "/api/v1/conversations",
            params={
                "page": 1,
                "page_size": 20,
                "status": "active",
                "contact_type": "whatsapp",
            },
            headers=_auth_headers(),
        )

        assert response.status_code == 200
        payload = response.json()

        assert list(payload.keys()) == ["data", "total", "page", "page_size"]
        assert payload["total"] == 100
        assert payload["page"] == 1
        assert payload["page_size"] == 20

        item = payload["data"][0]
        assert list(item.keys()) == [
            "id",
            "phone",
            "contact_name",
            "contact_type",
            "status",
            "bot_active",
            "last_message",
            "last_message_at",
            "unread_count",
        ]
        assert item["last_message_at"] == "2026-04-14T18:30:00.000Z"

        assert captured["tenant_id"] == "tenant-test-123"
        assert captured["page"] == 1
        assert captured["page_size"] == 20
        assert captured["status"] == "active"
        assert captured["contact_type"] == "whatsapp"

    def test_get_conversations_uses_defaults(self, monkeypatch):
        _stub_tenant_context(monkeypatch)
        captured: dict[str, object] = {}

        def _fake_list_conversations(self, **kwargs):
            captured.update(kwargs)
            return {
                "data": [],
                "total": 0,
                "page": kwargs["page"],
                "page_size": kwargs["page_size"],
            }

        monkeypatch.setattr(
            "src.http.routers.conversations.ConversationRepo.list_conversations",
            _fake_list_conversations,
        )

        response = client.get("/api/v1/conversations", headers=_auth_headers())

        assert response.status_code == 200
        payload = response.json()
        assert payload == {
            "data": [],
            "total": 0,
            "page": 1,
            "page_size": 20,
        }

        assert captured["page"] == 1
        assert captured["page_size"] == 20
        assert captured["status"] is None
        assert captured["contact_type"] is None

    def test_get_conversations_validates_page_size_max(self, monkeypatch):
        _stub_tenant_context(monkeypatch)
        response = client.get(
            "/api/v1/conversations",
            params={"page_size": 101},
            headers=_auth_headers(),
        )

        assert response.status_code == 422

    def test_patch_conversation_returns_full_item_and_only_sent_fields(self, monkeypatch):
        _stub_tenant_context(monkeypatch)
        captured: dict[str, object] = {}

        def _fake_update_conversation(self, **kwargs):
            captured.update(kwargs)
            return {
                "id": kwargs["conversation_id"],
                "phone": "+573001234567",
                "contact_name": "Ana Gomez",
                "contact_type": "whatsapp",
                "status": "active",
                "bot_active": False,
                "last_message": "Listo, te ayudo",
                "last_message_at": datetime(2026, 4, 16, 20, 0, tzinfo=timezone.utc),
                "unread_count": 1,
            }

        monkeypatch.setattr(
            "src.http.routers.conversations.ConversationRepo.update_conversation",
            _fake_update_conversation,
        )

        response = client.patch(
            "/api/v1/conversations/conv-123",
            json={"bot_active": False, "contact_name": "  Ana Gomez  "},
            headers=_auth_headers(),
        )

        assert response.status_code == 200
        payload = response.json()
        assert list(payload.keys()) == [
            "id",
            "phone",
            "contact_name",
            "contact_type",
            "status",
            "bot_active",
            "last_message",
            "last_message_at",
            "unread_count",
        ]
        assert payload["id"] == "conv-123"
        assert payload["last_message_at"] == "2026-04-16T20:00:00.000Z"

        assert captured["tenant_id"] == "tenant-test-123"
        assert captured["conversation_id"] == "conv-123"
        assert captured["updates"] == {
            "bot_active": False,
            "contact_name": "  Ana Gomez  ",
        }

    def test_patch_conversation_returns_404_when_not_found(self, monkeypatch):
        _stub_tenant_context(monkeypatch)

        monkeypatch.setattr(
            "src.http.routers.conversations.ConversationRepo.update_conversation",
            lambda self, **kwargs: None,
        )

        response = client.patch(
            "/api/v1/conversations/conv-missing",
            json={"contact_name": "Nuevo"},
            headers=_auth_headers(),
        )

        assert response.status_code == 404

    def test_post_manual_message_returns_404_when_conversation_not_found(self, monkeypatch):
        _stub_tenant_context(monkeypatch)

        monkeypatch.setattr(
            "src.http.routers.conversations.MessageRepo.get_conversation_for_tenant",
            lambda self, **kwargs: None,
        )

        response = client.post(
            "/api/v1/conversations/conv-missing/messages",
            json={"content": "Hola desde agente"},
            headers=_auth_headers(),
        )

        assert response.status_code == 404

    def test_post_manual_message_returns_409_when_bot_active(self, monkeypatch):
        _stub_tenant_context(monkeypatch)

        monkeypatch.setattr(
            "src.http.routers.conversations.MessageRepo.get_conversation_for_tenant",
            lambda self, **kwargs: {
                "id": "conv-1",
                "tenant_id": "tenant-test-123",
                "bot_active": True,
                "phone": "+573001234567",
            },
        )

        response = client.post(
            "/api/v1/conversations/conv-1/messages",
            json={"content": "Hola desde agente"},
            headers=_auth_headers(),
        )

        assert response.status_code == 409
        assert response.json()["detail"] == "El bot debe estar desactivado para enviar mensajes manuales"

    def test_post_manual_message_returns_422_when_window_expired(self, monkeypatch):
        _stub_tenant_context(monkeypatch)

        monkeypatch.setattr(
            "src.http.routers.conversations.MessageRepo.get_conversation_for_tenant",
            lambda self, **kwargs: {
                "id": "conv-2",
                "tenant_id": "tenant-test-123",
                "bot_active": False,
                "phone": "+573001234567",
            },
        )
        monkeypatch.setattr(
            "src.http.routers.conversations.MessageRepo.get_last_contact_message_at",
            lambda self, **kwargs: datetime.now(timezone.utc) - timedelta(hours=25),
        )

        response = client.post(
            "/api/v1/conversations/conv-2/messages",
            json={"content": "Hola desde agente"},
            headers=_auth_headers(),
        )

        assert response.status_code == 422
        assert response.json() == {
            "error": "ventana_expirada",
            "templates_disponibles": [],
        }

    def test_post_manual_message_sends_and_persists(self, monkeypatch):
        _stub_tenant_context(monkeypatch)
        captured: dict[str, object] = {}

        monkeypatch.setattr(
            "src.http.routers.conversations.MessageRepo.get_conversation_for_tenant",
            lambda self, **kwargs: {
                "id": "conv-3",
                "tenant_id": "tenant-test-123",
                "bot_active": False,
                "phone": "+573001234567",
            },
        )
        monkeypatch.setattr(
            "src.http.routers.conversations.MessageRepo.get_last_contact_message_at",
            lambda self, **kwargs: datetime.now(timezone.utc) - timedelta(hours=1),
        )

        def _fake_send_text_message(*, to: str, content: str):
            captured["wa_to"] = to
            captured["wa_content"] = content
            return {"messages": [{"id": "wamid.123"}]}

        monkeypatch.setattr(
            "src.http.routers.conversations.whatsapp_service.send_text_message",
            _fake_send_text_message,
        )

        def _fake_persist(self, **kwargs):
            captured.update(kwargs)
            return {
                "id": "msg-1",
                "content": kwargs["content"],
                "sender": "agent",
                "status": "sent",
                "sent_at": datetime(2026, 4, 17, 16, 0, tzinfo=timezone.utc),
            }

        monkeypatch.setattr(
            "src.http.routers.conversations.MessageRepo.persist_manual_agent_message",
            _fake_persist,
        )

        response = client.post(
            "/api/v1/conversations/conv-3/messages",
            json={"content": "  Mensaje manual  "},
            headers=_auth_headers(),
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload == {
            "id": "msg-1",
            "content": "Mensaje manual",
            "sender": "agent",
            "status": "sent",
            "sent_at": "2026-04-17T16:00:00.000Z",
        }

        assert captured["wa_to"] == "+573001234567"
        assert captured["wa_content"] == "Mensaje manual"
        assert captured["tenant_id"] == "tenant-test-123"
        assert captured["conversation_id"] == "conv-3"
        assert captured["content"] == "Mensaje manual"

    def test_post_read_marks_conversation_as_read(self, monkeypatch):
        _stub_tenant_context(monkeypatch)
        captured: dict[str, object] = {}

        def _fake_mark_as_read(self, **kwargs):
            captured.update(kwargs)
            return True

        monkeypatch.setattr(
            "src.http.routers.conversations.ConversationRepo.mark_as_read",
            _fake_mark_as_read,
        )

        response = client.post(
            "/api/v1/conversations/conv-read/read",
            headers=_auth_headers(),
        )

        assert response.status_code == 200
        assert response.json() == {"ok": True}
        assert captured["tenant_id"] == "tenant-test-123"
        assert captured["conversation_id"] == "conv-read"

    def test_post_read_returns_404_when_conversation_not_found(self, monkeypatch):
        _stub_tenant_context(monkeypatch)

        monkeypatch.setattr(
            "src.http.routers.conversations.ConversationRepo.mark_as_read",
            lambda self, **kwargs: False,
        )

        response = client.post(
            "/api/v1/conversations/conv-missing/read",
            headers=_auth_headers(),
        )

        assert response.status_code == 404
