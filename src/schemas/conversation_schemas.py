"""
Schemas de Pydantic para Conversations y Messages

Maneja el flujo de conversaciones del chatbot con clientes
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ============================================
# ENUMS
# ============================================

class ConversationStatus(str, Enum):
    """Estados de una conversación"""
    ACTIVE = "active"
    CLOSED = "closed"
    ARCHIVED = "archived"


class MessageRole(str, Enum):
    """Roles en una conversación"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


# ============================================
# MESSAGE SCHEMAS
# ============================================

class MessageCreate(BaseModel):
    """Schema para crear un mensaje"""
    
    conversation_id: str = Field(
        ...,
        description="ID de la conversación"
    )
    
    role: MessageRole = Field(
        ...,
        description="Rol del mensaje (user, assistant, system)"
    )
    
    content: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Contenido del mensaje"
    )
    
    strategy_used: Optional[str] = Field(
        None,
        description="Estrategia del agente usada (si aplica)"
    )
    
    metadata: Optional[dict] = Field(
        default_factory=dict,
        description="Metadata adicional"
    )
    
    @field_validator('content')
    @classmethod
    def validate_content(cls, v):
        """Validar que el contenido no esté vacío"""
        if not v or not v.strip():
            raise ValueError("El contenido no puede estar vacío")
        return v.strip()
    
    class Config:
        json_schema_extra = {
            "example": {
                "conversation_id": "conv-123",
                "role": "user",
                "content": "Hola, ¿tienen laptops en stock?",
                "strategy_used": None,
                "metadata": {}
            }
        }


class MessageResponse(BaseModel):
    """Schema de respuesta para un mensaje"""
    
    id: str
    conversation_id: str
    role: str
    content: str
    strategy_used: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "msg-123",
                "conversation_id": "conv-456",
                "role": "user",
                "content": "Hola, ¿tienen laptops?",
                "strategy_used": None,
                "created_at": "2024-01-26T10:00:00"
            }
        }


class ChatHistoryMessage(BaseModel):
    """Schema para historial de chat (formato LLM)"""
    
    role: str = Field(..., description="user, assistant, o system")
    content: str = Field(..., description="Contenido del mensaje")
    
    class Config:
        json_schema_extra = {
            "example": {
                "role": "user",
                "content": "Hola, ¿tienen laptops en stock?"
            }
        }


# ============================================
# CONVERSATION SCHEMAS
# ============================================

class ConversationCreate(BaseModel):
    """Schema para crear una conversación"""
    
    phone_number: str = Field(
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
    
    context: Optional[dict] = Field(
        default_factory=dict,
        description="Contexto inicial de la conversación"
    )
    
    @field_validator('phone_number')
    @classmethod
    def validate_phone(cls, v):
        """Validar formato de teléfono"""
        v = v.strip()
        
        if not v.startswith('+') and not v[0].isdigit():
            raise ValueError("Teléfono debe empezar con + o número")
        
        digits = v[1:] if v.startswith('+') else v
        if not digits.isdigit():
            raise ValueError("Teléfono solo puede contener números")
        
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "phone_number": "+573001234567",
                "customer_name": "Juan Pérez",
                "context": {
                    "source": "whatsapp",
                    "campaign": "promo-2024"
                }
            }
        }


class ConversationUpdate(BaseModel):
    """Schema para actualizar una conversación"""
    
    customer_name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255
    )
    
    status: Optional[ConversationStatus] = None
    
    context: Optional[dict] = None
    
    current_strategy: Optional[str] = Field(
        None,
        description="Estrategia actual del agente"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "customer_name": "Juan Pérez García",
                "status": "active",
                "current_strategy": "product_search"
            }
        }


class ConversationResponse(BaseModel):
    """Schema de respuesta para una conversación"""
    
    id: str
    tenant_id: str
    phone_number: str
    customer_name: Optional[str] = None
    status: str
    context: dict = Field(default_factory=dict)
    current_strategy: Optional[str] = None
    
    # Fechas
    created_at: datetime
    closed_at: Optional[datetime] = None
    
    # Estadísticas (opcionales)
    message_count: Optional[int] = Field(
        None,
        description="Total de mensajes"
    )
    
    last_message_at: Optional[datetime] = Field(
        None,
        description="Fecha del último mensaje"
    )
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "conv-123",
                "tenant_id": "tenant-abc",
                "phone_number": "+573001234567",
                "customer_name": "Juan Pérez",
                "status": "active",
                "context": {
                    "last_product_viewed": "laptop-dell-xps",
                    "budget": 2000
                },
                "current_strategy": "product_search",
                "created_at": "2024-01-26T10:00:00",
                "closed_at": None,
                "message_count": 5,
                "last_message_at": "2024-01-26T10:15:00"
            }
        }


