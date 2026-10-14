"""
Models Package

Exports todos los modelos de dominio para fácil importación.

Uso:
    from src.models import Product, Sale, Conversation
"""

# Importar todos los modelos
from src.models.models import (
    # Enums
    ConversationStatus,
    MessageRole,
    MessageType,
    SaleStatus,
    PaymentStatus,
    TenantPlan,
    DeliveryStatus,
    
    # Models
    Tenant,
    AgentConfig,
    Product,
    Conversation,
    Message,
    Sale,
    SaleItem,
    Webhook,
    WebhookDelivery,
)

# Exports
__all__ = [
    # Enums
    "ConversationStatus",
    "MessageRole",
    "MessageType",
    "SaleStatus",
    "PaymentStatus",
    "TenantPlan",
    "DeliveryStatus",
    
    # Models
    "Tenant",
    "AgentConfig",
    "Product",
    "Conversation",
    "Message",
    "Sale",
    "SaleItem",
    "Webhook",
    "WebhookDelivery",
]
