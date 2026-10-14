import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.http.app import create_app
from src.http.routers.agent import agent_config_repo
from src.models import AgentConfig

API_PREFIX = "/api/v1"

# UUID válido para los tests
TENANT_UUID = "eae6b1d9-09c9-421e-82b8-750c68aed89d"


def _auth_headers(tenant_id: str = TENANT_UUID) -> dict[str, str]:
    return {
        "Authorization": "Bearer demo-token",
        "X-Tenant-Id": tenant_id,
    }


def _mock_tenant():
    """Crea un tenant mock válido para los tests."""
    tenant = MagicMock()
    tenant.tenant_id = TENANT_UUID
    tenant.id = TENANT_UUID
    tenant.name = "Tenant Test"
    tenant.slug = "tenant-test"
    tenant.is_active = True
    return tenant


def _make_client():
    """Crea un TestClient con el middleware de tenant mockeado."""
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    return client


@pytest.fixture(autouse=True)
def mock_tenant_middleware(monkeypatch):
    """
    Mockea load_tenant_context para que no llame a Supabase real.
    Se aplica automáticamente a todos los tests del módulo.
    """
    mock = _mock_tenant()
    monkeypatch.setattr(
        "src.services.tenant_service.load_tenant_context",
        lambda tenant_id: mock,
    )
    monkeypatch.setattr(
        "src.http.app.load_tenant_context",
        lambda tenant_id: mock,
    )
    return mock


@pytest.fixture(autouse=True)
def mock_auth(monkeypatch):
    """Mockea la verificación de token JWT para los tests."""
    from src.http import deps

    mock_user = MagicMock()
    mock_user.tenant_id = TENANT_UUID
    mock_user.tenant = MagicMock()
    mock_user.tenant.id = TENANT_UUID
    mock_user.tenant.tenant_id = TENANT_UUID
    monkeypatch.setattr(deps, "verify_access_token", lambda token, db: mock_user)
    return mock_user


def test_get_agent_config_returns_404_when_no_config(monkeypatch):
    monkeypatch.setattr(agent_config_repo, "get_by_tenant_id", lambda tenant_id: None)

    client = _make_client()
    response = client.get(f"{API_PREFIX}/agent/config", headers=_auth_headers())

    assert response.status_code == 404
    assert response.json()["detail"] == "Agent configuration not found"


def test_patch_agent_config_updates_partial_fields(monkeypatch):
    patch_payload = {
        "welcome_message": "¡Hola! Estoy listo para ayudarte de nuevo.",
    }

    updated_config = AgentConfig(
        id=str(uuid.uuid4()),
        tenant_id=TENANT_UUID,
        nombre_agente="Asistente Inmobiliario",
        system_prompt="Actúa como asistente inmobiliario profesional.",
        welcome_message=patch_payload["welcome_message"],
        temperatura=0.7,
        idioma="es",
    )

    monkeypatch.setattr(
        agent_config_repo,
        "update_for_tenant",
        lambda tenant_id, data: updated_config,
    )

    client = _make_client()
    response = client.patch(
        f"{API_PREFIX}/agent/config",
        json=patch_payload,
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    assert response.json()["welcome_message"] == patch_payload["welcome_message"]
    assert response.json()["nombre_agente"] == "Asistente Inmobiliario"


def test_patch_agent_config_rejects_invalid_temperature():
    client = _make_client()
    response = client.patch(
        f"{API_PREFIX}/agent/config",
        json={"temperatura": 1.5},
        headers=_auth_headers(),
    )

    assert response.status_code == 422
    assert response.json()["detail"]


def test_patch_agent_config_returns_404_when_no_config(monkeypatch):
    """Test que cuando update_for_tenant retorna None, devuelve 404"""
    monkeypatch.setattr(
        agent_config_repo,
        "update_for_tenant",
        lambda tenant_id, data: None,
    )

    client = _make_client()
    response = client.patch(
        f"{API_PREFIX}/agent/config",
        json={"nombre_agente": "Test"},
        headers=_auth_headers(),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Agent configuration not found"


def test_patch_agent_config_rejects_extra_fields():
    """Test que extra='forbid' rechaza campos no permitidos"""
    client = _make_client()
    response = client.patch(
        f"{API_PREFIX}/agent/config",
        json={
            "nombre_agente": "Test",
            "extra_field": "should_fail",
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any("extra" in str(d).lower() for d in detail)


def test_patch_agent_config_rejects_tenant_id_modification():
    """Test que no permite modificar tenant_id por seguridad multi-tenant"""
    client = _make_client()
    response = client.patch(
        f"{API_PREFIX}/agent/config",
        json={
            "nombre_agente": "Test",
            "tenant_id": "another-tenant",
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 422
    detail_text = str(response.json()["detail"])
    assert "tenant_id" in detail_text


def test_patch_agent_config_rejects_empty_payload():
    """Test que rechaza payload vacío (sin campos para actualizar)"""
    client = _make_client()
    response = client.patch(
        f"{API_PREFIX}/agent/config",
        json={},
        headers=_auth_headers(),
    )

    assert response.status_code == 422
    detail_text = str(response.json()["detail"])
    assert "campo" in detail_text.lower() or "field" in detail_text.lower()
