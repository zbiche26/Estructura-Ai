from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, Query, HTTPException, status
from pydantic.functional_validators import AfterValidator

from src.http.schemas.analytics_schemas import (
    AnalyticsOverviewResponse,
    AnalyticsSeriesResponse,
    ConversationsByDayResponse,
    HandoffRateResponse,
    HourlyActivityResponse,
    IntentDistributionResponse,
    TopProductsConsultedResponse,
    TopProductsSoldResponse,
)
from src.services.analytics_service import (
    get_analytics_overview,
    get_conversations_by_day,
    get_handoff_rate,
    get_conversations_by_week,
    get_conversations_by_month,
    get_hourly_activity,
    get_intent_distribution,
    get_top_products_consulted,
    get_top_products_sold,
)
from src.http.deps import CurrentUser, get_current_user, get_tenant_id
from src.core.database import get_db


def current_user_dep(
    tenant_id: str = Depends(get_tenant_id),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> CurrentUser:
    """Resuelve al usuario actual asegurando que exista un tenant válido."""
    return get_current_user(tenant_id=tenant_id, authorization=authorization)

router = APIRouter(prefix="/analytics", tags=["Analytics"])

@router.get(
    "/overview",
    response_model=AnalyticsOverviewResponse,
    summary="Overview general de analytics",
    description=(
        "Devuelve métricas resumidas de conversaciones para la ventana indicada.\n\n"
        "Valores válidos para window_days: 1 (hoy), 7 (última semana), 30 (último mes)."
    ),
)
def overview_analytics(
    window_days: int = Query(
        7,
        description="Ventana (en días). Valores válidos: 1, 7, 30.",
    ),
    current_user: CurrentUser = Depends(current_user_dep),
    db=Depends(get_db),
):
    """Devuelve un resumen general de analytics de conversaciones."""
    if window_days not in (1, 7, 30):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="window_days debe ser uno de los siguientes valores: 1, 7 o 30",
        )
    return get_analytics_overview(
        tenant_id=current_user.tenant.id,
        window_days=window_days,
        db=db,
    )


@router.get(
    "/hourly-activity",
    response_model=HourlyActivityResponse,
    summary="Actividad por hora del día",
    description=(
        "Devuelve el total de conversaciones agrupadas por hora del día (0-23) "
        "para la ventana indicada. Siempre retorna 24 buckets.\n\n"
        "Valores válidos para window_days: 1 (hoy), 7 (última semana), 30 (último mes)."
    ),
)
def hourly_activity(
    window_days: int = Query(
        7,
        description="Ventana (en días). Valores válidos: 1, 7, 30.",
    ),
    current_user: CurrentUser = Depends(current_user_dep),
    db=Depends(get_db),
):
    if window_days not in (1, 7, 30):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="window_days debe ser uno de los siguientes valores: 1, 7 o 30",
        )
    return get_hourly_activity(
        tenant_id=current_user.tenant.id,
        window_days=window_days,
        db=db,
    )


@router.get(
    "/conversations/day",
    response_model=ConversationsByDayResponse,
    summary="Conversaciones por día",
    description=(
        "Devuelve conteos de conversaciones por día para la ventana indicada.\n\n"
        "Valores válidos para window_days: 1 (hoy), 7 (última semana), 30 (último mes)."
    ),
)
def conversations_by_day(
    window_days: int = Query(
        30,
        description="Ventana (en días). Valores válidos: 1, 7, 30.",
    ),
    current_user: CurrentUser = Depends(current_user_dep),
    db=Depends(get_db),
):
    if window_days not in (1, 7, 30):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="window_days debe ser uno de los siguientes valores: 1, 7 o 30",
        )
    return get_conversations_by_day(
        tenant_id=current_user.tenant.id,
        window_days=window_days,
        db=db,
    )


@router.get(
    "/handoff-rate",
    response_model=HandoffRateResponse,
    summary="Tasa de transferencia a humano",
    description="Devuelve la tasa de conversaciones transferidas a un agente humano (decimal 0–1) en la ventana indicada.",
)
def handoff_rate_endpoint(
    window_days: int = Query(
        7,
        description="Ventana (en días). Valores válidos: 1, 7, 30.",
    ),
    current_user: CurrentUser = Depends(current_user_dep),
    db=Depends(get_db),
):
    if window_days not in (1, 7, 30):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="window_days debe ser uno de los siguientes valores: 1, 7 o 30",
        )

    return get_handoff_rate(
        tenant_id=current_user.tenant.id,
        window_days=window_days,
        db=db,
    )


@router.get(
    "/conversations/week",
    response_model=AnalyticsSeriesResponse,
    summary="Conversaciones por semana",
)
def conversations_by_week(
    weeks: int = Query(
        12,
        ge=1,
        le=52,
        description="Número de semanas a considerar",
    ),
    current_user: CurrentUser = Depends(current_user_dep),
    db=Depends(get_db),
):
    return get_conversations_by_week(
        tenant_id=current_user.tenant.id,
        weeks=weeks,
        db=db,
    )


@router.get(
    "/conversations/month",
    response_model=AnalyticsSeriesResponse,
    summary="Conversaciones por mes",
)
def conversations_by_month(
    months: int = Query(
        12,
        ge=1,
        le=24,
        description="Número de meses a considerar",
    ),
    current_user: CurrentUser = Depends(current_user_dep),
    db=Depends(get_db),
):
    return get_conversations_by_month(
        tenant_id=current_user.tenant.id,
        months=months,
        db=db,
    )


@router.get(
    "/intents/distribution",
    response_model=IntentDistributionResponse,
    summary="Distribución de intents",
)
def intent_distribution(
    window_days: int = Query(
        30,
        ge=1,
        le=180,
        description="Ventana (en días) para analizar intents",
    ),
    current_user: CurrentUser = Depends(current_user_dep),
    db=Depends(get_db),
):
    return get_intent_distribution(
        tenant_id=current_user.tenant.id,
        window_days=window_days,
        db=db,
    )


@router.get(
    "/products/top-consulted",
    response_model=TopProductsConsultedResponse,
    summary="Top productos consultados",
)
def top_products_consulted(
    window_days: int = Query(
        30,
        ge=1,
        le=365,
        description="Ventana (en días) para agrupar consultas",
    ),
    limit: int = Query(
        10,
        ge=1,
        le=50,
        description="Límite de resultados",
    ),
    current_user: CurrentUser = Depends(current_user_dep),
    db=Depends(get_db),
):
    return get_top_products_consulted(
        tenant_id=current_user.tenant.id,
        window_days=window_days,
        limit=limit,
        db=db,
    )


@router.get(
    "/products/top-sold",
    response_model=TopProductsSoldResponse,
    summary="Top productos más vendidos",
)
def top_products_sold(
    window_days: int = Query(
        30,
        ge=1,
        le=365,
        description="Ventana (en días) para ventas",
    ),
    limit: int = Query(
        10,
        ge=1,
        le=50,
        description="Límite de resultados",
    ),
    current_user: CurrentUser = Depends(current_user_dep),
    db=Depends(get_db),
):
    return get_top_products_sold(
        tenant_id=current_user.tenant.id,
        window_days=window_days,
        limit=limit,
        db=db,
    )
