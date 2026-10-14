"""
Product Repository - Gestión de Productos

Repository específico para la entidad Product con métodos
adicionales para búsqueda y filtrado de productos.

Uso:
    from src.repositories.product_repository import product_repo
    
    # Buscar productos en stock
    products = product_repo.get_in_stock()
    
    # Buscar por categoría
    electronics = product_repo.find_by_category("Electrónica")
"""

from typing import List, Optional
from decimal import Decimal
from uuid import UUID
from datetime import datetime, timedelta

from src.repositories.base import BaseRepository
from src.models import Product
from src.core.logger import logger
from src.core.database import db
from src.core.tenant_context import TenantContextManager


class ProductRepository(BaseRepository[Product]):
    """
    Repository para gestionar productos
    
    Hereda todas las operaciones CRUD de BaseRepository
    y agrega métodos específicos para productos.
    """
    
    def __init__(self, client=None):
        """Inicializa el repository de productos"""
        super().__init__(
            table_name="products",
            model_class=Product,
            client=client or db.client
        )
    
    # ============================================
    # BÚSQUEDAS ESPECÍFICAS
    # ============================================
    
    def find_by_sku(self, sku: str) -> Optional[Product]:
        """
        Busca un producto por su SKU
        
        Args:
            sku: Código SKU del producto
        
        Returns:
            Producto encontrado o None
        """
        try:
            results = self.find({"sku": sku}, limit=1)
            return results[0] if results else None
        except Exception as e:
            logger.error(f"❌ Error al buscar producto por SKU {sku}: {e}")
            return None
    
    def find_by_category(
        self,
        category: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[Product]:
        """
        Busca productos por categoría
        
        Args:
            category: Nombre de la categoría
            limit: Número máximo de resultados
            offset: Offset para paginación
        
        Returns:
            Lista de productos
        """
        try:
            return self.find(
                {"category": category, "is_active": True},
                limit=limit,
                offset=offset
            )
        except Exception as e:
            logger.error(f"❌ Error al buscar productos por categoría {category}: {e}")
            return []
    
    def search_by_name(
        self,
        search_term: str,
        limit: int = 20
    ) -> List[Product]:
        """
        Busca productos por nombre (búsqueda parcial)
        
        Args:
            search_term: Término a buscar
            limit: Número máximo de resultados
        
        Returns:
            Lista de productos que coinciden
        """
        try:
            # Query con ILIKE para búsqueda case-insensitive
            result = (
                self.client.table(self.table_name)
                .select("*")
                .ilike("name", f"%{search_term}%")
                .eq("is_active", True)
                .limit(limit)
                .execute()
            )
            
            products = [Product(**record) for record in result.data]
            
            logger.debug(f"🔍 Búsqueda '{search_term}': {len(products)} productos encontrados")
            return products
            
        except Exception as e:
            logger.error(f"❌ Error al buscar productos por nombre: {e}")
            return []
    
    # ============================================
    # FILTROS DE STOCK
    # ============================================
    
    def get_in_stock(self, limit: int = 100) -> List[Product]:
        """
        Obtiene productos que tienen stock disponible
        
        Args:
            limit: Número máximo de resultados
        
        Returns:
            Lista de productos con stock > 0
        """
        try:
            result = (
                self.client.table(self.table_name)
                .select("*")
                .gt("stock", 0)  # Greater than 0
                .eq("is_active", True)
                .limit(limit)
                .execute()
            )
            
            products = [Product(**record) for record in result.data]
            
            logger.debug(f"📦 Productos en stock: {len(products)}")
            return products
            
        except Exception as e:
            logger.error(f"❌ Error al obtener productos en stock: {e}")
            return []
    
    def get_out_of_stock(self, limit: int = 100) -> List[Product]:
        """
        Obtiene productos sin stock
        
        Args:
            limit: Número máximo de resultados
        
        Returns:
            Lista de productos con stock = 0
        """
        try:
            return self.find(
                {"stock": 0, "is_active": True},
                limit=limit
            )
        except Exception as e:
            logger.error(f"❌ Error al obtener productos sin stock: {e}")
            return []

    # ============================================
    # ANALYTICS
    # ============================================

    def get_top_consulted_products(self, last_days: int = 30, limit: int = 10) -> List[dict]:
        """Obtiene productos más consultados (vistas) para el tenant."""
        if last_days <= 0:
            raise ValueError("last_days debe ser mayor que cero")
        safe_limit = max(1, min(limit, 50))
        start_date = (datetime.utcnow().date() - timedelta(days=min(last_days, 365) - 1)).isoformat()

        try:
            query = (
                self.client.table("product_views")
                .select("product_id, product_name, product_sku, viewed_at")
                .gte("viewed_at", start_date)
            )
            tenant = TenantContextManager.get_current()
            if tenant and tenant.tenant_id:
                query = query.eq("tenant_id", tenant.tenant_id)
            result = query.execute()
        except Exception as e:
            logger.error(f"❌ Error al obtener productos consultados: {e}")
            return []

        aggregation: dict = {}
        for record in result.data or []:
            key = record.get("product_id") or "unknown"
            entry = aggregation.setdefault(key, {
                "product_id": record.get("product_id"),
                "product_name": record.get("product_name"),
                "product_sku": record.get("product_sku"),
                "views": 0,
            })
            entry["views"] += 1

        items = sorted(
            aggregation.values(),
            key=lambda x: (-x["views"], str(x.get("product_name") or "")),
        )
        return items[:safe_limit]
    
    def get_low_stock(self, limit: int = 100) -> List[Product]:
        """
        Obtiene productos con stock bajo (stock <= min_stock)
        
        Args:
            limit: Número máximo de resultados
        
        Returns:
            Lista de productos con stock bajo
        """
        try:
            # Query para productos donde stock <= min_stock
            result = (
                self.client.table(self.table_name)
                .select("*")
                .filter("stock", "lte", "min_stock")  # Less than or equal
                .eq("is_active", True)
                .limit(limit)
                .execute()
            )
            
            products = [Product(**record) for record in result.data]
            
            logger.debug(f"⚠️ Productos con stock bajo: {len(products)}")
            return products
            
        except Exception as e:
            logger.error(f"❌ Error al obtener productos con stock bajo: {e}")
            return []
    
    # ============================================
    # FILTROS DE PRECIO
    # ============================================
    
    def find_by_price_range(
        self,
        min_price: Decimal,
        max_price: Decimal,
        limit: int = 100
    ) -> List[Product]:
        """
        Busca productos en un rango de precio
        
        Args:
            min_price: Precio mínimo
            max_price: Precio máximo
            limit: Número máximo de resultados
        
        Returns:
            Lista de productos en el rango
        """
        try:
            result = (
                self.client.table(self.table_name)
                .select("*")
                .gte("price", float(min_price))  # Greater than or equal
                .lte("price", float(max_price))  # Less than or equal
                .eq("is_active", True)
                .limit(limit)
                .execute()
            )
            
            products = [Product(**record) for record in result.data]
            
            logger.debug(f"💰 Productos entre ${min_price} y ${max_price}: {len(products)}")
            return products
            
        except Exception as e:
            logger.error(f"❌ Error al buscar por rango de precio: {e}")
            return []
    
    # ============================================
    # OPERACIONES DE STOCK
    # ============================================
    
    def update_stock(self, product_id: UUID | str, quantity: int) -> Optional[Product]:
        """
        Actualiza el stock de un producto
        
        Args:
            product_id: ID del producto
            quantity: Nueva cantidad de stock
        
        Returns:
            Producto actualizado o None
        """
        try:
            if quantity < 0:
                logger.error("❌ La cantidad de stock no puede ser negativa")
                return None
            
            return self.update(product_id, {"stock": quantity})
            
        except Exception as e:
            logger.error(f"❌ Error al actualizar stock: {e}")
            return None
    
    def decrease_stock(self, product_id: UUID | str, quantity: int) -> Optional[Product]:
        """
        Disminuye el stock de un producto
        
        Args:
            product_id: ID del producto
            quantity: Cantidad a restar
        
        Returns:
            Producto actualizado o None si no hay suficiente stock
        """
        try:
            # Obtener producto actual
            product = self.get_by_id(product_id)
            
            if not product:
                logger.error(f"❌ Producto no encontrado: {product_id}")
                return None
            
            # Verificar stock suficiente
            if product.stock < quantity:
                logger.error(f"❌ Stock insuficiente. Disponible: {product.stock}, Solicitado: {quantity}")
                return None
            
            # Actualizar stock
            new_stock = product.stock - quantity
            return self.update(product_id, {"stock": new_stock})
            
        except Exception as e:
            logger.error(f"❌ Error al disminuir stock: {e}")
            return None
    
    def increase_stock(self, product_id: UUID | str, quantity: int) -> Optional[Product]:
        """
        Aumenta el stock de un producto
        
        Args:
            product_id: ID del producto
            quantity: Cantidad a agregar
        
        Returns:
            Producto actualizado o None
        """
        try:
            # Obtener producto actual
            product = self.get_by_id(product_id)
            
            if not product:
                logger.error(f"❌ Producto no encontrado: {product_id}")
                return None
            
            # Actualizar stock
            new_stock = product.stock + quantity
            return self.update(product_id, {"stock": new_stock})
            
        except Exception as e:
            logger.error(f"❌ Error al aumentar stock: {e}")
            return None
    
    # ============================================
    # ACTIVAR/DESACTIVAR
    # ============================================
    
    def activate(self, product_id: UUID | str) -> Optional[Product]:
        """Activa un producto"""
        return self.update(product_id, {"is_active": True})
    
    def deactivate(self, product_id: UUID | str) -> Optional[Product]:
        """Desactiva un producto"""
        return self.update(product_id, {"is_active": False})
    
    # ============================================
    # ESTADÍSTICAS
    # ============================================
    
    def get_total_value(self) -> Decimal:
        """
        Calcula el valor total del inventario (stock * price)
        
        Returns:
            Valor total del inventario
        """
        try:
            products = self.get_all(limit=10000)  # Todos los productos
            total = sum(
                Decimal(str(p.price)) * Decimal(str(p.stock))
                for p in products
                if p.is_active
            )
            
            logger.debug(f"💰 Valor total del inventario: ${total}")
            return total
            
        except Exception as e:
            logger.error(f"❌ Error al calcular valor total: {e}")
            return Decimal("0")
    
    def get_stats(self) -> dict:
        """
        Obtiene estadísticas del inventario
        
        Returns:
            Diccionario con estadísticas
        """
        try:
            stats = {
                "total_products": self.count({"is_active": True}),
                "in_stock": len(self.get_in_stock()),
                "out_of_stock": len(self.get_out_of_stock()),
                "low_stock": len(self.get_low_stock()),
                "total_value": float(self.get_total_value())
            }
            
            logger.debug(f"📊 Estadísticas del inventario: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"❌ Error al obtener estadísticas: {e}")
            return {}


# ============================================
# INSTANCIA GLOBAL
# ============================================
product_repo = ProductRepository()


# ============================================
# EJEMPLO DE USO
# ============================================
if __name__ == "__main__":
    from src.core.tenant_context import TenantContextManager
    
    # Configurar tenant
    tenant_manager = TenantContextManager()
    tenant_manager.set_tenant("00000000-0000-0000-0000-000000000001")
    
    print("\n📦 PRODUCT REPOSITORY - EJEMPLOS")
    print("=" * 60)
    
    # 1. Obtener todos los productos
    print("\n1️⃣ Todos los productos:")
    products = product_repo.get_all(limit=5)
    for p in products:
        print(f"  - {p.name}: ${p.price} (Stock: {p.stock})")
    
    # 2. Buscar por categoría
    print("\n2️⃣ Productos de categoría 'Accesorios':")
    accessories = product_repo.find_by_category("Accesorios")
    for p in accessories:
        print(f"  - {p.name}")
    
    # 3. Productos en stock
    print("\n3️⃣ Productos en stock:")
    in_stock = product_repo.get_in_stock()
    print(f"  Total: {len(in_stock)} productos")
    
    # 4. Estadísticas
    print("\n4️⃣ Estadísticas del inventario:")
    stats = product_repo.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print("\n" + "=" * 60)