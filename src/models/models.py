"""
Modelos de Dominio - Entidades de Negocio

Estos modelos representan los objetos de negocio principales.
Usan Pydantic para validación automática.

Jerarquía:
- BaseModel: Modelo base con campos comunes
- Tenant: Cliente/Empresa
- Product: Producto del catálogo
- Conversation: Conversación de WhatsApp
- Message: Mensaje individual
- Sale: Venta
- SaleItem: Item de una venta
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from decimal import Decimal
from uuid import UUID, uuid4
from enum import Enum

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, EmailStr, Field, field_validator

# ============================================
# ENUMS - Estados y Tipos
# ============================================


class ConversationStatus(str, Enum):
    """Estados posibles de una conversación"""

    ACTIVE = "active"
    CLOSED = "closed"
    ARCHIVED = "archived"


class MessageRole(str, Enum):
    """Roles de los mensajes"""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class MessageType(str, Enum):
    """Tipos de mensaje de WhatsApp"""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    DOCUMENT = "document"
    VIDEO = "video"


class SaleStatus(str, Enum):
    """Estados de una venta"""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class PaymentStatus(str, Enum):
    """Estados de pago"""

    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"


class TenantPlan(str, Enum):
    """Planes disponibles"""

    STARTER = "starter"
    GROWTH = "growth"
    ENTERPRISE = "enterprise"


class DeliveryStatus(str, Enum):
    """Estado de una entrega de webhook"""

    SUCCESS = "success"
    FAILED = "failed"


# ============================================
# BASE MODELS
# ============================================


class BaseDBModel(BaseModel):
    """
    Modelo base para todas las entidades de BD

    Incluye campos comunes: id, created_at, updated_at
    """

    model_config = ConfigDict(
        from_attributes=True, populate_by_name=True, use_enum_values=True
    )

    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TenantBoundModel(BaseDBModel):
    """
    Modelo base para entidades que pertenecen a un tenant

    Todas las entidades Multi-Tenant heredan de aquí
    """

    tenant_id: UUID


class AgentConfig(TenantBoundModel):
    """Configuración del agente IA asociada a un tenant."""

    nombre_agente: Optional[str] = Field(default=None, max_length=255)
    system_prompt: Optional[str] = Field(default=None)
    welcome_message: Optional[str] = Field(default=None)
    temperatura: float = Field(default=0.7, ge=0.0, le=1.0)
    idioma: str = Field(default="es", min_length=2, max_length=50)
    owner_phone: Optional[str] = Field(default=None)


# ============================================
# TENANT (Cliente/Empresa)
# ============================================


class Tenant(BaseDBModel):
    """
    Representa un cliente/empresa en el sistema Multi-Tenant

    Cada tenant tiene su propia instancia aislada de la aplicación
    """

    name: str = Field(min_length=1, max_length=255)
    email: EmailStr = Field(..., description="Email único del administrador del tenant")
    password_hash: str = Field(
        ...,
        description="Hash bcrypt de la contraseña (nunca se devuelve en respuestas)",
    )
    slug: str = Field(min_length=1, max_length=100)
    config: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True

    plan: TenantPlan = TenantPlan.STARTER
    max_products: int = 100
    max_conversations: int = 1000

    website_url: Optional[str] = None

    # Campos de WhatsApp para la integracion aislada por tenant
    whatsapp_phone_number: Optional[str] = Field(default=None, max_length=20)
    whatsapp_phone_id: Optional[str] = Field(default=None, max_length=255)
    whatsapp_token_encrypted: Optional[str] = None
    whatsapp_webhook_secret: Optional[str] = Field(default=None, max_length=255)
    whatsapp_enabled: bool = False

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        """Slug debe ser lowercase y solo contener a-z, 0-9, y guiones"""
        import re

        if not re.match(r"^[a-z0-9-]+$", v):
            raise ValueError(
                "Slug debe contener solo letras minúsculas, números y guiones"
            )
        return v

    def __repr__(self) -> str:
        return f"<Tenant {self.slug} ({self.plan})>"


# ============================================
# PRODUCT (Producto)
# ============================================


class Product(TenantBoundModel):
    """
    Representa un producto en el catálogo

    Incluye información de pricing, inventario y metadata
    """

    name: str = Field(min_length=1, max_length=500)
    description: Optional[str] = None
    sku: Optional[str] = Field(None, max_length=100)

    price: Decimal = Field(ge=0)
    cost: Optional[Decimal] = Field(None, ge=0)
    currency: str = Field(default="USD", max_length=3)

    stock: int = Field(default=0, ge=0)
    min_stock: int = Field(default=0, ge=0)
    max_stock: Optional[int] = Field(None, ge=0)

    category: Optional[str] = Field(None, max_length=100)
    tags: Optional[List[str]] = Field(default=None)  # ← CAMBIADO: Ahora es Optional

    metadata: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True

    embedding: Optional[List[float]] = None

    # ← AGREGADO: Validator para tags
    @field_validator("tags", mode="before")
    @classmethod
    def validate_tags(cls, v):
        """Convierte None a lista vacía"""
        return v if v is not None else []

    @property
    def is_in_stock(self) -> bool:
        """Verifica si el producto tiene stock disponible"""
        return self.stock > 0

    @property
    def is_low_stock(self) -> bool:
        """Verifica si el stock está bajo"""
        return self.stock <= self.min_stock

    @property
    def profit_margin(self) -> Optional[Decimal]:
        """Calcula el margen de ganancia"""
        if self.cost and self.cost > 0:
            return ((self.price - self.cost) / self.price) * 100
        return None

    def __repr__(self) -> str:
        return f"<Product {self.name} (${self.price})>"


# ============================================
# CONVERSATION (Conversación WhatsApp)
# ============================================


class Conversation(TenantBoundModel):
    """
    Representa una conversación de WhatsApp con un cliente

    Mantiene el estado y contexto de la conversación
    """

    phone_number: str = Field(min_length=10, max_length=20)
    customer_name: Optional[str] = Field(None, max_length=255)

    status: ConversationStatus = ConversationStatus.ACTIVE

    current_strategy: Optional[str] = Field(None, max_length=100)
    context: Dict[str, Any] = Field(default_factory=dict)

    metadata: Dict[str, Any] = Field(default_factory=dict)

    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_message_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    closed_at: Optional[datetime] = None

    @property
    def is_active(self) -> bool:
        """Verifica si la conversación está activa"""
        return self.status == ConversationStatus.ACTIVE

    @property
    def duration_minutes(self) -> Optional[int]:
        """Duración de la conversación en minutos"""
        if self.closed_at:
            delta = self.closed_at - self.started_at
            return int(delta.total_seconds() / 60)
        return None

    def __repr__(self) -> str:
        return f"<Conversation {self.phone_number} ({self.status})>"


# ============================================
# MESSAGE (Mensaje)
# ============================================


class Message(TenantBoundModel):
    """
    Representa un mensaje individual en una conversación

    Puede ser del usuario, del asistente, o del sistema
    """

    conversation_id: UUID

    role: MessageRole
    content: str = Field(min_length=1)

    whatsapp_message_id: Optional[str] = Field(None, max_length=255)
    message_type: MessageType = MessageType.TEXT

    strategy_used: Optional[str] = Field(None, max_length=100)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def is_from_user(self) -> bool:
        """Verifica si el mensaje es del usuario"""
        return self.role == MessageRole.USER

    @property
    def is_from_assistant(self) -> bool:
        """Verifica si el mensaje es del asistente"""
        return self.role == MessageRole.ASSISTANT

    def __repr__(self) -> str:
        preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"<Message {self.role}: {preview}>"


# ============================================
# SALE (Venta)
# ============================================


class Sale(TenantBoundModel):
    """
    Representa una venta completa

    Incluye totales, estado de pago, y relación con conversación
    """

    conversation_id: Optional[UUID] = None

    customer_phone: str = Field(min_length=10, max_length=20)
    customer_name: Optional[str] = Field(None, max_length=255)

    status: SaleStatus = SaleStatus.PENDING

    subtotal: Decimal = Field(default=Decimal("0.00"), ge=0)
    tax: Decimal = Field(default=Decimal("0.00"), ge=0)
    discount: Decimal = Field(default=Decimal("0.00"), ge=0)
    total: Decimal = Field(default=Decimal("0.00"), ge=0)
    currency: str = Field(default="USD", max_length=3)

    payment_method: Optional[str] = Field(None, max_length=50)
    payment_status: PaymentStatus = PaymentStatus.PENDING

    notes: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    confirmed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    items: List["SaleItem"] = Field(default_factory=list)

    @property
    def is_paid(self) -> bool:
        """Verifica si la venta está pagada"""
        return self.payment_status == PaymentStatus.PAID

    @property
    def is_completed(self) -> bool:
        """Verifica si la venta está completada"""
        return self.status == SaleStatus.COMPLETED

    def calculate_total(self):
        """Calcula el total basado en subtotal, tax y discount"""
        self.total = self.subtotal + self.tax - self.discount

    def __repr__(self) -> str:
        return f"<Sale {self.id} (${self.total} - {self.status})>"


# ============================================
# SALE ITEM (Item de Venta)
# ============================================


class SaleItem(TenantBoundModel):
    """
    Representa un item individual en una venta

    Guarda un snapshot del producto en el momento de la venta
    """

    sale_id: UUID
    product_id: UUID

    product_name: str = Field(min_length=1, max_length=500)
    product_sku: Optional[str] = Field(None, max_length=100)

    quantity: int = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    subtotal: Decimal = Field(ge=0)
    discount: Decimal = Field(default=Decimal("0.00"), ge=0)
    total: Decimal = Field(ge=0)

    metadata: Dict[str, Any] = Field(default_factory=dict)

    def calculate_totals(self):
        """Calcula subtotal y total"""
        self.subtotal = self.unit_price * self.quantity
        self.total = self.subtotal - self.discount

    def __repr__(self) -> str:
        return f"<SaleItem {self.product_name} x{self.quantity}>"


# ============================================
# WEBHOOKS (Configuración y Entregas)
# ============================================


class Webhook(TenantBoundModel):
    """Configuración de webhook por tenant."""

    name: str = Field(min_length=1, max_length=150)
    url: AnyHttpUrl
    description: str | None = Field(default=None, max_length=500)
    secret: str | None = Field(default=None, max_length=255)
    headers: dict[str, str] = Field(default_factory=dict)
    events: list[str] = Field(default_factory=list)
    is_active: bool = True


class WebhookDelivery(TenantBoundModel):
    """Registro de entregas de webhooks para auditoría."""

    webhook_id: UUID
    delivery_status: DeliveryStatus
    response_status_code: int | None = None
    response_body: str | None = None
    error_message: str | None = None
    request_payload: Dict[str, Any] = Field(default_factory=dict)
    attempt: int = 1


# ============================================
# UPDATE FORWARD REFS
# ============================================
Sale.model_rebuild()
