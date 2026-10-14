"""
Servicio de búsqueda de productos con cache
"""

from typing import List, Dict, Any
from supabase import create_client

from src.config import settings
from src.services.cache_service import get_cache


class ProductSearchService:
    """Búsqueda de productos con cache automático"""
    
    def __init__(self):
        self.supabase = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY
        )
        self.cache = get_cache()
    
    def search_products(self, query: str, tenant_id: str = None) -> List[Dict[str, Any]]:
        """
        Busca productos con cache automático
        
        Args:
            query: Término de búsqueda
            tenant_id: ID del tenant (opcional)
        
        Returns:
            Lista de productos
        """
        # Intentar obtener del cache
        cached = self.cache.get('products:search', query=query, tenant_id=tenant_id)
        if cached is not None:
            return cached
        
        # Cache miss - buscar en BD
        result = self.supabase.rpc(
            'search_products',
            {'search_query': query}
        ).execute()
        
        products = result.data if result.data else []
        
        # Guardar en cache
        self.cache.set('products:search', products, query=query, tenant_id=tenant_id)
        
        return products
    
    def get_product_by_id(self, product_id: str) -> Dict[str, Any]:
        """Obtiene producto por ID con cache"""
        # Intentar cache
        cached = self.cache.get('products:id', product_id=product_id)
        if cached is not None:
            return cached
        
        # Cache miss
        result = self.supabase.table('products')\
            .select('*')\
            .eq('id', product_id)\
            .single()\
            .execute()
        
        product = result.data if result.data else {}
        
        # Guardar en cache
        self.cache.set('products:id', product, product_id=product_id)
        
        return product
    
    def invalidate_product_cache(self, product_id: str = None):
        """Invalida cache de productos (cuando se actualiza)"""
        if product_id:
            self.cache.invalidate('products:id', product_id=product_id)
        
        # Invalidar todas las búsquedas
        self.cache.invalidate_prefix('products:search')