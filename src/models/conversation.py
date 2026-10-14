"""
Modelos de dominio para el sistema de conversación AI

Estos modelos representan conversaciones, mensajes y contexto
para el agente de IA.
"""
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from enum import Enum
from dataclasses import dataclass, field
from pydantic import BaseModel, Field


# ==================== ENUMS ====================

class MessageRole(str, Enum):
    """Roles de mensajes en la conversación"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION = "function"


class ConversationStatus(str, Enum):
    """Estados de una conversación"""
    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"
    ARCHIVED = "archived"


class IntentType(str, Enum):
    """Tipos de intención del usuario"""
    GREETING = "greeting"
    INQUIRY = "inquiry"
    PURCHASE = "purchase"
    COMPLAINT = "complaint"
    SUPPORT = "support"
    FAREWELL = "farewell"
    UNKNOWN = "unknown"


# ==================== VALUE OBJECTS ====================

@dataclass(frozen=True)
class ConversationMetadata:
    """Metadata de conversación (inmutable)"""
    platform: str  # whatsapp, telegram, web, etc.
    user_phone: Optional[str] = None
    user_name: Optional[str] = None
    tags: tuple = field(default_factory=tuple)
    
    def __post_init__(self):
        # Convertir lista a tupla si es necesario
        if isinstance(self.tags, list):
            object.__setattr__(self, 'tags', tuple(self.tags))


# ==================== PYDANTIC MODELS ====================

class MessageCreate(BaseModel):
    """Schema para crear un mensaje"""
    role: MessageRole
    content: str
    metadata: Optional[Dict[str, Any]] = None


class MessageResponse(BaseModel):
    """Schema para respuesta de mensaje"""
    id: str
    conversation_id: str
    role: MessageRole
    content: str
    tokens_used: Optional[int] = None
    created_at: datetime
    metadata: Optional[Dict[str, Any]] = None


class ConversationCreate(BaseModel):
    """Schema para crear una conversación"""
    tenant_id: str
    platform: str
    user_phone: Optional[str] = None
    user_name: Optional[str] = None
    initial_message: Optional[str] = None


class ConversationResponse(BaseModel):
    """Schema para respuesta de conversación"""
    id: str
    tenant_id: str
    status: ConversationStatus
    platform: str
    user_phone: Optional[str] = None
    user_name: Optional[str] = None
    message_count: int
    created_at: datetime
    updated_at: datetime
    metadata: Optional[Dict[str, Any]] = None


# ==================== DOMAIN MODELS ====================

class Message:
    """
    Modelo de dominio para un mensaje en la conversación
    
    Representa un mensaje individual con su rol, contenido y metadata.
    """
    
    def __init__(
        self,
        role: MessageRole,
        content: str,
        conversation_id: Optional[str] = None,
        message_id: Optional[str] = None,
        tokens_used: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        created_at: Optional[datetime] = None
    ):
        self.id = message_id
        self.conversation_id = conversation_id
        self.role = role
        self.content = content
        self.tokens_used = tokens_used
        self.metadata = metadata or {}
        self.created_at = created_at or datetime.now(timezone.utc)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario"""
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "role": self.role.value,
            "content": self.content,
            "tokens_used": self.tokens_used,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat()
        }
    
    def to_llm_format(self) -> Dict[str, str]:
        """
        Convierte a formato compatible con LLMs
        
        Returns:
            Dict con 'role' y 'content' para OpenAI/Anthropic
        """
        return {
            "role": self.role.value,
            "content": self.content
        }
    
    def __repr__(self) -> str:
        return f"Message(role={self.role.value}, content={self.content[:50]}...)"


