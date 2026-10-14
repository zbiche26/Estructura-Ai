"""Sistema de alertas de bajo stock"""

from typing import List, Dict, Any
from supabase import create_client
from src.config import settings
from src.core.logger import logger
from src.core.event_bus import event_bus


class StockAlertService:
    """Servicio de alertas de stock"""
    
    def __init__(self):
        self.supabase = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY
        )
    
    def check_low_stock(self, threshold: int = 10) -> List[Dict[str, Any]]:
        """
        Revisa productos con stock bajo y crea alertas
        
        Args:
            threshold: Nivel mínimo de stock
            
        Returns:
            Lista de alertas creadas
        """
        # Buscar productos con stock bajo
        result = self.supabase.table('products')\
            .select('id, name, stock, category, tenant_id')\
            .eq('is_active', True)\
            .lte('stock', threshold)\
            .execute()
        
        alerts = []
        
        for product in result.data:
            # Crear alerta en BD
            alert_result = self.supabase.rpc(
                'create_stock_alert',
                {
                    'p_product_id': product['id'],
                    'p_tenant_id': product['tenant_id'],
                    'p_current_stock': product['stock'],
                    'p_threshold': threshold
                }
            ).execute()
            
            alert_data = {
                'alert_id': alert_result.data,
                'product_id': product['id'],
                'product_name': product['name'],
                'current_stock': product['stock'],
                'threshold': threshold,
                'category': product['category'],
                'tenant_id': product['tenant_id'],
                'severity': 'critical' if product['stock'] <= 5 else 'warning'
            }
            
            alerts.append(alert_data)
            
            # Publicar evento para notificaciones
            event_bus.publish('low_stock_alert', alert_data)
        
        logger.info(f"✅ {len(alerts)} alertas de stock bajo generadas")
        return alerts
    
    def get_active_alerts(self, tenant_id: str = None) -> List[Dict[str, Any]]:
        """Obtiene alertas activas"""
        query = self.supabase.table('stock_alerts')\
            .select('*')\
            .eq('status', 'active')\
            .order('severity', desc=True)\
            .order('created_at', desc=True)
        
        if tenant_id:
            query = query.eq('tenant_id', tenant_id)
        
        result = query.execute()
        return result.data
    
    def resolve_alert(self, alert_id: str, resolved_by: str = None) -> bool:
        """Marca alerta como resuelta"""
        result = self.supabase.rpc(
            'resolve_stock_alert',
            {
                'p_alert_id': alert_id,
                'p_resolved_by': resolved_by
            }
        ).execute()
        
        return result.data

        