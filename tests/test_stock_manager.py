"""
Tests para Stock Manager
Requieren Supabase real — skipeados en CI/local sin BD configurada
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from src.services.stock_manager import StockManager
from src.models.stock import StockLevel, StockReservation

# ============================================================
# Tests de integración — requieren Supabase real
# ============================================================
pytestmark = pytest.mark.skip(
    reason="integration test — requires real Supabase credentials"
)


@pytest.fixture
def stock_manager():
    return StockManager()


@pytest.fixture
def test_product_id(stock_manager):
    result = (
        stock_manager.supabase.table("products")
        .select("id")
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    if result.data:
        return str(result.data[0]["id"])
    pytest.skip("No hay productos en la BD para testing")


@pytest.fixture
def test_conversation_id():
    return str(uuid4())


def test_get_stock_level(stock_manager, test_product_id):
    stock_level = stock_manager.get_stock_level(test_product_id)
    assert isinstance(stock_level, StockLevel)
    assert stock_level.total_stock >= 0


def test_reserve_stock_success(stock_manager, test_product_id, test_conversation_id):
    stock_level = stock_manager.get_stock_level(test_product_id)
    if stock_level.available_stock < 1:
        pytest.skip("No hay stock disponible para reservar")
    reservation = stock_manager.reserve_stock(
        product_id=test_product_id,
        quantity=1,
        conversation_id=test_conversation_id,
        tenant_id="demo",
        duration_minutes=30,
    )
    assert isinstance(reservation, StockReservation)
    assert reservation.status == "active"
    stock_manager.release_stock(str(reservation.id))


def test_reserve_stock_insufficient(
    stock_manager, test_product_id, test_conversation_id
):
    stock_level = stock_manager.get_stock_level(test_product_id)
    with pytest.raises(ValueError, match="Insufficient stock"):
        stock_manager.reserve_stock(
            product_id=test_product_id,
            quantity=stock_level.available_stock + 100,
            conversation_id=test_conversation_id,
            tenant_id="demo",
        )


def test_release_stock(stock_manager, test_product_id, test_conversation_id):
    stock_level = stock_manager.get_stock_level(test_product_id)
    if stock_level.available_stock < 1:
        pytest.skip("No hay stock disponible")
    reservation = stock_manager.reserve_stock(
        product_id=test_product_id,
        quantity=1,
        conversation_id=test_conversation_id,
        tenant_id="demo",
    )
    result = stock_manager.release_stock(str(reservation.id))
    assert result is True


def test_update_stock_increase(stock_manager, test_product_id):
    result = stock_manager.update_stock(
        product_id=test_product_id, quantity_change=5, reason="Test"
    )
    assert result["change"] == 5
    stock_manager.update_stock(
        product_id=test_product_id, quantity_change=-5, reason="Rollback"
    )


def test_update_stock_decrease(stock_manager, test_product_id):
    initial_stock = stock_manager.get_stock_level(test_product_id)
    if initial_stock.total_stock < 1:
        pytest.skip("No hay stock para reducir")
    result = stock_manager.update_stock(
        product_id=test_product_id, quantity_change=-1, reason="Test"
    )
    assert result["change"] == -1
    stock_manager.update_stock(
        product_id=test_product_id, quantity_change=1, reason="Rollback"
    )


def test_update_stock_negative_fails(stock_manager, test_product_id):
    initial_stock = stock_manager.get_stock_level(test_product_id)
    with pytest.raises(ValueError, match="Cannot reduce stock below 0"):
        stock_manager.update_stock(
            product_id=test_product_id,
            quantity_change=-(initial_stock.total_stock + 100),
        )


def test_cleanup_expired_reservations(
    stock_manager, test_product_id, test_conversation_id
):
    stock_level = stock_manager.get_stock_level(test_product_id)
    if stock_level.available_stock < 1:
        pytest.skip("No hay stock disponible")
    reservation = stock_manager.reserve_stock(
        product_id=test_product_id,
        quantity=1,
        conversation_id=test_conversation_id,
        tenant_id="demo",
        duration_minutes=0,
    )
    count = stock_manager.cleanup_expired_reservations()
    assert count >= 1


def test_stock_level_properties(stock_manager, test_product_id):
    stock_level = stock_manager.get_stock_level(test_product_id)
    if stock_level.available_stock > 0:
        assert stock_level.is_available is True
    else:
        assert stock_level.is_available is False


def test_reserve_multiple_products(stock_manager, test_conversation_id):
    products = (
        stock_manager.supabase.table("products")
        .select("id")
        .eq("is_active", True)
        .gte("stock", 1)
        .limit(2)
        .execute()
    )
    if not products.data or len(products.data) < 2:
        pytest.skip("No hay suficientes productos con stock")
    reservations = []
    for product in products.data:
        reservation = stock_manager.reserve_stock(
            product_id=str(product["id"]),
            quantity=1,
            conversation_id=test_conversation_id,
            tenant_id="demo",
        )
        reservations.append(reservation)
    assert len(reservations) == 2
    for reservation in reservations:
        stock_manager.release_stock(str(reservation.id))
