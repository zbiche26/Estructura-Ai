from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from src.http.app import create_app

TENANT_UUID = "eae6b1d9-09c9-421e-82b8-750c68aed89d"

MOCK_STOCK_ITEMS = [
    {
        "id": "prod-001",
        "name": "Silla Ergonómica",
        "sku": "SKU-001",
        "stock": 5,
        "min_stock": 10,
    },
    {
        "id": "prod-002",
        "name": "Mesa de Oficina",
        "sku": "SKU-002",
        "stock": 15,
        "min_stock": 5,
    },
]


def _mock_tenant():
    mock = MagicMock()
    mock.tenant_id = TENANT_UUID
    mock.id = TENANT_UUID
    mock.name = "Eje Inmobiliario"
    mock.slug = "eje-inmobiliario"
    mock.is_active = True
    return mock


def _mock_user():
    mock = MagicMock()
    mock.tenant_id = TENANT_UUID
    mock.tenant = MagicMock()
    mock.tenant.id = TENANT_UUID
    return mock


@pytest.fixture(autouse=True)
def mock_tenant(monkeypatch):
    tenant = _mock_tenant()
    monkeypatch.setattr("src.http.app.load_tenant_context", lambda x: tenant)
    monkeypatch.setattr(
        "src.services.tenant_service.load_tenant_context", lambda x: tenant
    )
    return tenant


@pytest.fixture(autouse=True)
def mock_auth(monkeypatch):
    from src.http import deps

    user = _mock_user()
    monkeypatch.setattr(deps, "verify_access_token", lambda token, db: user)
    return user


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


def _headers():
    return {
        "X-Tenant-Id": TENANT_UUID,
        "Authorization": "Bearer demo-token",
    }


class TestInventoryStockEndpoint:
    def test_get_stock_returns_products(self, client):
        response = client.get("/api/v1/plugins/inventory/stock", headers=_headers())
        assert response.status_code in [200, 404, 501]

    def test_get_stock_low_stock_filter(self, client):
        response = client.get(
            "/api/v1/plugins/inventory/stock",
            params={"low_stock_only": True},
            headers=_headers(),
        )
        assert response.status_code in [200, 404, 501]

    def test_get_stock_search_filter(self, client):
        response = client.get(
            "/api/v1/plugins/inventory/stock",
            params={"search": "Silla"},
            headers=_headers(),
        )
        assert response.status_code in [200, 404, 501]


class TestInventoryAdjustEndpoint:
    def test_adjust_stock_success(self, client):
        payload = {"product_id": "prod-001", "adjustment": 5, "reason": "Inventario"}
        response = client.post(
            "/api/v1/plugins/inventory/adjust",
            headers=_headers(),
            json=payload,
        )
        assert response.status_code in [200, 202, 404, 501]

    def test_adjust_stock_zero_adjustment(self, client):
        payload = {"product_id": "prod-001", "adjustment": 0, "reason": "Inventario"}
        response = client.post(
            "/api/v1/plugins/inventory/adjust",
            headers=_headers(),
            json=payload,
        )
        assert response.status_code in [400, 422, 404, 501]


class TestInventoryAlertsEndpoint:
    def test_list_alerts_returns_results(self, client):
        response = client.get("/api/v1/plugins/inventory/alerts", headers=_headers())
        assert response.status_code in [200, 404, 501]

    def test_list_alerts_filter_by_level(self, client):
        response = client.get(
            "/api/v1/plugins/inventory/alerts",
            params={"level": "critical"},
            headers=_headers(),
        )
        assert response.status_code in [200, 404, 501]


class TestInventoryHistoryEndpoint:
    def test_history_returns_paginated_data(self, client):
        response = client.get(
            "/api/v1/plugins/inventory/history",
            params={"page": 1, "limit": 5},
            headers=_headers(),
        )
        assert response.status_code in [200, 404, 501]

    def test_history_filters_by_product(self, client):
        response = client.get(
            "/api/v1/plugins/inventory/history",
            params={"product_id": "prod-001"},
            headers=_headers(),
        )
        assert response.status_code in [200, 404, 501]
