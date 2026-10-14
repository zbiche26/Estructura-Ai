"""
Schemas de Pydantic para Product

Estos schemas definen:
- Cómo validar datos de entrada (Create, Update)
- Cómo formatear datos de salida (Response)
- Documentación automática de la API
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from decimal import Decimal
from datetime import datetime


# ============================================
# SCHEMAS DE ENTRADA (Request)
# ============================================

class ProductCreate(BaseModel):
    """Schema para crear un producto"""
    
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Nombre del producto",
        examples=["Laptop Dell XPS 15"]
    )
    
    description: Optional[str] = Field(
        None,
        max_length=1000,
        description="Descripción detallada del producto"
    )
    
    price: Decimal = Field(
        ...,
        gt=0,
        decimal_places=2,
        description="Precio de venta",
        examples=[1299.99]
    )
    
    cost: Optional[Decimal] = Field(
        None,
        ge=0,
        decimal_places=2,
        description="Costo del producto"
    )
    
    stock: int = Field(
        default=0,
        ge=0,
        description="Cantidad en inventario"
    )
    
    sku: Optional[str] = Field(
        None,
        max_length=100,
        description="Código SKU único",
        examples=["DELL-XPS-15-001"]
    )
    
    category: Optional[str] = Field(
        None,
        max_length=100,
        description="Categoría del producto",
        examples=["Laptops", "Electrónicos"]
    )
    
    is_active: bool = Field(
        default=True,
        description="Si el producto está activo"
    )
    
    @field_validator('price', 'cost')
    @classmethod
    def validate_prices(cls, v):
        """Validar que los precios sean positivos"""
        if v is not None and v < 0:
            raise ValueError("El precio/costo debe ser mayor o igual a 0")
        return v
    
    @field_validator('stock')
    @classmethod
    def validate_stock(cls, v):
        """Validar que el stock sea no negativo"""
        if v < 0:
            raise ValueError("El stock no puede ser negativo")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Laptop Dell XPS 15",
                "description": "Laptop profesional con Intel i7",
                "price": 1299.99,
                "cost": 800.00,
                "stock": 5,
                "sku": "DELL-XPS-15-001",
                "category": "Laptops",
                "is_active": True
            }
        }


class ProductUpdate(BaseModel):
    """Schema para actualizar un producto (todos los campos opcionales)"""
    
    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255
    )
    
    description: Optional[str] = Field(
        None,
        max_length=1000
    )
    
    price: Optional[Decimal] = Field(
        None,
        gt=0,
        decimal_places=2
    )
    
    cost: Optional[Decimal] = Field(
        None,
        ge=0,
        decimal_places=2
    )
    
    stock: Optional[int] = Field(
        None,
        ge=0
    )
    
    sku: Optional[str] = Field(
        None,
        max_length=100
    )
    
    category: Optional[str] = Field(
        None,
        max_length=100
    )
    
    is_active: Optional[bool] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "price": 1199.99,
                "stock": 10
            }
        }


# ============================================
# SCHEMAS DE SALIDA (Response)
# ============================================

class ProductResponse(BaseModel):
    """Schema de respuesta para un producto"""
    
    id: str = Field(..., description="ID único del producto")
    tenant_id: str = Field(..., description="ID del tenant")
    name: str
    description: Optional[str] = None
    price: Decimal
    cost: Optional[Decimal] = None
    stock: int
    sku: Optional[str] = None
    category: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    # Campos calculados
    profit_margin: Optional[Decimal] = Field(
        None,
        description="Margen de ganancia (%)"
    )
    
    @classmethod
    def from_model(cls, product):
        """Crear desde el modelo de dominio"""
        data = {
            "id": str(product.id),
            "tenant_id": str(product.tenant_id),
            "name": product.name,
            "description": product.description,
            "price": product.price,
            "cost": product.cost,
            "stock": product.stock,
            "sku": product.sku,
            "category": product.category,
            "is_active": product.is_active,
            "created_at": product.created_at,
            "updated_at": product.updated_at,
        }
        
        # Calcular margen de ganancia
        if product.cost and product.cost > 0:
            profit = product.price - product.cost
            data["profit_margin"] = (profit / product.cost) * 100
        
        return cls(**data)
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "tenant_id": "tenant-abc-123",
                "name": "Laptop Dell XPS 15",
                "description": "Laptop profesional",
                "price": 1299.99,
                "cost": 800.00,
                "stock": 5,
                "sku": "DELL-XPS-15-001",
                "category": "Laptops",
                "is_active": True,
                "profit_margin": 62.50,
                "created_at": "2024-01-26T10:00:00",
                "updated_at": "2024-01-26T10:00:00"
            }
        }


class ProductListResponse(BaseModel):
    """Schema de respuesta para lista de productos"""
    
    products: list[ProductResponse]
    total: int = Field(..., description="Total de productos")
    page: int = Field(default=1, description="Página actual")
    page_size: int = Field(default=20, description="Items por página")
    
    class Config:
        json_schema_extra = {
            "example": {
                "products": [
                    {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "name": "Laptop Dell XPS 15",
                        "price": 1299.99,
                        "stock": 5
                    }
                ],
                "total": 1,
                "page": 1,
                "page_size": 20
            }
        }


# ============================================
# SCHEMAS AUXILIARES
# ============================================

class StockUpdateSchema(BaseModel):
    """Schema para actualizar stock"""
    
    quantity: int = Field(
        ...,
        description="Cantidad a agregar (positivo) o quitar (negativo)"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "quantity": 10
            }
        }


class ProductSearchSchema(BaseModel):
    """Schema para búsqueda de productos"""
    
    query: Optional[str] = Field(
        None,
        description="Término de búsqueda"
    )
    
    category: Optional[str] = Field(
        None,
        description="Filtrar por categoría"
    )
    
    min_price: Optional[Decimal] = Field(
        None,
        ge=0,
        description="Precio mínimo"
    )
    
    max_price: Optional[Decimal] = Field(
        None,
        ge=0,
        description="Precio máximo"
    )
    
    in_stock_only: bool = Field(
        default=False,
        description="Solo productos en stock"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "laptop",
                "category": "Electrónicos",
                "min_price": 500.00,
                "max_price": 2000.00,
                "in_stock_only": True
            }
        }