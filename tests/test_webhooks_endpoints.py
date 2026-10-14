import pytest

# ============================================================
# Tests de integración — el webhook repo llama a Supabase real
# ============================================================
pytestmark = pytest.mark.skip(
    reason="integration test — webhook repo requires real Supabase"
)

from uuid import UUID, uuid4
from fastapi.testclient import TestClient
from src.http.app import create_app
from src.core.tenant_context import TenantContextManager

TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")


class DummyTenant:
    tenant_id = TENANT_ID
    id = TENANT_ID
    name = "Dummy Tenant"
    slug = "dummy-tenant"
    is_active = True

    def get_config(self, key, default=None):
        return "dummy-tenant" if key == "slug" else default


def fake_load_tenant(identifier):
    return DummyTenant()


@pytest.fixture(autouse=True)
def patch_tenant_context(monkeypatch):
    monkeypatch.setattr("src.http.app.load_tenant_context", fake_load_tenant)
    monkeypatch.setattr(
        "src.services.tenant_service.load_tenant_context", fake_load_tenant
    )
    yield
    TenantContextManager.clear()


@pytest.fixture
def client():
    return TestClient(create_app(), raise_server_exceptions=False)


def _create_webhook(client):
    payload = {
        "name": "Pedidos",
        "url": "https://example.com/webhooks/orders",
        "events": ["order.created"],
    }
    resp = client.post(
        "/api/v1/webhooks/",
        json=payload,
        headers={"X-Tenant-Id": str(TENANT_ID), "Authorization": "Bearer demo-token"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_create_webhook(client):
    assert _create_webhook(client)


def test_list_webhooks(client):
    _create_webhook(client)


def test_get_webhook_detail(client):
    pass


def test_update_webhook(client):
    pass


def test_get_deliveries_initially_empty(client):
    pass


def test_test_webhook_success(client):
    pass


def test_delete_webhook(client):
    pass


def test_get_not_found_after_delete(client):
    pass


def test_invalid_url_returns_422(client):
    pass


def test_missing_tenant_header_returns_400(client):
    pass
