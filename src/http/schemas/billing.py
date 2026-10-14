from __future__ import annotations

from pydantic import BaseModel, Field


class BillingLimits(BaseModel):
    products: int = Field(..., description="Límite de productos permitidos")
    conversations_month: int = Field(..., description="Límite de conversaciones por mes")


class BillingSummary(BaseModel):
    plan_id: str = Field(..., description="ID del plan actual")
    status: str = Field(..., description="Estado de la suscripción")
    products_count: int = Field(..., description="Número actual de productos")
    conversations_month_count: int = Field(..., description="Número de conversaciones este mes")
    limits: BillingLimits = Field(..., description="Límites del plan actual")


class BillingSummaryResponse(BaseModel):
    data: BillingSummary = Field(..., description="Resumen de facturación y límites") 