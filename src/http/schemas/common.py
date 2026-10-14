from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional, List, Dict, Any

from pydantic import BaseModel, Field, EmailStr


# ======================
# Envelope estándar
# ======================


class Meta(BaseModel):
    request_id: str = Field(default="req_stub", description="ID único de la petición")
    timestamp: datetime = Field(default_factory=lambda: datetime.utcnow(), description="Timestamp de la respuesta")


class ApiError(BaseModel):
    code: str = Field(..., description="Código de error")
    message: str = Field(..., description="Mensaje de error legible")
    details: Dict[str, Any] = Field(default_factory=dict, description="Detalles adicionales del error")


class ErrorResponse(BaseModel):
    error: ApiError = Field(..., description="Información del error")
    meta: Meta = Field(..., description="Metadatos de la respuesta")


# ======================
# Compat layer para deps.py (NO romper stubs existentes)
# ======================


class UserInfo(BaseModel):
    id: str = Field(..., description="ID único del usuario")
    email: EmailStr = Field(..., description="Email del usuario")
    name: Optional[str] = Field(None, description="Nombre del usuario")


class TenantInfo(BaseModel):
    id: str = Field(..., description="ID único del tenant")
    name: str = Field(..., description="Nombre del tenant")


# ======================
# /me contract (API pública)
# ======================

FeatureKey = Literal[
    "onboarding",
    "billing",
    "training",
    "conversations",
    "whatsapp",
    "inventory",
    "analytics",
    "excel_import",
    "webhooks",
    "reports",
    "performance",
]


class MeUser(BaseModel):
    id: str
    email: EmailStr
    full_name: Optional[str] = None


class MeTenant(BaseModel):
    id: str
    name: str


class MePlan(BaseModel):
    id: Literal["starter", "growth", "enterprise", "free"]
    status: Literal["active", "trialing", "past_due", "canceled"] = "active"
    trial_ends_at: Optional[datetime] = None


class UsageLimits(BaseModel):
    products: int = 0
    conversations_month: int = 0


class MeUsage(BaseModel):
    products_count: int = 0
    conversations_month_count: int = 0
    limits: UsageLimits


class MeData(BaseModel):
    user: MeUser
    tenant: MeTenant
    plan: MePlan
    features: List[FeatureKey] = Field(default_factory=list)
    usage: MeUsage


class MeResponse(BaseModel):
    data: MeData
    meta: Meta


# ======================
# Auth stubs
# ======================


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


# ======================
# Health
# ======================


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class TenantInfo(BaseModel):
    id: str
    name: str
    slug: Optional[str] = None
