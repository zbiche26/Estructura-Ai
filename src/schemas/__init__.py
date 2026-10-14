"""
Schemas de Pydantic para validación de datos

Uso:
    from src.schemas import ProductCreate, SaleCreate, ConversationCreate
"""

# Product Schemas
from src.schemas.product_schemas import (
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    ProductListResponse,
    StockUpdateSchema,
    ProductSearchSchema,
)

# Sale Schemas
from src.schemas.sale_schemas import (
    SaleStatus,
    SaleItemCreate,
    SaleItemResponse,
    SaleCreate,
    SaleUpdate,
    SaleResponse,
    SaleListResponse,
    SaleReportByDate,
    SaleReportByMonth,
    SaleSearchSchema,
)

# Conversation Schemas
from src.schemas.conversation_schemas import (
    ConversationStatus,
    MessageRole,
    MessageCreate,
    MessageResponse,
    ChatHistoryMessage,
    ConversationCreate,
    ConversationUpdate,
    ConversationResponse,
    ConversationWithMessages,
    ConversationListResponse,
    ConversationStats,
    AgentRequest,
    AgentResponse,
    ConversationSearchSchema,
)

__all__ = [
    # Product
    "ProductCreate",
    "ProductUpdate",
    "ProductResponse",
    "ProductListResponse",
    "StockUpdateSchema",
    "ProductSearchSchema",
    
    # Sale
    "SaleStatus",
    "SaleItemCreate",
    "SaleItemResponse",
    "SaleCreate",
    "SaleUpdate",
    "SaleResponse",
    "SaleListResponse",
    "SaleReportByDate",
    "SaleReportByMonth",
    "SaleSearchSchema",
    
    # Conversation
    "ConversationStatus",
    "MessageRole",
    "MessageCreate",
    "MessageResponse",
    "ChatHistoryMessage",
    "ConversationCreate",
    "ConversationUpdate",
    "ConversationResponse",
    "ConversationWithMessages",
    "ConversationListResponse",
    "ConversationStats",
    "AgentRequest",
    "AgentResponse",
    "ConversationSearchSchema",
]