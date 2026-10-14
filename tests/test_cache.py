"""Tests para el sistema de cache"""

import pytest
import time
from src.services.cache_service import CacheService, get_cache


def test_cache_set_and_get():
    """Test: Guardar y recuperar del cache"""
    cache = CacheService()
    
    cache.set('products', {'id': 1, 'name': 'Silla'}, query='silla')
    result = cache.get('products', query='silla')
    
    assert result == {'id': 1, 'name': 'Silla'}


def test_cache_miss():
    """Test: Cache miss cuando no existe"""
    cache = CacheService()
    
    result = cache.get('products', query='mesa')
    
    assert result is None


def test_cache_expiration():
    """Test: Cache expira después de TTL"""
    cache = CacheService(ttl_minutes=0.01)  # 0.6 segundos
    
    cache.set('products', {'id': 1}, query='test')
    time.sleep(1)
    result = cache.get('products', query='test')
    
    assert result is None


def test_cache_lru_eviction():
    """Test: Evicción LRU cuando está lleno"""
    cache = CacheService(max_size=3)
    
    cache.set('products', 'value1', query='a')
    cache.set('products', 'value2', query='b')
    cache.set('products', 'value3', query='c')
    
    # Acceder 'a' para que sea más reciente
    cache.get('products', query='a')
    
    # Agregar cuarto elemento (debe eliminar 'b' que es el menos usado)
    cache.set('products', 'value4', query='d')
    
    assert cache.get('products', query='a') == 'value1'
    assert cache.get('products', query='b') is None
    assert cache.get('products', query='c') == 'value3'
    assert cache.get('products', query='d') == 'value4'


def test_cache_invalidate():
    """Test: Invalidar entrada específica"""
    cache = CacheService()
    
    cache.set('products', 'value1', query='silla')
    cache.invalidate('products', query='silla')
    result = cache.get('products', query='silla')
    
    assert result is None


def test_cache_invalidate_prefix():
    """Test: Invalidar por prefijo"""
    cache = CacheService()
    
    cache.set('products', 'value1', query='a')
    cache.set('products', 'value2', query='b')
    cache.set('conversations', 'value3', id=1)
    
    cache.invalidate_prefix('products')
    
    assert cache.get('products', query='a') is None
    assert cache.get('products', query='b') is None
    assert cache.get('conversations', id=1) == 'value3'


def test_cache_stats():
    """Test: Estadísticas del cache"""
    cache = CacheService()
    
    cache.set('products', 'value1', query='a')
    
    cache.get('products', query='a')  # Hit
    cache.get('products', query='b')  # Miss
    cache.get('products', query='a')  # Hit
    
    stats = cache.get_stats()
    
    assert stats['hits'] == 2
    assert stats['misses'] == 1
    assert stats['hit_rate'] == 66.67


def test_cache_singleton():
    """Test: get_cache retorna mismo instance"""
    cache1 = get_cache()
    cache2 = get_cache()
    
    assert cache1 is cache2