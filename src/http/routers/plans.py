from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from src.http.schemas.plans import PlanPublicItem, PlanPublicLimits
from src.services.billing_service import PlanDefinitionService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["plans"])


@router.get(
    "/plans",
    response_model=list[PlanPublicItem],
    summary="Catálogo público de planes",
    description=(
        "Devuelve el catálogo de planes para UI de pricing/landing. "
        "Los límites se leen en tiempo real desde la base de datos. "
        "Endpoint público: no requiere autenticación."
    ),
)
def get_plans_catalog() -> list[PlanPublicItem]:
    try:
        raw_plans = PlanDefinitionService.get_all_plans()
    except Exception as exc:
        logger.error("Error obteniendo catálogo de planes: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error_code": "PLANS_SERVICE_ERROR", "message": "No se pudo obtener el catálogo de planes."},
        ) from exc

    return [
        PlanPublicItem(
            id=plan["key"],
            name=plan["name"],
            slug=plan["key"],
            price_monthly=float(plan["prices"]["monthly"]),
            limits=PlanPublicLimits(
                max_agents=int(plan["limits"].get("agents", 0)),
                max_conversations_month=int(plan["limits"].get("conversations", 0)),
                max_team_members=int(plan["limits"].get("users", 0)),
            ),
            features=list(plan["features"]),
        )
        for plan in raw_plans
    ]
