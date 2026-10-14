from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, HTTPException

from src.http.schemas.performance_schemas import (
    AgentResponseTimeResponse,
    AgentUptimeResponse,
    ErrorLogsResponse,
)
from src.services.performance_service import (
    get_agent_response_time,
    get_agent_uptime,
    get_error_logs,
    PERFORMANCE_WINDOW_MINUTES,
)
from src.http.deps import CurrentUser, get_current_user, get_tenant_id
from src.core.database import get_db
from src.core.logger import logger



def current_user_dep(
    tenant_id: str = Depends(get_tenant_id),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> CurrentUser:
    """Resuelve al usuario actual asegurando que exista un tenant válido."""
    return get_current_user(tenant_id=tenant_id, authorization=authorization)


router = APIRouter(prefix="/performance", tags=["Performance"])


@router.get(
    "/response-time",
    response_model=AgentResponseTimeResponse,
    summary="Tiempo de respuesta del agente",
    response_description="Promedio de tiempo de respuesta en segundos (null si no hay datos)",
    responses={
        200: {
            "description": "Respuesta exitosa",
            "content": {
                "application/json": {
                    "example": {
                        "tenant_id": "demo-tenant",
                        "avg_response_time_seconds": 2.5,
                        "window_minutes": 60,
                        "calculated_at": "2026-03-12T21:22:15.448782Z"
                    }
                }
            }
        },
        401: {"description": "No autorizado"},
        500: {"description": "Error interno"},
    },
)
def agent_response_time(
    window_minutes: int = Query(
        PERFORMANCE_WINDOW_MINUTES,
        ge=1,
        le=720,
        description="Ventana en minutos para promediar respuesta",
    ),
    current_user: CurrentUser = Depends(current_user_dep),
    db=Depends(get_db),
):
    try:
        return get_agent_response_time(
            tenant_id=current_user.tenant.id,
            window_minutes=window_minutes,
            db=db,
        )
    except Exception as exc:
        logger.error(f"/performance/response-time failed: {exc}")
        raise HTTPException(status_code=500, detail="Error interno de performance") from exc


@router.get(
    "/uptime",
    response_model=AgentUptimeResponse,
    summary="Uptime del agente",
    response_description="Uptime del agente y fuente de inicio",
    responses={
        200: {"description": "Respuesta exitosa"},
        401: {"description": "No autorizado"},
        500: {"description": "Error interno"},
    },
)
def agent_uptime(
    current_user: CurrentUser = Depends(current_user_dep),
):
    try:
        return get_agent_uptime()
    except Exception as exc:
        logger.error(f"/performance/uptime failed: {exc}")
        raise HTTPException(status_code=500, detail="Error interno de uptime") from exc


@router.get(
    "/error-logs",
    response_model=ErrorLogsResponse,
    summary="Logs de errores recientes",
    response_description="Lista de logs de error recientes",
    responses={
        200: {"description": "Respuesta exitosa"},
        401: {"description": "No autorizado"},
        500: {"description": "Error interno"},
    },
)
def error_logs(
    limit: int = Query(
        50,
        ge=1,
        le=100,
        description="Número máximo de errores a retornar",
    ),
    current_user: CurrentUser = Depends(current_user_dep),
    db=Depends(get_db),
):
    try:
        return get_error_logs(
            tenant_id=current_user.tenant.id,
            limit=limit,
            db=db,
        )
    except Exception as exc:
        logger.error(f"/performance/error-logs failed: {exc}")
        raise HTTPException(status_code=500, detail="Error interno de logs") from exc
