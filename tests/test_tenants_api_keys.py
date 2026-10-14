import uuid
import pytest
from fastapi.testclient import TestClient
from src.http.app import create_app, API_PREFIX

# ============================================================
# Tests de integración — requieren Supabase real
# ============================================================
pytestmark = pytest.mark.skip(reason="integration test — requires real Supabase credentials")

app = create_app()
client = TestClient(app)

BASE_PATH = f"{API_PREFIX}/tenants"
PASSWORD = "TestPass123!"


def _suffix() -> str:
    return uuid.uuid4().hex[:8]


def _payload(suffix: str) -> dict:
    return {
        "name": f"Tenant {suffix}",
        "email": f"{suffix}@example.com",
        "password": PASSWORD,
        "slug": f"slug-{suffix}",
        "plan": "starter",
        "whatsapp_phone_number": f"+5730{str(abs(uuid.uuid4().int))[-7:]}",
    }


def _create_tenant() -> dict:
    suffix = _suffix()
    payload = _payload(suffix)
    resp = client.post(f"{BASE_PATH}/register", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    return {"id": data["id"], "payload": payload}


def test_generate_api_key_success():
    tenant = _create_tenant()
    resp = client.post(f"{BASE_PATH}/{tenant['id']}/api-keys")
    body = resp.json()
    assert resp.status_code == 201
    assert body["api_key"]
    assert body["id"]


def test_generate_api_key_with_name():
    tenant = _create_tenant()
    resp = client.post(f"{BASE_PATH}/{tenant['id']}/api-keys", json={"name": "server-key"})
    body = resp.json()
    assert resp.status_code == 201
    assert body["name"] == "server-key"


def test_generate_api_key_tenant_not_found():
    fake_id = str(uuid.uuid4())
    resp = client.post(f"{BASE_PATH}/{fake_id}/api-keys")
    assert resp.status_code == 404


def test_revoke_api_key_success():
    tenant = _create_tenant()
    create_resp = client.post(f"{BASE_PATH}/{tenant['id']}/api-keys")
    key_id = create_resp.json()["id"]
    resp = client.delete(f"{BASE_PATH}/{tenant['id']}/api-keys/{key_id}")
    assert resp.status_code == 200
    assert "revocada" in resp.json()["message"]


def test_revoke_api_key_not_found():
    tenant = _create_tenant()
    resp = client.delete(f"{BASE_PATH}/{tenant['id']}/api-keys/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_revoke_api_key_already_revoked():
    tenant = _create_tenant()
    create_resp = client.post(f"{BASE_PATH}/{tenant['id']}/api-keys")
    key_id = create_resp.json()["id"]
    client.delete(f"{BASE_PATH}/{tenant['id']}/api-keys/{key_id}")
    resp = client.delete(f"{BASE_PATH}/{tenant['id']}/api-keys/{key_id}")
    assert resp.status_code == 400


def test_usage_success():
    tenant = _create_tenant()
    resp = client.get(f"{BASE_PATH}/{tenant['id']}/usage")
    body = resp.json()
    assert resp.status_code == 200
    assert "messages_used" in body


def test_usage_tenant_not_found():
    resp = client.get(f"{BASE_PATH}/{uuid.uuid4()}/usage")
    assert resp.status_code == 404


def test_billing_success():
    tenant = _create_tenant()
    resp = client.get(f"{BASE_PATH}/{tenant['id']}/billing")
    body = resp.json()
    assert resp.status_code == 200
    assert body["plan"]


def test_billing_tenant_not_found():
    resp = client.get(f"{BASE_PATH}/{uuid.uuid4()}/billing")
    assert resp.status_code == 404


def test_generate_multiple_keys_are_distinct():
    tenant = _create_tenant()
    resp1 = client.post(f"{BASE_PATH}/{tenant['id']}/api-keys")
    resp2 = client.post(f"{BASE_PATH}/{tenant['id']}/api-keys")
    assert resp1.json()["api_key"] != resp2.json()["api_key"]