class ConversationWithMessages(BaseModel):
    """Schema de conversación con mensajes incluidos"""
    
    conversation: ConversationResponse
    messages: List[MessageResponse]
    
    class Config:
        json_schema_extra = {
            "example": {
                "conversation": {
                    "id": "conv-123",
                    "phone_number": "+573001234567",
                    "status": "active"
                },
                "messages": [
                    {
                        "id": "msg-1",
                        "role": "user",
                        "content": "Hola"
                    },
                    {
                        "id": "msg-2",
                        "role": "assistant",
                        "content": "¡Hola! ¿Cómo puedo ayudarte?"
                    }
                ]
            }
        }


class ConversationListResponse(BaseModel):
    """Schema de respuesta para lista de conversaciones"""
    
    conversations: List[ConversationResponse]
    total: int = Field(..., description="Total de conversaciones")
    page: int = Field(default=1)
    page_size: int = Field(default=20)
    
    class Config:
        json_schema_extra = {
            "example": {
                "conversations": [],
                "total": 0,
                "page": 1,
                "page_size": 20
            }
        }


# ============================================
# SCHEMAS DE ESTADÍSTICAS
# ============================================

class ConversationStats(BaseModel):
    """Schema para estadísticas de conversación"""
    
    conversation_id: str
    total_messages: int = Field(..., description="Total de mensajes")
    user_messages: int = Field(..., description="Mensajes del usuario")
    assistant_messages: int = Field(..., description="Mensajes del asistente")
    system_messages: int = Field(..., description="Mensajes del sistema")
    
    # Duración
    duration_minutes: Optional[int] = Field(
        None,
        description="Duración en minutos"
    )
    
    # Estrategias usadas
    strategies_used: List[str] = Field(
        default_factory=list,
        description="Estrategias del agente usadas"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "conversation_id": "conv-123",
                "total_messages": 10,
                "user_messages": 5,
                "assistant_messages": 4,
                "system_messages": 1,
                "duration_minutes": 15,
                "strategies_used": [
                    "welcome",
                    "product_search",
                    "closing"
                ]
            }
        }


# ============================================
# SCHEMAS PARA AGENTE IA
# ============================================

class AgentRequest(BaseModel):
    """Schema para request al agente IA"""
    
    conversation_id: str = Field(
        ...,
        description="ID de la conversación"
    )
    
    user_message: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Mensaje del usuario"
    )
    
    force_strategy: Optional[str] = Field(
        None,
        description="Forzar una estrategia específica (opcional)"
    )
    
    include_history: bool = Field(
        default=True,
        description="Incluir historial de conversación"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "conversation_id": "conv-123",
                "user_message": "¿Tienen laptops Dell en stock?",
                "force_strategy": None,
                "include_history": True
            }
        }


class AgentResponse(BaseModel):
    """Schema de respuesta del agente IA"""
    
    message_id: str = Field(..., description="ID del mensaje guardado")
    
    response: str = Field(
        ...,
        description="Respuesta generada por el agente"
    )
    
    strategy_used: str = Field(
        ...,
        description="Estrategia utilizada"
    )
    
    confidence: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Confianza en la respuesta (0-1)"
    )
    
    suggested_actions: Optional[List[str]] = Field(
        default_factory=list,
        description="Acciones sugeridas para el vendedor"
    )
    
    products_mentioned: Optional[List[str]] = Field(
        default_factory=list,
        description="IDs de productos mencionados"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "message_id": "msg-456",
                "response": "¡Claro! Tenemos 3 modelos de laptops Dell en stock...",
                "strategy_used": "product_search",
                "confidence": 0.95,
                "suggested_actions": [
                    "Mostrar catálogo de laptops",
                    "Enviar precios"
                ],
                "products_mentioned": [
                    "prod-123",
                    "prod-456"
                ]
            }
        }


# ============================================
# SCHEMAS AUXILIARES
# ============================================

class ConversationSearchSchema(BaseModel):
    """Schema para búsqueda de conversaciones"""
    
    phone_number: Optional[str] = None
    status: Optional[ConversationStatus] = None
    customer_name: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    has_messages: Optional[bool] = Field(
        None,
        description="Filtrar conversaciones con/sin mensajes"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "phone_number": "+573001234567",
                "status": "active",
                "date_from": "2024-01-01T00:00:00",
                "date_to": "2024-01-31T23:59:59",
                "has_messages": True
            }
        }