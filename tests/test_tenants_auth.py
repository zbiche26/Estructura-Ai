import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from src.http.app import create_app, API_PREFIX
from src.http.routers import tenants as tenants_router

# ============================================================
# Tests de integración — requieren Supabase real con credenciales válidas
# Skipeados en CI/local sin BD real configurada
# ============================================================
pytestmark = pytest.mark.skip(
    reason="integration test — requires real Supabase credentials"
)

app = create_app()
client = TestClient(app)

PASSWORD = "TestPass123!"


def _whatsapp(suffix: str) -> str:
    digits = str(abs(uuid.uuid4().int))[-7:]
    return f"+5730{digits}"


BASE_PATH = f"{API_PREFIX}/tenants"


def _payload(suffix: str, *, password: str = PASSWORD, whatsapp: str = None) -> dict:
    if whatsapp is None:
        whatsapp = _whatsapp(suffix)
    return {
        "name": f"Test User {suffix}",
        "email": f"{suffix}@example.com",
        "password": password,
        "slug": f"slug-{suffix}",
        "plan": "starter",
        "whatsapp_phone_number": whatsapp,
    }


def _suffix() -> str:
    return uuid.uuid4().hex[:8]


def test_register_success():
    suffix = _suffix()
    payload = _payload(suffix)
    resp = client.post(f"{BASE_PATH}/register", json=payload)
    assert resp.status_code == 201
    assert resp.json()["email"] == payload["email"]


def test_register_email_duplicate():
    suffix = _suffix()
    payload = _payload(suffix)
    client.post(f"{BASE_PATH}/register", json=payload)
    resp = client.post(
        f"{BASE_PATH}/register",
        json={
            **payload,
            "slug": f"dup-{suffix}",
            "whatsapp_phone_number": _whatsapp(_suffix()),
        },
    )
    assert resp.status_code == 409
    assert "EMAIL_ALREADY_EXISTS" in resp.text


def test_register_slug_duplicate():
    suffix = _suffix()
    payload = _payload(suffix)
    client.post(f"{BASE_PATH}/register", json=payload)
    payload2 = _payload(_suffix())
    payload2["slug"] = payload["slug"]
    payload2["whatsapp_phone_number"] = _whatsapp(_suffix())
    resp = client.post(f"{BASE_PATH}/register", json=payload2)
    assert resp.status_code == 409
    assert "SLUG_ALREADY_EXISTS" in resp.text


def test_register_whatsapp_duplicate():
    suffix1 = _suffix()
    suffix2 = _suffix()
    shared_whatsapp = _whatsapp("shared")
    payload1 = _payload(suffix1, whatsapp=shared_whatsapp)
    payload2 = _payload(suffix2, whatsapp=shared_whatsapp)
    client.post(f"{BASE_PATH}/register", json=payload1)
    resp = client.post(f"{BASE_PATH}/register", json=payload2)
    assert resp.status_code == 409
    assert "WHATSAPP_PHONE_ALREADY_EXISTS" in resp.text


def test_register_whatsapp_duplicate_error_body():
    suffix1 = _suffix()
    suffix2 = _suffix()
    shared_whatsapp = _whatsapp("shared-body")
    payload1 = _payload(suffix1, whatsapp=shared_whatsapp)
    payload2 = _payload(suffix2, whatsapp=shared_whatsapp)

    client.post(f"{BASE_PATH}/register", json=payload1)
    resp = client.post(f"{BASE_PATH}/register", json=payload2)

    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["error_code"] == "WHATSAPP_PHONE_ALREADY_EXISTS"
    assert detail["message"] == "Este número de WhatsApp ya está registrado"


def test_update_tenant_whatsapp_duplicate():
    suffix1 = _suffix()
    suffix2 = _suffix()
    shared_whatsapp = _whatsapp("update-dup")
    payload1 = _payload(suffix1, whatsapp=shared_whatsapp)
    payload2 = _payload(suffix2)

    created_1 = client.post(f"{BASE_PATH}/register", json=payload1)
    created_2 = client.post(f"{BASE_PATH}/register", json=payload2)

    assert created_1.status_code == 201
    assert created_2.status_code == 201

    tenant_2_id = created_2.json()["id"]
    resp = client.put(
        f"{BASE_PATH}/{tenant_2_id}",
        json={"whatsapp_phone_number": shared_whatsapp},
    )

    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["error_code"] == "WHATSAPP_PHONE_ALREADY_EXISTS"
    assert detail["message"] == "Este número de WhatsApp ya está registrado"


