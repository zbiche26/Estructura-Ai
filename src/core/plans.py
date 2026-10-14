"""Definición centralizada de planes y beneficios."""

from __future__ import annotations

from typing import Dict

from src.schemas.tenant_schemas import TenantPlanEnum

#los limitesd de productos son referencias no estaban definidos en el documento que me paso camilo
PLAN_BENEFITS: Dict[str, dict] = {
    TenantPlanEnum.STARTER.value: {
        "max_products": 100,
        "max_conversations": 1000,
    },
    TenantPlanEnum.GROWTH.value: {
        "max_products": 500,
        "max_conversations": 5000,
    },
    TenantPlanEnum.SCALE.value: {
        # Sujeo a cambios segun el cliente y negociación
        "max_products": 5000,
        "max_conversations": 20000,
    },
}


def get_plan_limits(plan: str) -> dict:
    """Obtiene límites por plan; cae a starter si no coincide."""
    return PLAN_BENEFITS.get(plan, PLAN_BENEFITS[TenantPlanEnum.STARTER.value]).copy()
