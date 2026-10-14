from __future__ import annotations

from datetime import datetime, timezone

from ..deps import CurrentUser
from ..schemas.common import MeResponse, MeData, MePlan, MeUsage, UsageLimits, Meta


# Features por plan
PLAN_FEATURES = {
    "starter": ["onboarding", "billing", "conversations", "whatsapp", "inventory"],
    "growth": [
        "onboarding",
        "billing",
        "conversations",
        "whatsapp",
        "inventory",
        "analytics",
        "training",
        "excel_import",
    ],
    "enterprise": [
        "onboarding",
        "billing",
        "conversations",
        "whatsapp",
        "inventory",
        "analytics",
        "training",
        "excel_import",
        "webhooks",
        "reports",
        "performance",
    ],
}


def build_me_response(current: CurrentUser) -> MeResponse:
    tenant = current.tenant
    plan = (
        str(tenant.plan).lower()
        if hasattr(tenant, "plan") and tenant.plan
        else "starter"
    )

    features = PLAN_FEATURES.get(plan, PLAN_FEATURES["starter"])

    data = MeData(
        user={
            "id": current.user.id,
            "email": current.user.email,
            "full_name": current.user.name,
        },
        tenant={
            "id": current.tenant.id,
            "name": current.tenant.name,
            "slug": getattr(current.tenant, "slug", ""),
        },
        plan=MePlan(
            id=plan,
            status="active",
            trial_ends_at=None,
        ),
        features=features,
        usage=MeUsage(
            products_count=0,
            conversations_month_count=0,
            limits=UsageLimits(
                products=getattr(tenant, "max_products", 500),
                conversations_month=getattr(tenant, "max_conversations", 1000),
            ),
        ),
    )
    return MeResponse(data=data, meta=Meta())
