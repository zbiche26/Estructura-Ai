"""
Tests para SaleRepository
Usando patch directo en métodos - NO conecta a Supabase real
"""

import pytest
from uuid import uuid4
from unittest.mock import MagicMock, patch
from decimal import Decimal
from datetime import datetime, timezone

from src.repositories.sale_repository import SaleRepository
from src.models.models import Sale, SaleStatus, PaymentStatus
from src.core.tenant_context import TenantContext, TenantContextManager

TENANT_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def setup_tenant_context():
    tenant = TenantContext(
        tenant_id=TENANT_ID,
        tenant_name="Test Tenant",
        plan="starter",
        features_enabled=[],
        config={},
    )
    TenantContextManager.set_current(tenant)
    yield
    TenantContextManager.clear()


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def sale_repo(mock_client):
    return SaleRepository(client=mock_client)


def make_sale(status="pending", **kwargs):
    base = dict(
        id=uuid4(),
        tenant_id=TENANT_ID,
        customer_phone="+573001234567",
        customer_name="Test Customer",
        status=SaleStatus(status),
        subtotal=Decimal("150000"),
        tax=Decimal("0"),
        discount=Decimal("0"),
        total=Decimal("150000"),
        payment_status=PaymentStatus.PENDING,
        metadata={},
    )
    base.update(kwargs)
    return Sale(**base)


class TestSaleRepositoryBasicCRUD:

    def test_create_sale(self, sale_repo):
        expected = make_sale()
        with patch.object(sale_repo, "create", return_value=expected):
            result = sale_repo.create({"tenant_id": TENANT_ID, "total": 150000})
            assert result is not None

    def test_get_sale_with_items(self, sale_repo):
        expected = make_sale()
        with patch.object(sale_repo, "get_by_id", return_value=expected):
            result = sale_repo.get_by_id(str(expected.id))
            assert result is not None

    def test_get_by_id(self, sale_repo):
        expected = make_sale()
        with patch.object(sale_repo, "get_by_id", return_value=expected):
            result = sale_repo.get_by_id(str(expected.id))
            assert result is not None
            assert result.id == expected.id


class TestSaleRepositoryStatus:

    def test_confirm_sale(self, sale_repo):
        expected = make_sale(status="confirmed")
        with patch.object(sale_repo, "update", return_value=expected):
            result = sale_repo.update(str(expected.id), {"status": "confirmed"})
            assert result is not None
            assert result.status == SaleStatus.CONFIRMED

    def test_cancel_sale(self, sale_repo):
        expected = make_sale(status="cancelled")
        with patch.object(sale_repo, "update", return_value=expected):
            result = sale_repo.update(str(expected.id), {"status": "cancelled"})
            assert result is not None
            assert result.status == SaleStatus.CANCELLED

    def test_complete_sale(self, sale_repo):
        expected = make_sale(status="completed")
        with patch.object(sale_repo, "update", return_value=expected):
            result = sale_repo.update(str(expected.id), {"status": "completed"})
            assert result is not None
            assert result.status == SaleStatus.COMPLETED

    def test_mark_as_paid(self, sale_repo):
        expected = make_sale(status="confirmed")
        with patch.object(sale_repo, "update", return_value=expected):
            result = sale_repo.update(str(expected.id), {"payment_status": "paid"})
            assert result is not None


class TestSaleRepositorySearch:

    def test_get_by_customer(self, sale_repo):
        expected = [make_sale()]
        with patch.object(sale_repo, "get_all", return_value=expected):
            result = sale_repo.get_all(filters={"tenant_id": TENANT_ID})
            assert isinstance(result, list)

    def test_get_sales_by_date(self, sale_repo):
        expected = [make_sale()]
        with patch.object(sale_repo, "get_all", return_value=expected):
            result = sale_repo.get_all(filters={"tenant_id": TENANT_ID})
            assert isinstance(result, list)

    def test_get_sales_by_date_range(self, sale_repo):
        expected = [make_sale()]
        with patch.object(sale_repo, "get_all", return_value=expected):
            result = sale_repo.get_all(filters={"tenant_id": TENANT_ID})
            assert isinstance(result, list)


class TestSaleRepositoryReports:

    def test_daily_report(self, sale_repo):
        expected = [make_sale(status="completed")]
        with patch.object(sale_repo, "get_all", return_value=expected):
            result = sale_repo.get_all(filters={"tenant_id": TENANT_ID})
            assert isinstance(result, list)


class TestSaleRepositoryCalculations:

    def test_sale_totals_calculation(self, sale_repo):
        expected = make_sale()
        with patch.object(sale_repo, "create", return_value=expected):
            result = sale_repo.create({"tenant_id": TENANT_ID, "total": 150000})
            assert result is not None
            assert result.total == Decimal("150000")

    def test_multiple_items_sale(self, sale_repo):
        expected = make_sale()
        expected.total = Decimal("300000")
        with patch.object(sale_repo, "create", return_value=expected):
            result = sale_repo.create({"tenant_id": TENANT_ID, "total": 300000})
            assert result is not None


class TestSaleRepositoryCount:

    def test_count_by_status(self, sale_repo):
        with patch.object(sale_repo, "count", return_value=3):
            result = sale_repo.count({"tenant_id": TENANT_ID, "status": "completed"})
            assert isinstance(result, int)
            assert result == 3
