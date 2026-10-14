from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class AnalyticsOverviewResponse(BaseModel):
    tenant_id: str = Field(..., description="Tenant analizado")
    total_conversations: int = Field(..., ge=0, description="Total de conversaciones registradas")
    active_users: int = Field(..., ge=0, description="Usuarios únicos con conversaciones activas")
    avg_response_time_seconds: float = Field(default=0.0, ge=0, description="Tiempo promedio de respuesta en segundos. 0.0 cuando no hay datos.")
    conversations_per_day: Dict[str, int] = Field(
        ...,
        description="Mapa fecha → conversaciones creadas",
    )
    window_days: int = Field(
        ...,
        description="Ventana de análisis (días). Valores válidos: 1, 7, 30.",
    )
    calculated_at: datetime = Field(..., description="Fecha de generación del reporte (UTC)")


class TimeBucket(BaseModel):
    bucket: str = Field(..., description="Etiqueta del periodo (YYYY-MM-DD, YYYY-Www o YYYY-MM)")
    total: int = Field(..., ge=0, description="Total de conversaciones en el periodo")


class AnalyticsSeriesResponse(BaseModel):
    tenant_id: str = Field(..., description="Tenant analizado")
    buckets: List[TimeBucket] = Field(..., description="Lista de buckets con conteo por periodo")
    window_days: int = Field(..., description="Ventana de análisis en días")
    calculated_at: datetime = Field(..., description="Fecha de generación del reporte (UTC)")


class DayBucket(BaseModel):
    date: str = Field(..., description="Fecha en formato YYYY-MM-DD")
    count: int = Field(..., ge=0, description="Total de conversaciones del día")


class ConversationsByDayResponse(BaseModel):
    data: List[DayBucket] = Field(..., description="Conversaciones agrupadas por día")


class HandoffRateResponse(BaseModel):
    rate: float = Field(..., ge=0.0, le=1.0, description="Tasa de transferencias a humano (decimal 0–1, ej: 0.12 = 12%)")
    transferred: int = Field(..., ge=0, description="Cantidad de conversaciones transferidas")
    total: int = Field(..., ge=0, description="Total de conversaciones analizadas")


class IntentBucket(BaseModel):
    name: str = Field(..., description="Nombre del intent")
    total: int = Field(..., ge=0, description="Total de ocurrencias del intent en la ventana")


class IntentDistributionResponse(BaseModel):
    data: List[IntentBucket] = Field(..., description="Distribución de intents ordenada por frecuencia descendente")


class ProductConsultedStat(BaseModel):
    product_id: str | None = Field(None, description="ID del producto")
    product_name: str | None = Field(None, description="Nombre del producto")
    product_sku: str | None = Field(None, description="SKU del producto")
    views: int = Field(..., ge=0, description="Total de vistas/consultas")


class TopProductsConsultedResponse(BaseModel):
    tenant_id: str = Field(..., description="Tenant analizado")
    items: List[ProductConsultedStat] = Field(..., description="Productos más consultados")
    window_days: int = Field(..., description="Ventana de análisis en días")
    limit: int = Field(..., ge=1, le=50, description="Límite de resultados devueltos")
    calculated_at: datetime = Field(..., description="Fecha de generación del reporte (UTC)")


class ProductSoldStat(BaseModel):
    product_id: str | None = Field(None, description="ID del producto")
    product_name: str | None = Field(None, description="Nombre del producto")
    product_sku: str | None = Field(None, description="SKU del producto")
    total_quantity: int = Field(..., ge=0, description="Total de unidades vendidas")


class TopProductsSoldResponse(BaseModel):
    tenant_id: str = Field(..., description="Tenant analizado")
    items: List[ProductSoldStat] = Field(..., description="Productos más vendidos")
    window_days: int = Field(..., description="Ventana de análisis en días")
    limit: int = Field(..., ge=1, le=50, description="Límite de resultados devueltos")
    calculated_at: datetime = Field(..., description="Fecha de generación del reporte (UTC)")


class HourlyBucket(BaseModel):
    hour: int = Field(..., ge=0, le=23, description="Hora del día en formato 24h (0-23)")
    label: str = Field(..., description="Etiqueta legible de la hora, ej. '09:00'")
    total: int = Field(..., ge=0, description="Total de conversaciones iniciadas en esa hora")


class HourlyActivityResponse(BaseModel):
    tenant_id: str = Field(..., description="Tenant analizado")
    buckets: List[HourlyBucket] = Field(
        ...,
        description="Actividad por hora del día — siempre 24 elementos (hora 0 a 23)",
    )
    window_days: int = Field(..., description="Ventana de análisis en días")
    calculated_at: datetime = Field(..., description="Fecha de generación del reporte (UTC)")

