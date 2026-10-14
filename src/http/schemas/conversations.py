from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class ConversationListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="ID único de la conversación")
    phone: str = Field(..., description="Número de teléfono del contacto")
    contact_name: str = Field(..., description="Nombre del contacto")
    contact_type: str = Field(..., description="Tipo de contacto (cliente, lead, etc.)")
    status: str = Field(..., description="Estado de la conversación")
    bot_active: bool = Field(..., description="Si el bot está activo en esta conversación")
    last_message: str = Field(..., description="Último mensaje de la conversación")
    last_message_at: datetime = Field(..., description="Fecha del último mensaje")
    unread_count: int = Field(..., ge=0, description="Número de mensajes no leídos")

    @field_serializer("last_message_at")
    def serialize_last_message_at(self, value: datetime) -> str:
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class ConversationsListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: list[ConversationListItem] = Field(..., description="Lista de conversaciones")
    total: int = Field(..., ge=0, description="Total de conversaciones disponibles")
    page: int = Field(..., ge=1, description="Página actual")
    page_size: int = Field(..., ge=1, le=100, description="Tamaño de página")


class ConversationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bot_active: bool | None = Field(None, description="Activar/desactivar el bot en la conversación")
    contact_type: str | None = Field(None, description="Tipo de contacto")
    contact_name: str | None = Field(None, description="Nombre del contacto")
