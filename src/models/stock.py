"""
Modelos de dominio para gestión de stock
"""

from datetime import datetime, timedelta
from typing import Optional, Literal
from pydantic import BaseModel, Field, UUID4, field_validator


class StockReservation(BaseModel):
    """Modelo de reserva de stock"""
    
    id: Optional[UUID4] = None
    product_id: UUID4
    conversation_id: UUID4
    tenant_id: str
    quantity: int = Field(gt=0, description="Cantidad debe ser mayor a 0")
    status: Literal['active', 'released', 'completed'] = 'active'
    
    created_at: Optional[datetime] = None
    expires_at: datetime
    released_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    notes: Optional[str] = None
    
    @field_validator('quantity')
    @classmethod
    def validate_quantity(cls, v):
        if v <= 0:
            raise ValueError('Quantity must be greater than 0')
        return v
    
    class Config:
        from_attributes = True


class StockLevel(BaseModel):
    """Nivel de stock de un producto"""
    
    product_id: UUID4
    total_stock: int = Field(ge=0)
    reserved_stock: int = Field(ge=0)
    available_stock: int = Field(ge=0)
    
    @property
    def is_available(self) -> bool:
        """¿Hay stock disponible?"""
        return self.available_stock > 0
    
    def can_reserve(self, quantity: int) -> bool:
        """¿Se puede reservar esta cantidad?"""
        return self.available_stock >= quantity


class ReservationCreate(BaseModel):
    """DTO para crear reserva"""
    
    product_id: UUID4
    conversation_id: UUID4
    quantity: int = Field(gt=0)
    duration_minutes: int = Field(default=30, ge=5, le=120)
    notes: Optional[str] = None


class StockUpdate(BaseModel):
    """DTO para actualizar stock"""
    
    product_id: UUID4
    quantity_change: int  # Puede ser positivo (aumentar) o negativo (reducir)
    reason: Optional[str] = None