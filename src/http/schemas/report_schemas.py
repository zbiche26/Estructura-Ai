from datetime import date, datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class WeeklyBucket(BaseModel):
    bucket_date: date = Field(..., description="Día del bucket")
    total_sales: int = Field(..., ge=0, description="Total de ventas en el día")
    total_revenue: Decimal = Field(..., ge=0, description="Ingresos totales en el día")


class WeeklyReportResponse(BaseModel):
    tenant_id: str = Field(..., description="Tenant del reporte")
    start_date: date = Field(..., description="Fecha de inicio del periodo semanal")
    end_date: date = Field(..., description="Fecha de fin del periodo semanal")
    total_sales: int = Field(..., description="Total de ventas en la semana")
    total_revenue: Decimal = Field(..., description="Ingresos totales en la semana")
    average_sale: Decimal = Field(..., description="Promedio de venta por transacción")
    buckets: List[WeeklyBucket] = Field(..., description="Desglose diario de ventas")
    calculated_at: datetime = Field(..., description="Fecha de generación del reporte")


class MonthlyBucket(BaseModel):
    day: int = Field(..., ge=1, le=31, description="Día del mes")
    total_sales: int = Field(..., ge=0, description="Total de ventas en el día")
    total_revenue: Decimal = Field(..., ge=0, description="Ingresos totales en el día")


class MonthlyReportResponse(BaseModel):
    tenant_id: str = Field(..., description="Tenant del reporte")
    year: int = Field(..., description="Año del reporte")
    month: int = Field(..., description="Mes del reporte")
    total_sales: int = Field(..., description="Total de ventas en el mes")
    total_revenue: Decimal = Field(..., description="Ingresos totales en el mes")
    average_sale: Decimal = Field(..., description="Promedio de venta por transacción")
    unique_customers: int = Field(..., description="Número de clientes únicos")
    best_day: Optional[str] = Field(None, description="Día con más ventas")
    best_day_revenue: Optional[Decimal] = Field(None, description="Ingresos del mejor día")
    buckets: List[MonthlyBucket] = Field(..., description="Desglose diario de ventas")
    calculated_at: datetime = Field(..., description="Fecha de generación del reporte")


class ExportReportResponse(BaseModel):
    tenant_id: str = Field(..., description="Tenant del reporte exportado")
    period: Literal["weekly", "monthly"] = Field(..., description="Periodo del reporte")
    format: Literal["csv", "pdf"] = Field(..., description="Formato del archivo exportado")
    content: str = Field(..., description="Contenido base64 del archivo exportado")
    calculated_at: datetime = Field(..., description="Fecha de generación del reporte")
