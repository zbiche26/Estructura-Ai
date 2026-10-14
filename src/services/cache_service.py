"""
Sistema de Cache en Memoria
Reduce consultas a BD para búsquedas frecuentes
"""

from typing import Any, Optional, Dict
from datetime import datetime, timedelta
import hashlib
import json


class CacheService:
    """
    Cache en memoria para búsquedas frecuentes
    
    Features:
    - Límite de 100 entradas (LRU - Least Recently Used)
    - TTL configurable (default: 5 minutos)
    - Métricas de hits/misses
    """
    
    def __init__(self, max_size: int = 100, ttl_minutes: int = 5):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._max_size = max_size
        self._ttl = timedelta(minutes=ttl_minutes)
        
        # Métricas
        self._hits = 0
        self._misses = 0
    
    def _generate_key(self, prefix: str, **kwargs) -> str:
        """Genera clave única para cache"""
        data = json.dumps(kwargs, sort_keys=True)
        hash_value = hashlib.md5(data.encode()).hexdigest()
        return f"{prefix}:{hash_value}"
    
    def get(self, prefix: str, **kwargs) -> Optional[Any]:
        """
        Obtiene valor del cache
        
        Returns:
            Valor si existe y no expiró, None si no
        """
        key = self._generate_key(prefix, **kwargs)
        
        if key not in self._cache:
            self._misses += 1
            return None
        
        entry = self._cache[key]
        
        # Verificar si expiró
        if datetime.now() > entry['expires_at']:
            del self._cache[key]
            self._misses += 1
            return None
        
        # Hit
        self._hits += 1
        entry['last_accessed'] = datetime.now()
        return entry['value']
    
    def set(self, prefix: str, value: Any, **kwargs):
        """Guarda valor en cache"""
        key = self._generate_key(prefix, **kwargs)
        
        # Si está lleno, eliminar el menos usado (LRU)
        if len(self._cache) >= self._max_size and key not in self._cache:
            self._evict_lru()
        
        self._cache[key] = {
            'value': value,
            'created_at': datetime.now(),
            'expires_at': datetime.now() + self._ttl,
            'last_accessed': datetime.now()
        }
    
    def _evict_lru(self):
        """Elimina la entrada menos recientemente usada"""
        if not self._cache:
            return
        
        lru_key = min(
            self._cache.keys(),
            key=lambda k: self._cache[k]['last_accessed']
        )
        del self._cache[lru_key]
    
    def invalidate(self, prefix: str, **kwargs):
        """Invalida entrada específica del cache"""
        key = self._generate_key(prefix, **kwargs)
        if key in self._cache:
            del self._cache[key]
    
    def invalidate_prefix(self, prefix: str):
        """Invalida todas las entradas con un prefijo"""
        keys_to_delete = [
            k for k in self._cache.keys()
            if k.startswith(prefix)
        ]
        for key in keys_to_delete:
            del self._cache[key]
    
    def clear(self):
        """Limpia todo el cache"""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estadísticas del cache"""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0
        
        return {
            'hits': self._hits,
            'misses': self._misses,
            'total_requests': total,
            'hit_rate': round(hit_rate, 2),
            'cache_size': len(self._cache),
            'max_size': self._max_size
        }


# Singleton global
_cache_instance: Optional[CacheService] = None


def get_cache() -> CacheService:
    """Obtiene instancia singleton del cache"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = CacheService()
    return _cache_instance