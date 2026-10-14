from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import List
from pydantic import BaseModel, ConfigDict, Field, field_serializer


class MessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(
        ..., min_length=1, description="Contenido del mensaje a enviar"
    )


class MessageSender(str, Enum):
    BOT = "bot"
    AGENT = "agent"
    CONTACT = "contact"
    IMPORTED = "imported"


class MessageStatus(str, Enum):
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"


class ConversationMessageItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., description="ID único del mensaje")
    content: str = Field(..., description="Contenido del mensaje")
    sender: MessageSender = Field(..., description="Quién envió el mensaje")
    status: MessageStatus = Field(..., description="Estado de entrega del mensaje")
    sent_at: datetime = Field(..., description="Fecha de envío del mensaje")

    @field_serializer("sent_at")
    def serialize_sent_at(self, value: datetime) -> str:
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class ConversationMessagesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data: list[ConversationMessageItem] = Field(
        ..., description="Lista de mensajes de la conversación"
    )
    has_more: bool
    oldest_cursor: str | None


class ReactivateConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template_name: str = Field(
        ..., min_length=1, description="Nombre de la plantilla aprobada en Meta"
    )
    language: str = Field(default="es", description="Código de idioma de la plantilla")
    params: List[str] = Field(
        default=[], description="Parámetros de texto para el body de la plantilla"
    )


class ReactivateConversationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversation_id: str
    template_name: str
    status: str = "sent"
    message: str = "Plantilla enviada exitosamente"