class Conversation:
    """
    Modelo de dominio para una conversación completa
    
    Gestiona el historial de mensajes, contexto y estado de
    una conversación con un usuario.
    """
    
    def __init__(
        self,
        tenant_id: str,
        conversation_id: Optional[str] = None,
        status: ConversationStatus = ConversationStatus.ACTIVE,
        metadata: Optional[ConversationMetadata] = None,
        messages: Optional[List[Message]] = None,
        context: Optional[Dict[str, Any]] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None
    ):
        self.id = conversation_id
        self.tenant_id = tenant_id
        self.status = status
        self.metadata = metadata or ConversationMetadata(platform="unknown")
        self.messages = messages or []
        self.context = context or {}
        self.created_at = created_at or datetime.now(timezone.utc)
        self.updated_at = updated_at or datetime.now(timezone.utc)
        
        # Stats
        self.total_tokens = 0
    
    def add_message(self, message: Message) -> None:
        """
        Agrega un mensaje a la conversación
        
        Args:
            message: Mensaje a agregar
        """
        message.conversation_id = self.id
        self.messages.append(message)
        self.updated_at = datetime.now(timezone.utc)
        
        if message.tokens_used:
            self.total_tokens += message.tokens_used
    
    def get_history(
        self,
        limit: Optional[int] = None,
        include_system: bool = True
    ) -> List[Message]:
        """
        Obtiene el historial de mensajes
        
        Args:
            limit: Número máximo de mensajes (más recientes)
            include_system: Si incluir mensajes del sistema
            
        Returns:
            Lista de mensajes
        """
        messages = self.messages
        
        if not include_system:
            messages = [m for m in messages if m.role != MessageRole.SYSTEM]
        
        if limit:
            messages = messages[-limit:]
        
        return messages
    
    def get_llm_history(
        self,
        limit: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """
        Obtiene historial en formato para LLM
        
        Args:
            limit: Número máximo de mensajes
            
        Returns:
            Lista de mensajes en formato LLM
        """
        messages = self.get_history(limit=limit, include_system=True)
        return [m.to_llm_format() for m in messages]
    
    def get_last_user_message(self) -> Optional[Message]:
        """Obtiene el último mensaje del usuario"""
        for message in reversed(self.messages):
            if message.role == MessageRole.USER:
                return message
        return None
    
    def update_context(self, key: str, value: Any) -> None:
        """
        Actualiza el contexto de la conversación
        
        Args:
            key: Clave del contexto
            value: Valor a guardar
        """
        self.context[key] = value
        self.updated_at = datetime.now(timezone.utc)
    
    def get_context(self, key: str, default: Any = None) -> Any:
        """
        Obtiene un valor del contexto
        
        Args:
            key: Clave a buscar
            default: Valor por defecto
            
        Returns:
            Valor del contexto o default
        """
        return self.context.get(key, default)
    
    def close(self) -> None:
        """Cierra la conversación"""
        self.status = ConversationStatus.CLOSED
        self.updated_at = datetime.now(timezone.utc)
    
    def archive(self) -> None:
        """Archiva la conversación"""
        self.status = ConversationStatus.ARCHIVED
        self.updated_at = datetime.now(timezone.utc)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario"""
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "status": self.status.value,
            "metadata": {
                "platform": self.metadata.platform,
                "user_phone": self.metadata.user_phone,
                "user_name": self.metadata.user_name,
                "tags": list(self.metadata.tags)
            },
            "messages": [m.to_dict() for m in self.messages],
            "context": self.context,
            "total_tokens": self.total_tokens,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
    
    def __repr__(self) -> str:
        return (
            f"Conversation(id={self.id}, tenant={self.tenant_id}, "
            f"messages={len(self.messages)}, status={self.status.value})"
        )


# ==================== HELPER FUNCTIONS ====================

def create_system_message(content: str) -> Message:
    """Helper para crear mensaje del sistema"""
    return Message(
        role=MessageRole.SYSTEM,
        content=content
    )


def create_user_message(content: str) -> Message:
    """Helper para crear mensaje del usuario"""
    return Message(
        role=MessageRole.USER,
        content=content
    )


def create_assistant_message(
    content: str,
    tokens_used: Optional[int] = None
) -> Message:
    """Helper para crear mensaje del asistente"""
    return Message(
        role=MessageRole.ASSISTANT,
        content=content,
        tokens_used=tokens_used
    )