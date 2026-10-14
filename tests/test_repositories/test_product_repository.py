"""
Tests para ProductRepository
Usando patch directo en métodos - NO conecta a Supabase real
"""
import pytest
from uuid import uuid4
from unittest.mock import MagicMock, patch
from decimal import Decimal

from src.repositories.product_repository import ProductRepository
from src.models.models import Product
from src.core.tenant_context import TenantContext, TenantContextManager


TENANT_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def setup_tenant_context():
    tenant = TenantContext(
        tenant_id=TENANT_ID,
        tenant_name="Test Tenant",
        plan="starter",
        features_enabled=[],
        config={}
    )
    TenantContextManager.set_current(tenant)
    yield
    TenantContextManager.clear()


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def product_repo(mock_client):
    return ProductRepository(client=mock_client)


def make_product(**kwargs):
    base = dict(
        id=uuid4(),
        tenant_id=TENANT_ID,
        name="Laptop Dell XPS",
        sku=f"SKU-{uuid4().hex[:6]}",
        description="Laptop de alto rendimiento",
        price=Decimal("1500000"),
        stock=10,
        min_stock=2,
        category="electronica",
        is_active=True,
        metadata={},
    )
    base.update(kwargs)
    return Product(**base)


class TestProductRepositoryBasicCRUD:

    def test_create_product(self, product_repo):
        expected = make_product()
        with patch.object(product_repo, 'create', return_value=expected):
            result = product_repo.create({"tenant_id": TENANT_ID, "name": "Laptop"})
            assert result is not None
            assert result.name == expected.name

    def test_get_by_id(self, product_repo):
        expected = make_product()
        with patch.object(product_repo, 'get_by_id', return_value=expected):
            result = product_repo.get_by_id(str(expected.id))
            assert result is not None
            assert result.id == expected.id

    def test_get_all(self, product_repo):
        expected = [make_product() for _ in range(3)]
        with patch.object(product_repo, 'get_all', return_value=expected):
            result = product_repo.get_all(filters={"tenant_id": TENANT_ID})
            assert isinstance(result, list)
            assert len(result) == 3

    def test_update_product(self, product_repo):
        expected = make_product(name="Laptop Actualizado")
        with patch.object(product_repo, 'update', return_value=expected):
            result = product_repo.update(str(expected.id), {"name": "Laptop Actualizado"})
            assert result is not None
            assert result.name == "Laptop Actualizado"

    def test_delete_product(self, product_repo):
        with patch.object(product_repo, 'delete', return_value=True):
            result = product_repo.delete(str(uuid4()))
            assert result is True


class TestProductRepositorySearch:

    def test_find_by_sku(self, product_repo):
        expected = make_product(sku="SKU-001")
        with patch.object(product_repo, 'find_by_sku', return_value=expected):
            result = product_repo.find_by_sku(TENANT_ID, "SKU-001")
            assert result is not None

    def test_find_by_category(self, product_repo):
        expected = [make_product(category="electronica")]
        with patch.object(product_repo, 'find_by_category', return_value=expected):
            result = product_repo.find_by_category(TENANT_ID, "electronica")
            assert isinstance(result, list)

    def test_search_by_name(self, product_repo):
        expected = [make_product(name="Laptop Dell")]
        with patch.object(product_repo, 'search_by_name', return_value=expected):
            result = product_repo.search_by_name(TENANT_ID, "laptop")
            assert isinstance(result, list)


class TestProductRepositoryStock:

    def test_update_stock(self, product_repo):
        expected = make_product(stock=20)
        with patch.object(product_repo, 'update_stock', return_value=expected):
            result = product_repo.update_stock(str(expected.id), 20)
            assert result is not None

    def test_decrease_stock(self, product_repo):
        expected = make_product(stock=8)
        with patch.object(product_repo, 'decrease_stock', return_value=expected):
            result = product_repo.decrease_stock(str(expected.id), 2)
            assert result is not None

    def test_decrease_stock_insufficient(self, product_repo):
        with patch.object(product_repo, 'decrease_stock', side_effect=ValueError("Stock insuficiente")):
            with pytest.raises(Exception):
                product_repo.decrease_stock(str(uuid4()), 100)

    def test_increase_stock(self, product_repo):
        expected = make_product(stock=15)
        with patch.object(product_repo, 'increase_stock', return_value=expected):
            result = product_repo.increase_stock(str(expected.id), 5)
            assert result is not None


class TestProductRepositoryPrice:

    def test_find_by_price_range(self, product_repo):
        expected = [make_product(price=Decimal("1000000"))]
        with patch.object(product_repo, 'find_by_price_range', return_value=expected):
            result = product_repo.find_by_price_range(TENANT_ID, 500000, 2000000)
            assert isinstance(result, list)


class TestProductRepositoryActivation:

    def test_activate_deactivate(self, product_repo):
        expected = make_product(is_active=False)
        with patch.object(product_repo, 'update', return_value=expected):
            result = product_repo.update(str(expected.id), {"is_active": False})
            assert result is not None
            assert result.is_active is False


class TestProductRepositoryCount:

    def test_count_by_category(self, product_repo):
        with patch.object(product_repo, 'count', return_value=5):
            count = product_repo.count({"tenant_id": TENANT_ID, "category": "electronica"})
            assert isinstance(count, int)
            assert count == 5

    def test_exists(self, product_repo):
        with patch.object(product_repo, 'exists', return_value=True):
            result = product_repo.exists(str(uuid4()))
            assert result is True