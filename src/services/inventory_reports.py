"""Reportes de inventario"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from supabase import create_client
from src.config import settings
from src.core.logger import logger


class InventoryReportService:
    """Servicio de reportes de inventario"""
    
    def __init__(self):
        self.supabase = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY
        )
    
    def get_product_rotation(
        self,
        tenant_id: str,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Calcula rotación de productos (ventas en período)
        
        Args:
            tenant_id: ID del tenant
            days: Período en días (default 30)
            
        Returns:
            Lista de productos con estadísticas de rotación
        """
        result = self.supabase.rpc(
            'get_product_rotation',
            {'p_tenant_id': tenant_id, 'p_days': days}
        ).execute()
        
        products = []
        for row in result.data:
            classification = self._classify_rotation(
                row['units_sold'],
                float(row['rotation_rate'])
            )
            
            products.append({
                'product_id': row['id'],
                'product_name': row['name'],
                'category': row['category'],
                'current_stock': row['current_stock'],
                'units_sold': row['units_sold'],
                'avg_sale_quantity': float(row['avg_sale_quantity']),
                'rotation_rate': float(row['rotation_rate']),
                'classification': classification,
                'period_days': days
            })
        
        logger.info(f"📊 Reporte de rotación generado: {len(products)} productos")
        return products
    
    def _classify_rotation(self, units_sold: int, rotation_rate: float) -> str:
        """Clasifica rotación del producto"""
        if units_sold == 0:
            return 'no_movement'
        elif rotation_rate >= 2.0:
            return 'high_rotation'
        elif rotation_rate >= 0.5:
            return 'medium_rotation'
        else:
            return 'low_rotation'
    
    def get_stale_products(
        self,
        tenant_id: str,
        days_threshold: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Detecta productos sin movimiento en X días
        
        Args:
            tenant_id: ID del tenant
            days_threshold: Días sin movimiento (default 30)
            
        Returns:
            Lista de productos sin movimiento
        """
        result = self.supabase.rpc(
            'get_stale_products',
            {
                'p_tenant_id': tenant_id,
                'p_days_threshold': days_threshold
            }
        ).execute()
        
        stale_products = []
        for row in result.data:
            days_inactive = row['days_since_last_movement'] or (days_threshold + 1)
            
            stale_products.append({
                'product_id': row['id'],
                'product_name': row['name'],
                'category': row['category'],
                'current_stock': row['stock'],
                'last_movement_date': row['last_movement_date'],
                'days_since_last_movement': days_inactive,
                'risk_level': self._calculate_risk_level(days_inactive, row['stock'])
            })
        
        logger.warning(f"⚠️  {len(stale_products)} productos sin movimiento")
        return stale_products
    
    def _calculate_risk_level(self, days_inactive: int, stock: int) -> str:
        """Calcula nivel de riesgo de producto sin movimiento"""
        if days_inactive >= 90 and stock > 10:
            return 'high'
        elif days_inactive >= 60:
            return 'medium'
        elif days_inactive >= 30:
            return 'low'
        else:
            return 'none'
    
    def get_stock_adjustments_history(
        self,
        product_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        days: int = 30,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Obtiene historial de ajustes manuales de stock
        
        Args:
            product_id: Filtrar por producto (opcional)
            tenant_id: Filtrar por tenant (opcional)
            days: Período en días
            limit: Máximo de registros
            
        Returns:
            Historial de ajustes
        """
        start_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        query = self.supabase.table('stock_movements')\
            .select('*')\
            .eq('movement_type', 'adjustment')\
            .gte('created_at', start_date)\
            .order('created_at', desc=True)\
            .limit(limit)
        
        if product_id:
            query = query.eq('product_id', product_id)
        
        if tenant_id:
            query = query.eq('tenant_id', tenant_id)
        
        result = query.execute()
        
        adjustments = []
        for row in result.data:
            adjustments.append({
                'id': row['id'],
                'product_id': row['product_id'],
                'quantity_change': row['quantity'],
                'stock_before': row['stock_before'],
                'stock_after': row['stock_after'],
                'reason': row['reason'],
                'notes': row['notes'],
                'user_id': row['user_id'],
                'created_at': row['created_at']
            })
        
        logger.info(f"📝 {len(adjustments)} ajustes de stock encontrados")
        return adjustments