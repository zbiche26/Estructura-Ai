import pytest
import os
from src.services.tenant_service import load_tenant_context

# ============================================================
# Tests de integración — requieren Supabase real
# ============================================================
pytestmark = pytest.mark.skip(
    reason="integration test — requires real Supabase credentials"
)


@pytest.mark.skipif(
    not os.getenv("SUPABASE_URL")
    or not (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")),
    reason="SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY/KEY requeridos",
)
def test_load_tenant_context_from_supabase():
    slug = os.environ["TEST_TENANT_SLUG"]
    ctx = load_tenant_context(slug)
    assert ctx is not None


from fastapi.testclient import TestClient
from src.http.app import create_app
from supabase import create_client


@pytest.fixture
def client():
    from src.http.app import create_app

    return TestClient(create_app())


TENANT_ID = "f948870f-0fbb-44c5-b48f-1daf41b76267"
WEBHOOK_SECRET = "mi_token_verificacion"
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")


def test_get_tenant_direct_from_supabase():
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    response = client.table("tenants").select("*").eq("id", TENANT_ID).execute()
    assert response.data


def test_list_all_tenants():
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    response = client.table("tenants").select("*").execute()
    assert response.data is not None


def test_real_supabase_tenant(client):
    params = {
        "mode": "subscribe",
        "token": "mi_token_verificacion",
        "challenge": "112233",
    }
    headers = {"X-Tenant-ID": TENANT_ID}
    response = client.get(
        f"/webhook/whatsapp/{TENANT_ID}", params=params, headers=headers
    )
    assert response.status_code in [200, 403, 404]


import requests

BASE_URL = "http://localhost:8000"


def test_real_webhook_get():
    params = {
        "mode": "subscribe",
        "token": "mi_token_verificacion",
        "challenge": "prueba123",
    }
    headers = {"X-Tenant-ID": TENANT_ID}
    url = f"{BASE_URL}/webhook/whatsapp/{TENANT_ID}"
    response = requests.get(url, params=params, headers=headers)
    assert response.status_code in [200, 403, 404]


def test_real_webhook_post():
    import json, hmac, hashlib

    payload = {"object": "whatsapp_business_account", "entry": []}
    body = json.dumps(payload)
    signature = hmac.new(
        WEBHOOK_SECRET.encode(), body.encode(), hashlib.sha256
    ).hexdigest()
    headers = {
        "X-Tenant-ID": TENANT_ID,
        "X-Hub-Signature-256": f"sha256={signature}",
        "Content-Type": "application/json",
    }
    response = requests.post(
        f"{BASE_URL}/webhook/whatsapp/{TENANT_ID}", data=body, headers=headers
    )
    assert response.status_code in [200, 403, 404]
