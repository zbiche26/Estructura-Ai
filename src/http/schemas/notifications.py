from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, UUID4

NotificationType = Literal["billing", "onboarding", "limit", "performance", "message"]


class NotificationItem(BaseModel):
    id: UUID4 = Field(..., description="Identificador único de la notificación")
    type: NotificationType = Field(..., description="Tipo de notificación (billing, onboarding, limit, performance)")
    title: str = Field(..., description="Título de la notificación")
    body: str = Field(..., description="Contenido completo de la notificación")
    read_at: Optional[datetime] = Field(None, description="Fecha de lectura (null si no leída)")
    created_at: datetime = Field(..., description="Fecha de creación de la notificación")


class NotificationsResponse(BaseModel):
    data: List[NotificationItem]
    total: int = Field(..., description="Total de notificaciones del tenant")
    unread: int = Field(..., description="Notificaciones no leídas")
