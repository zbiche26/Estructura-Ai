"""Tests para ProductSearchService con cache"""

import pytest
from unittest.mock import Mock, patch
from src.services.product_search_service import ProductSearchService


@pytest.fixture
def mock_supabase():
    """Mock de Supabase client"""
    with patch("src.services.product_search_service.create_client") as mock:
        client = Mock()
        mock.return_value = client
        yield client


def test_search_products_cache_miss(mock_supabase):
    """Test: Primera busqueda va a BD (cache miss)"""
    mock_supabase.rpc.return_value.execute.return_value.data = [
        {"id": "1", "name": "Silla Ejecutiva", "price": 100}
    ]
    service = ProductSearchService()
    result = service.search_products("silla")
    assert len(result) == 1
    assert result[0]["name"] == "Silla Ejecutiva"
    assert mock_supabase.rpc.called


def test_search_products_cache_hit(mock_supabase):
    """Test: Segunda busqueda usa cache (cache hit)"""
    mock_supabase.rpc.return_value.execute.return_value.data = [
        {"id": "1", "name": "Silla", "price": 100}
    ]
    service = ProductSearchService()
    result1 = service.search_products("silla")
    mock_supabase.rpc.reset_mock()
    result2 = service.search_products("silla")
    assert result1 == result2
    assert not mock_supabase.rpc.called


def test_invalidate_cache(mock_supabase):
    """Test: Invalidar cache fuerza nueva busqueda en BD"""
    mock_supabase.rpc.return_value.execute.return_value.data = [
        {"id": "1", "name": "Silla", "price": 100}
    ]
    service = ProductSearchService()
    service.search_products("silla")
    mock_supabase.rpc.reset_mock()
    service.invalidate_product_cache()
    service.search_products("silla")
    assert mock_supabase.rpc.called


@pytest.mark.skip(reason="requires real Supabase")
def test_cache_stats():
    """Test: Verificar estadisticas del cache"""
    service = ProductSearchService()
    service.search_products("silla")
    service.search_products("silla")
    service.search_products("mesa")
    stats = service.cache.get_stats()
    assert stats["hits"] >= 1
    assert stats["misses"] >= 1
    assert stats["hit_rate"] > 0
