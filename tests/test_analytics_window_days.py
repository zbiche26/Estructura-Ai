from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.http.app import API_PREFIX, create_app
from src.http.routers import analytics_router

TENANT_UUID = "eae6b1d9-09c9-421e-82b8-750c68aed89d"


def _fake_tenant():
    mock = MagicMock()
    mock.tenant_id = TENANT_UUID
    mock.id = TENANT_UUID
    mock.name = "Tenant Test"
    mock.slug = "tenant-test"
    mock.is_active = True
    return mock


def _fake_user():
    return SimpleNamespace(tenant=SimpleNamespace(id=TENANT_UUID))


@pytest.fixture(autouse=True)
def mock_tenant(monkeypatch):
    tenant = _fake_tenant()
    monkeypatch.setattr("src.http.app.load_tenant_context", lambda x: tenant)
    monkeypatch.setattr(
        "src.services.tenant_service.load_tenant_context", lambda x: tenant
    )


def _build_client(monkeypatch) -> TestClient:
    app = create_app()

    app.dependency_overrides[analytics_router.current_user_dep] = _fake_user
    app.dependency_overrides[analytics_router.get_db] = lambda: MagicMock()

    def _fake_overview(*, tenant_id, window_days, db):
        return {
            "tenant_id": tenant_id,
            "total_conversations": 10,
            "active_users": 4,
            "avg_response_time": 1.2,
            "conversations_per_day": {
                f"2026-04-{str(i).zfill(2)}": i for i in range(1, window_days + 1)
            },
            "window_days": window_days,
            "calculated_at": datetime.utcnow().isoformat(),
        }

    def _fake_day(*, tenant_id, window_days, db):
        # Retorna exactamente el shape de ConversationsByDayResponse
        return {
            "data": [
                {"date": f"2026-04-{str(i).zfill(2)}", "count": i}
                for i in range(1, window_days + 1)
            ],
        }

    monkeypatch.setattr(analytics_router, "get_analytics_overview", _fake_overview)
    monkeypatch.setattr(analytics_router, "get_conversations_by_day", _fake_day)

    return TestClient(app, raise_server_exceptions=False)


def test_overview_accepts_1_7_30(monkeypatch):
    client = _build_client(monkeypatch)
    for value in (1, 7, 30):
        resp = client.get(
            f"{API_PREFIX}/analytics/overview?window_days={value}",
            headers={"X-Tenant-Id": TENANT_UUID, "Authorization": "Bearer demo-token"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["window_days"] == value
        assert len(body["conversations_per_day"]) == value


def test_overview_out_of_range_returns_422(monkeypatch):
    client = _build_client(monkeypatch)
    resp = client.get(
        f"{API_PREFIX}/analytics/overview?window_days=200",
        headers={"X-Tenant-Id": TENANT_UUID, "Authorization": "Bearer demo-token"},
    )
    assert resp.status_code in [400, 422]


def test_overview_default_is_7(monkeypatch):
    client = _build_client(monkeypatch)
    resp = client.get(
        f"{API_PREFIX}/analytics/overview",
        headers={"X-Tenant-Id": TENANT_UUID, "Authorization": "Bearer demo-token"},
    )
    assert resp.status_code == 200
    assert resp.json()["window_days"] == 7


def test_conversations_day_accepts_1_7_30(monkeypatch):
    client = _build_client(monkeypatch)
    for value in (1, 7, 30):
        resp = client.get(
            f"{API_PREFIX}/analytics/conversations/day?window_days={value}",
            headers={"X-Tenant-Id": TENANT_UUID, "Authorization": "Bearer demo-token"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert isinstance(body["data"], list)


def test_conversations_day_out_of_range_returns_422(monkeypatch):
    client = _build_client(monkeypatch)
    resp = client.get(
        f"{API_PREFIX}/analytics/conversations/day?window_days=200",
        headers={"X-Tenant-Id": TENANT_UUID, "Authorization": "Bearer demo-token"},
    )
    assert resp.status_code in [400, 422]