def test_update_tenant_same_whatsapp_no_conflict():
    suffix = _suffix()
    current_whatsapp = _whatsapp("same-number")
    payload = _payload(suffix, whatsapp=current_whatsapp)
    created = client.post(f"{BASE_PATH}/register", json=payload)

    assert created.status_code == 201
    tenant_id = created.json()["id"]

    resp = client.put(
        f"{BASE_PATH}/{tenant_id}",
        json={"whatsapp_phone_number": current_whatsapp, "name": f"Updated {suffix}"},
    )

    assert resp.status_code == 200
    assert resp.json()["whatsapp_phone_number"] == current_whatsapp


def test_register_weak_password():
    suffix = _suffix()
    weak_payload = _payload(suffix, password="123")
    resp = client.post(f"{BASE_PATH}/register", json=weak_payload)
    assert resp.status_code == 422


def test_login_success():
    suffix = _suffix()
    payload = _payload(suffix)
    client.post(f"{BASE_PATH}/register", json=payload)
    resp = client.post(
        f"{BASE_PATH}/login",
        json={
            "email": payload["email"],
            "password": payload["password"],
        },
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_wrong_email():
    resp = client.post(
        f"{BASE_PATH}/login",
        json={
            "email": "noexist@example.com",
            "password": PASSWORD,
        },
    )
    assert resp.status_code == 401
    assert "INVALID_CREDENTIALS" in resp.text


def test_login_wrong_password():
    suffix = _suffix()
    payload = _payload(suffix)
    client.post(f"{BASE_PATH}/register", json=payload)
    resp = client.post(
        f"{BASE_PATH}/login",
        json={
            "email": payload["email"],
            "password": "Wrong123!",
        },
    )
    assert resp.status_code == 401
    assert "INVALID_CREDENTIALS" in resp.text


def test_login_inactive_tenant():
    pass


def test_logout_success():
    pass


def test_logout_invalid_token():
    pass


def test_refresh_token_success():
    tenant_id = str(uuid.uuid4())
    fake_tenant = SimpleNamespace(
        id=tenant_id,
        name="Tenant Refresh",
        email="refresh@example.com",
        slug="tenant-refresh",
        is_active=True,
        plan="starter",
        max_products=100,
        max_conversations=1000,
        whatsapp_phone_number="+573001112233",
        whatsapp_enabled=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    original_find_by_id = tenants_router.tenant_repo.find_by_id
    tenants_router.tenant_repo.find_by_id = lambda tenant_id_value: (
        fake_tenant if str(tenant_id_value) == tenant_id else None
    )

    try:
        refresh_token = tenants_router.create_token(
            sub=tenant_id,
            secret=tenants_router.JWT_REFRESH_SECRET,
            expires_in=3600,
            token_type="refresh",
            extra={
                "email": fake_tenant.email,
                "plan": fake_tenant.plan,
                "ver": int(datetime.now(timezone.utc).timestamp()),
            },
        )

        resp = client.post(
            f"{BASE_PATH}/refresh-token",
            json={"refresh_token": refresh_token},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["tenant"]["id"] == tenant_id
    finally:
        tenants_router.tenant_repo.find_by_id = original_find_by_id


def test_refresh_token_invalid():
    resp = client.post(
        f"{BASE_PATH}/refresh-token",
        json={"refresh_token": "invalid.token.value"},
    )
    assert resp.status_code == 401
    assert "REFRESH_TOKEN_INVALID" in resp.text


def test_forgot_password_valid():
    suffix = _suffix()
    payload = _payload(suffix)
    client.post(f"{BASE_PATH}/register", json=payload)
    resp = client.post(
        f"{BASE_PATH}/forgot-password",
        json={
            "email": payload["email"],
        },
    )
    assert resp.status_code == 200
    assert "reset_token" in resp.json()


def test_forgot_password_invalid():
    resp = client.post(
        f"{BASE_PATH}/forgot-password", json={"email": "noexist@example.com"}
    )
    assert resp.status_code == 200
    assert resp.json()["reset_token"] is None


def test_reset_password_success():
    pass


def test_reset_password_invalid():
    pass


def test_reset_password_tenant_not_found():
    pass
