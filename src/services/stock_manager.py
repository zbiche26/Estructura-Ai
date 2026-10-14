"""
Stock Manager - Gestión transaccional de inventario
"""

from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from uuid import UUID

from supabase import create_client
from src.config import settings
from src.models.stock import (
    StockReservation,
    StockLevel,
    ReservationCreate,
    StockUpdate
)


class StockManager:
    """Gestión de stock con reservas transaccionales"""
    
    def __init__(self):
        self.supabase = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY
        )
    
    def get_stock_level(self, product_id: str) -> StockLevel:
        """
        Obtiene nivel de stock (total, reservado, disponible)
        
        Args:
            product_id: UUID del producto
        
        Returns:
            StockLevel con información completa
        """
        result = self.supabase.rpc(
            'get_available_stock',
            {'p_product_id': product_id}
        ).execute()
        
        if not result.data or len(result.data) == 0:
            raise ValueError(f"Product {product_id} not found")
        
        stock_data = result.data[0]
        
        return StockLevel(
            product_id=product_id,
            total_stock=stock_data['total_stock'] or 0,
            reserved_stock=stock_data['reserved_stock'] or 0,
            available_stock=stock_data['available_stock'] or 0
        )
    
    def reserve_stock(
        self,
        product_id: str,
        quantity: int,
        conversation_id: str,
        tenant_id: str,
        duration_minutes: int = 30
    ) -> StockReservation:
        """
        Reserva stock durante una conversación
        
        Args:
            product_id: UUID del producto
            quantity: Cantidad a reservar
            conversation_id: UUID de la conversación
            tenant_id: ID del tenant
            duration_minutes: Duración de la reserva (default 30 min)
        
        Returns:
            StockReservation creada
        
        Raises:
            ValueError: Si no hay stock suficiente
        """
        # 1. Verificar stock disponible
        stock_level = self.get_stock_level(product_id)
        
        if not stock_level.can_reserve(quantity):
            raise ValueError(
                f"Insufficient stock. Available: {stock_level.available_stock}, "
                f"Requested: {quantity}"
            )
        
        # 2. Crear reserva
        expires_at = datetime.now() + timedelta(minutes=duration_minutes)
        
        reservation_data = {
            'product_id': product_id,
            'conversation_id': conversation_id,
            'tenant_id': tenant_id,
            'quantity': quantity,
            'status': 'active',
            'expires_at': expires_at.isoformat()
        }
        
        result = self.supabase.table('stock_reservations')\
            .insert(reservation_data)\
            .execute()
        
        if not result.data:
            raise Exception("Failed to create reservation")
        
        return StockReservation(**result.data[0])
    
    def release_stock(self, reservation_id: str) -> bool:
        """
        Libera una reserva (usuario no compró)
        
        Args:
            reservation_id: UUID de la reserva
        
        Returns:
            True si se liberó correctamente
        """
        result = self.supabase.table('stock_reservations')\
            .update({
                'status': 'released',
                'released_at': datetime.now().isoformat()
            })\
            .eq('id', reservation_id)\
            .eq('status', 'active')\
            .execute()
        
        return len(result.data) > 0
    
    def complete_reservation(self, reservation_id: str) -> bool:
        """
        Completa una reserva (usuario compró)
        
        Args:
            reservation_id: UUID de la reserva
        
        Returns:
            True si se completó correctamente
        """
        # 1. Marcar reserva como completada
        result = self.supabase.table('stock_reservations')\
            .update({
                'status': 'completed',
                'completed_at': datetime.now().isoformat()
            })\
            .eq('id', reservation_id)\
            .eq('status', 'active')\
            .execute()
        
        if not result.data:
            return False
        
        # 2. Reducir stock del producto
        reservation = result.data[0]
        
        self.supabase.rpc(
            'update_product_stock',
            {
                'p_product_id': reservation['product_id'],
                'p_quantity_change': -reservation['quantity']
            }
        ).execute()
        
        return True
    
    def update_stock(
        self,
        product_id: str,
        quantity_change: int,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Actualiza stock de un producto (transaccional)
        
        Args:
            product_id: UUID del producto
            quantity_change: Cambio en cantidad (positivo o negativo)
            reason: Razón del cambio
        
        Returns:
            Información del stock actualizado
        """
        # Obtener producto actual
        product = self.supabase.table('products')\
            .select('stock')\
            .eq('id', product_id)\
            .single()\
            .execute()
        
        if not product.data:
            raise ValueError(f"Product {product_id} not found")
        
        current_stock = product.data['stock']
        new_stock = current_stock + quantity_change
        
        if new_stock < 0:
            raise ValueError(
                f"Cannot reduce stock below 0. "
                f"Current: {current_stock}, Change: {quantity_change}"
            )
        
        # Actualizar stock
        result = self.supabase.table('products')\
            .update({'stock': new_stock})\
            .eq('id', product_id)\
            .execute()
        
        return {
            'product_id': product_id,
            'old_stock': current_stock,
            'new_stock': new_stock,
            'change': quantity_change,
            'reason': reason
        }
    
    def cleanup_expired_reservations(self) -> int:
        """
        Limpia reservas expiradas
        
        Returns:
            Número de reservas liberadas
        """
        result = self.supabase.table('stock_reservations')\
            .update({
                'status': 'released',
                'released_at': datetime.now().isoformat()
            })\
            .eq('status', 'active')\
            .lt('expires_at', datetime.now().isoformat())\
            .execute()
        
        return len(result.data) if result.data else 0