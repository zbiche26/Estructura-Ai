from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status

from ..deps import CurrentUser, get_current_user, get_tenant_id
from ..schemas.billing import BillingLimits, BillingSummary, BillingSummaryResponse
from src.core.database import SupabaseClient, get_db
from src.core.plans import get_plan_limits
from src.repositories.tenant_repository import tenant_repo

router = APIRouter(prefix="/billing", tags=["billing"])


def _count_products(db: SupabaseClient, tenant_id: str) -> int:
    result = (
        db.client.table("products")
        .select("id", count="exact")
        .eq("tenant_id", tenant_id)
        .limit(0)
        .execute()
    )
    return int(result.count or 0)


def current_user_dep(
    tenant_id: str = Depends(get_tenant_id),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> CurrentUser:
    return get_current_user(tenant_id=tenant_id, authorization=authorization)


@router.get(
    "/summary",
    response_model=BillingSummaryResponse,
    summary="Get billing summary",
    description="Devuelve resumen de plan y consumo real para paywall/gating UI.",
)
def get_billing_summary(
    current_user: CurrentUser = Depends(current_user_dep),
    db: SupabaseClient = Depends(get_db),
) -> BillingSummaryResponse:
    tenant = tenant_repo.find_by_id(current_user.tenant.id)
    if not tenant:
        # get_current_user ya valida tenant, pero mantenemos guard clause por seguridad.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant no encontrado",
        )

    usage_config = (tenant.config or {}).get("usage", {})
    messages_used = int(usage_config.get("messages_used", 0))

    plan_limits = get_plan_limits(str(tenant.plan))
    products_limit = int(plan_limits.get("max_products", tenant.max_products))
    messages_limit = int(
        plan_limits.get("max_conversations", tenant.max_conversations)
    )

    summary = BillingSummary(
        plan_id=str(tenant.plan),
        status="active" if tenant.is_active else "paused",
        products_count=_count_products(db, str(tenant.id)),
        conversations_month_count=messages_used,
        limits=BillingLimits(
            products=products_limit,
            conversations_month=messages_limit,
        ),
    )
    return BillingSummaryResponse(data=summary)
