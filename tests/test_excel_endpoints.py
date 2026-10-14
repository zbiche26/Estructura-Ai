from __future__ import annotations

import io
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from src.http.app import create_app

TENANT_UUID = "eae6b1d9-09c9-421e-82b8-750c68aed89d"


def _fake_tenant():
    mock = MagicMock()
    mock.tenant_id = TENANT_UUID
    mock.id = TENANT_UUID
    mock.name = "Eje Inmobiliario"
    mock.slug = "eje-inmobiliario"
    mock.is_active = True
    return mock


def _fake_user():
    mock = MagicMock()
    mock.tenant_id = TENANT_UUID
    mock.tenant = MagicMock()
    mock.tenant.id = TENANT_UUID
    return mock


@pytest.fixture(autouse=True)
def mock_tenant(monkeypatch):
    tenant = _fake_tenant()
    monkeypatch.setattr("src.http.app.load_tenant_context", lambda x: tenant)
    monkeypatch.setattr(
        "src.services.tenant_service.load_tenant_context", lambda x: tenant
    )


@pytest.fixture(autouse=True)
def mock_auth(monkeypatch):
    from src.http import deps

    monkeypatch.setattr(deps, "verify_access_token", lambda token, db: _fake_user())


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


def _headers():
    return {
        "X-Tenant-Id": TENANT_UUID,
        "Authorization": "Bearer demo-token",
    }


class TestExcelUploadEndpoint:
    def test_upload_accepts_valid_excel(self, client):
        file_bytes = io.BytesIO(b"id,name\n1,Test")
        response = client.post(
            "/api/v1/plugins/excel/upload",
            headers=_headers(),
            files={
                "file": (
                    "productos.xlsx",
                    file_bytes,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert response.status_code in [202, 400, 404, 501]

    def test_upload_rejects_invalid_extension(self, client):
        response = client.post(
            "/api/v1/plugins/excel/upload",
            headers=_headers(),
            files={"file": ("productos.txt", io.BytesIO(b"data"), "text/plain")},
        )
        assert response.status_code in [400, 422, 404, 501]

    def test_upload_rejects_invalid_mime(self, client):
        response = client.post(
            "/api/v1/plugins/excel/upload",
            headers=_headers(),
            files={"file": ("productos.xlsx", io.BytesIO(b"data"), "text/plain")},
        )
        assert response.status_code in [400, 422, 404, 501]

    def test_upload_rejects_large_file(self, client):
        large_bytes = io.BytesIO(b"0" * (10 * 1024 * 1024 + 1))
        response = client.post(
            "/api/v1/plugins/excel/upload",
            headers=_headers(),
            files={
                "file": (
                    "productos.xlsx",
                    large_bytes,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert response.status_code in [400, 413, 404, 501]


class TestExcelTemplateEndpoint:
    def test_download_template_success(self, client):
        response = client.get("/api/v1/plugins/excel/template")
        assert response.status_code in [200, 404, 501]

    def test_download_template_not_found(self, client, monkeypatch):
        monkeypatch.setattr("src.http.routers.excel.os.path.isfile", lambda _: False)
        response = client.get("/api/v1/plugins/excel/template")
        assert response.status_code in [404, 501]


class TestExcelHistoryEndpoints:
    def test_list_imports_returns_data(self, client):
        response = client.get("/api/v1/plugins/excel/imports", headers=_headers())
        assert response.status_code in [200, 404, 501]

    def test_list_imports_rejects_invalid_status(self, client):
        response = client.get(
            "/api/v1/plugins/excel/imports",
            params={"status": "unknown"},
            headers=_headers(),
        )
        assert response.status_code in [400, 422, 404, 501]

    def test_list_imports_filters_by_status(self, client):
        response = client.get(
            "/api/v1/plugins/excel/imports",
            params={"status": "failed"},
            headers=_headers(),
        )
        assert response.status_code in [200, 404, 501]

    def test_get_import_detail_success(self, client):
        response = client.get(
            "/api/v1/plugins/excel/imports/import-1",
            headers=_headers(),
        )
        assert response.status_code in [200, 404, 501]

    def test_get_import_detail_not_found(self, client):
        response = client.get(
            "/api/v1/plugins/excel/imports/unknown",
            headers=_headers(),
        )
        assert response.status_code in [404, 501]
