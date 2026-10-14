"""
Schemas de Pydantic para Sales

Maneja ventas con múltiples items y cálculos automáticos
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from decimal import Decimal
from datetime import datetime, date
from enum import Enum


# ============================================
# ENUMS
# ============================================

class SaleStatus(str, Enum):
    """Estados posibles de una venta"""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


# ============================================
# SCHEMAS DE ITEMS
# ============================================

class SaleItemCreate(BaseModel):
    """Schema para crear un item de venta"""
    
    product_id: str = Field(
        ...,
        description="ID del producto"
    )
    
    product_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Nombre del producto"
    )
    
    quantity: int = Field(
        ...,
        gt=0,
        description="Cantidad del producto"
    )
    
    unit_price: Decimal = Field(
        ...,
        gt=0,
        decimal_places=2,
        description="Precio unitario"
    )
    
    discount: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        decimal_places=2,
        description="Descuento aplicado"
    )
    
    @field_validator('quantity')
    @classmethod
    def validate_quantity(cls, v):
        """Validar que la cantidad sea positiva"""
        if v <= 0:
            raise ValueError("La cantidad debe ser mayor a 0")
        return v
    
    @field_validator('unit_price')
    @classmethod
    def validate_price(cls, v):
        """Validar que el precio sea positivo"""
        if v <= 0:
            raise ValueError("El precio debe ser mayor a 0")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "product_id": "123e4567-e89b-12d3-a456-426614174000",
                "product_name": "Laptop Dell XPS 15",
                "quantity": 1,
                "unit_price": 1299.99,
                "discount": 100.00
            }
        }


class SaleItemResponse(BaseModel):
    """Schema de respuesta para un item de venta"""
    
    id: str
    product_id: str
    product_name: str
    quantity: int
    unit_price: Decimal
    discount: Decimal
    subtotal: Decimal = Field(..., description="Subtotal del item (qty * price - discount)")
    created_at: datetime
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "item-123",
                "product_id": "prod-456",
                "product_name": "Laptop Dell XPS 15",
                "quantity": 1,
                "unit_price": 1299.99,
                "discount": 100.00,
                "subtotal": 1199.99,
                "created_at": "2024-01-26T10:00:00"
            }
        }


# ============================================
# SCHEMAS DE VENTA (Request)
# ============================================

class SaleCreate(BaseModel):
    """Schema para crear una venta"""
    
    customer_phone: str = Field(
        ...,
        min_length=10,
        max_length=20,
        description="Teléfono del cliente",
        pattern=r"^\+?[1-9]\d{1,14}$"
    )
    
    customer_name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="Nombre del cliente"
    )
    
    items: List[SaleItemCreate] = Field(
        ...,
        min_length=1,
        description="Items de la venta (mínimo 1)"
    )
    
    metadata: Optional[dict] = Field(
        default_factory=dict,
        description="Metadata adicional"
    )
    
    @field_validator('items')
    @classmethod
    def validate_items(cls, v):
        """Validar que haya al menos un item"""
        if not v or len(v) == 0:
            raise ValueError("Debe haber al menos un item en la venta")
        return v
    
    @field_validator('customer_phone')
    @classmethod
    def validate_phone(cls, v):
        """Validar formato de teléfono"""
        # Limpiar espacios
        v = v.strip()
        
        # Debe empezar con + o número
        if not v.startswith('+') and not v[0].isdigit():
            raise ValueError("Teléfono debe empezar con + o número")
        
        # Solo números después del +
        digits = v[1:] if v.startswith('+') else v
        if not digits.isdigit():
            raise ValueError("Teléfono solo puede contener números")
        
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "customer_phone": "+573001234567",
                "customer_name": "Juan Pérez",
                "items": [
                    {
                        "product_id": "123e4567-e89b-12d3-a456-426614174000",
                        "product_name": "Laptop Dell XPS 15",
                        "quantity": 1,
                        "unit_price": 1299.99,
                        "discount": 100.00
                    }
                ],
                "metadata": {
                    "source": "whatsapp",
                    "conversation_id": "conv-123"
                }
            }
        }


class SaleUpdate(BaseModel):
    """Schema para actualizar una venta"""
    
    customer_name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255
    )
    
    status: Optional[SaleStatus] = None
    
    metadata: Optional[dict] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "customer_name": "Juan Pérez García",
                "status": "confirmed"
            }
        }


# ============================================
# SCHEMAS DE RESPUESTA
# ============================================

class SaleResponse(BaseModel):
    """Schema de respuesta para una venta"""
    
    id: str
    tenant_id: str
    customer_phone: str
    customer_name: Optional[str] = None
    status: str
    
    # Totales calculados
    subtotal: Decimal = Field(..., description="Subtotal sin impuestos")
    tax: Decimal = Field(..., description="Impuestos (19%)")
    total: Decimal = Field(..., description="Total a pagar")
    
    # Items (opcional, solo si se solicitan)
    items: Optional[List[SaleItemResponse]] = None
    
    # Fechas
    created_at: datetime
    confirmed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Metadata
    metadata: Optional[dict] = None
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "sale-123",
                "tenant_id": "tenant-abc",
                "customer_phone": "+573001234567",
                "customer_name": "Juan Pérez",
                "status": "confirmed",
                "subtotal": 1199.99,
                "tax": 227.99,
                "total": 1427.98,
                "items": [
                    {
                        "id": "item-1",
                        "product_name": "Laptop Dell XPS 15",
                        "quantity": 1,
                        "unit_price": 1299.99,
                        "discount": 100.00,
                        "subtotal": 1199.99
                    }
                ],
                "created_at": "2024-01-26T10:00:00",
                "confirmed_at": "2024-01-26T10:05:00",
                "completed_at": None,
                "metadata": {}
            }
        }


class SaleListResponse(BaseModel):
    """Schema de respuesta para lista de ventas"""
    
    sales: List[SaleResponse]
    total: int = Field(..., description="Total de ventas")
    page: int = Field(default=1)
    page_size: int = Field(default=20)
    
    class Config:
        json_schema_extra = {
            "example": {
                "sales": [],
                "total": 0,
                "page": 1,
                "page_size": 20
            }
        }


# ============================================
# SCHEMAS DE REPORTES
# ============================================

class SaleReportByDate(BaseModel):
    """Schema para reporte de ventas por fecha"""
    
    date: date
    total_sales: int = Field(..., description="Cantidad de ventas")
    total_amount: Decimal = Field(..., description="Monto total")
    
    # Por estado
    pending: int = 0
    confirmed: int = 0
    completed: int = 0
    cancelled: int = 0
    
    class Config:
        json_schema_extra = {
            "example": {
                "date": "2024-01-26",
                "total_sales": 10,
                "total_amount": 15000.00,
                "pending": 2,
                "confirmed": 5,
                "completed": 3,
                "cancelled": 0
            }
        }


class SaleReportByMonth(BaseModel):
    """Schema para reporte mensual"""
    
    year: int
    month: int
    total_sales: int
    total_amount: Decimal
    
    # Desglose por estado
    by_status: dict[str, int] = Field(
        default_factory=dict,
        description="Ventas por estado"
    )
    
    # Top productos
    top_products: Optional[List[dict]] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "year": 2024,
                "month": 1,
                "total_sales": 150,
                "total_amount": 250000.00,
                "by_status": {
                    "pending": 20,
                    "confirmed": 80,
                    "completed": 45,
                    "cancelled": 5
                },
                "top_products": [
                    {
                        "product_name": "Laptop Dell XPS 15",
                        "quantity_sold": 25,
                        "total_revenue": 32499.75
                    }
                ]
            }
        }


# ============================================
# SCHEMAS AUXILIARES
# ============================================

class SaleSearchSchema(BaseModel):
    """Schema para búsqueda de ventas"""
    
    customer_phone: Optional[str] = None
    status: Optional[SaleStatus] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    min_amount: Optional[Decimal] = Field(None, ge=0)
    max_amount: Optional[Decimal] = Field(None, ge=0)
    
    class Config:
        json_schema_extra = {
            "example": {
                "customer_phone": "+573001234567",
                "status": "completed",
                "date_from": "2024-01-01",
                "date_to": "2024-01-31",
                "min_amount": 100.00,
                "max_amount": 5000.00
            }
        }