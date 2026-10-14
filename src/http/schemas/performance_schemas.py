from datetime import datetime
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field


class AgentResponseTimeResponse(BaseModel):
    tenant_id: str = Field(..., description="Tenant analizado")
    avg_response_time_seconds: float | None = Field(
        None,
        description="Tiempo promedio de respuesta (s); None si no hay datos o hubo error",
    )
    window_minutes: int = Field(..., ge=1, le=720, description="Ventana analizada en minutos")
    calculated_at: datetime = Field(..., description="Fecha de generación (UTC)")


class AgentUptimeResponse(BaseModel):
    uptime_seconds: int = Field(..., ge=0, description="Segundos desde que el agente está arriba")
    started_at: datetime = Field(..., description="Marca de inicio del proceso")
    started_source: str = Field(..., description="Fuente de inicio: 'env' si APP_START_TIME, 'process' si fallback")
    process_id: int = Field(..., description="PID del worker que responde")
    calculated_at: datetime = Field(..., description="Fecha de generación (UTC)")


class ErrorLogEntry(BaseModel):
    id: Optional[str] = Field(None, description="ID del log")
    message: str = Field(..., description="Mensaje de error")
    level: Optional[str] = Field(None, description="Nivel del log")
    created_at: datetime = Field(..., description="Fecha del evento")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Metadata adicional")


class ErrorLogsResponse(BaseModel):
    tenant_id: str = Field(..., description="Tenant analizado")
    items: List[ErrorLogEntry] = Field(..., description="Lista de errores recientes")
    limit: int = Field(..., ge=1, le=100, description="Límite solicitado")
    calculated_at: datetime = Field(..., description="Fecha de generación (UTC)")
