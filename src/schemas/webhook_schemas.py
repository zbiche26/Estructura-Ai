from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, Field

from src.models import DeliveryStatus


class WebhookBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    url: AnyHttpUrl
    description: Optional[str] = Field(default=None, max_length=500)
    secret: Optional[str] = Field(default=None, max_length=255)
    headers: Dict[str, str] = Field(default_factory=dict)
    events: List[str] = Field(default_factory=list)
    is_active: bool = True


class WebhookCreateRequest(WebhookBase):
    pass


class WebhookUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    url: Optional[AnyHttpUrl] = None
    description: Optional[str] = Field(default=None, max_length=500)
    secret: Optional[str] = Field(default=None, max_length=255)
    headers: Optional[Dict[str, str]] = None
    events: Optional[List[str]] = None
    is_active: Optional[bool] = None


class WebhookResponse(WebhookBase):
    id: UUID
    tenant_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WebhookListResponse(BaseModel):
    items: List[WebhookResponse]
    total: int


class WebhookDeliveryResponse(BaseModel):
    id: UUID
    webhook_id: UUID
    tenant_id: UUID
    delivery_status: DeliveryStatus
    response_status_code: Optional[int] = None
    response_body: Optional[str] = None
    error_message: Optional[str] = None
    request_payload: Dict[str, Any] = Field(default_factory=dict)
    attempt: int = 1
    created_at: datetime

    class Config:
        from_attributes = True


class WebhookTestRequest(BaseModel):
    payload: Dict[str, Any] = Field(default_factory=lambda: {"test": True})
    headers: Dict[str, str] = Field(default_factory=dict)
