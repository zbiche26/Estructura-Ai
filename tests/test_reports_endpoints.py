import datetime

from fastapi.testclient import TestClient

from src.http.app import app
from src.core.tenant_context import TenantContext

client = TestClient(app)


def _stub_tenant(monkeypatch, tenant_id: str = "tenant-123"):
    def fake_load_tenant_context(identifier):
        return TenantContext(tenant_id=identifier, tenant_name="Test", plan="free")
    monkeypatch.setattr(
        "src.services.tenant_service.load_tenant_context",
        fake_load_tenant_context,
    )
    monkeypatch.setattr(
        "src.http.app.load_tenant_context",
        fake_load_tenant_context,
    )
    return tenant_id


def test_weekly_report_ok(monkeypatch):
    tenant_id = _stub_tenant(monkeypatch)
    def fake_weekly_report(tenant_id, db):
        return {
            "tenant_id": tenant_id,
            "start_date": datetime.date(2026, 3, 7),
            "end_date": datetime.date(2026, 3, 13),
            "total_sales": 3,
            "total_revenue": "150.0",
            "average_sale": "50.0",
            "buckets": [
                {"bucket_date": "2026-03-12", "total_sales": 2, "total_revenue": "100.0"},
                {"bucket_date": "2026-03-13", "total_sales": 1, "total_revenue": "50.0"},
            ],
            "calculated_at": datetime.datetime.utcnow(),
        }
    monkeypatch.setattr("src.http.routers.report_router.get_weekly_report", fake_weekly_report)
    headers = {"Authorization": "Bearer demo-token", "X-Tenant-Id": tenant_id}
    res = client.get("/api/v1/reports/weekly", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total_sales"] == 3
    assert len(data["buckets"]) == 2


def test_monthly_report_ok(monkeypatch):
    tenant_id = _stub_tenant(monkeypatch)
    def fake_monthly_report(tenant_id, year=None, month=None, db=None):
        return {
            "tenant_id": tenant_id,
            "year": 2026,
            "month": 3,
            "total_sales": 10,
            "total_revenue": "500.0",
            "average_sale": "50.0",
            "unique_customers": 4,
            "best_day": "2026-03-10",
            "best_day_revenue": "200.0",
            "buckets": [
                {"day": 10, "total_sales": 2, "total_revenue": "200.0"},
                {"day": 11, "total_sales": 3, "total_revenue": "150.0"},
            ],
            "calculated_at": datetime.datetime.utcnow(),
        }
    monkeypatch.setattr("src.http.routers.report_router.get_monthly_report", fake_monthly_report)
    headers = {"Authorization": "Bearer demo-token", "X-Tenant-Id": tenant_id}
    res = client.get("/api/v1/reports/monthly?year=2026&month=3", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total_sales"] == 10
    assert data["unique_customers"] == 4


def test_export_csv_ok(monkeypatch):
    tenant_id = _stub_tenant(monkeypatch)
    def fake_export(tenant_id, period, fmt, db=None):
        return {
            "tenant_id": tenant_id,
            "period": period,
            "format": fmt,
            "content": "Y3N2LGRhdGE=",
            "calculated_at": datetime.datetime.utcnow(),
        }
    monkeypatch.setattr("src.http.routers.report_router.export_report", fake_export)
    headers = {"Authorization": "Bearer demo-token", "X-Tenant-Id": tenant_id}
    res = client.get("/api/v1/reports/export?period=weekly&format=csv", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["format"] == "csv"


def test_export_pdf_ok(monkeypatch):
    tenant_id = _stub_tenant(monkeypatch)
    def fake_export(tenant_id, period, fmt, db=None):
        return {
            "tenant_id": tenant_id,
            "period": period,
            "format": fmt,
            "content": "cGRm",
            "calculated_at": datetime.datetime.utcnow(),
        }
    monkeypatch.setattr("src.http.routers.report_router.export_report", fake_export)
    headers = {"Authorization": "Bearer demo-token", "X-Tenant-Id": tenant_id}
    res = client.get("/api/v1/reports/export?period=monthly&format=pdf", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["format"] == "pdf"


def test_export_invalid_format(monkeypatch):
    tenant_id = _stub_tenant(monkeypatch)
    headers = {"Authorization": "Bearer demo-token", "X-Tenant-Id": tenant_id}
    res = client.get("/api/v1/reports/export?period=weekly&format=txt", headers=headers)
    assert res.status_code in (400, 422)
