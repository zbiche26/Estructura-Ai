from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from src.repositories.conversation_repository import ConversationRepository
from src.repositories.product_repository import ProductRepository
from src.repositories.sale_repository import SaleRepository
from src.core.database import SupabaseClient
from src.core.logger import logger


def get_analytics_overview(
    *,
    tenant_id: str,
    window_days: int,
    db: SupabaseClient,
) -> Dict[str, Any]:
    """Calcula métricas resumidas de conversaciones para el tenant actual."""
    repo = ConversationRepository(client=db.client)

    try:
        total_conversations = repo.count_all()
    except Exception as exc:
        logger.error(f"Analytics overview - count_all error: {exc}")
        total_conversations = 0

    try:
        active_users = repo.count_active_users()
    except Exception as exc:
        logger.error(f"Analytics overview - count_active_users error: {exc}")
        active_users = 0

    try:
        window_minutes = window_days * 24 * 60
        avg_minutes = repo.get_average_response_time(window_minutes=window_minutes)
        avg_response_time_seconds = (avg_minutes * 60.0) if avg_minutes is not None else 0.0
    except Exception as exc:
        logger.error(f"Analytics overview - avg_response_time error: {exc}")
        avg_response_time_seconds = 0.0

    try:
        conversations_per_day = repo.get_conversations_per_day(last_days=window_days)
    except Exception as exc:
        logger.error(f"Analytics overview - conversations_per_day error: {exc}")
        conversations_per_day = {}

    return {
        "tenant_id": tenant_id,
        "total_conversations": total_conversations or 0,
        "active_users": active_users or 0,
        "avg_response_time_seconds": avg_response_time_seconds,
        "conversations_per_day": conversations_per_day or {},
        "window_days": window_days,
        "calculated_at": datetime.utcnow().isoformat(),
    }


def _aggregate_to_buckets(per_day: Dict[str, int], mode: str) -> List[Dict[str, Any]]:
    buckets: Dict[str, int] = {}
    for day_str, count in per_day.items():
        try:
            day = datetime.fromisoformat(day_str)
        except Exception:
            continue
        if mode == "day":
            key = day.strftime("%Y-%m-%d")
        elif mode == "week":
            iso_year, iso_week, _ = day.isocalendar()
            key = f"{iso_year}-W{iso_week:02d}"
        elif mode == "month":
            key = day.strftime("%Y-%m")
        else:
            continue
        buckets[key] = buckets.get(key, 0) + int(count)
    return [
        {"bucket": k, "total": v}
        for k, v in sorted(buckets.items())
    ]


def get_conversations_by_day(
    *,
    tenant_id: str,
    window_days: int,
    db: SupabaseClient,
) -> Dict[str, Any]:
    repo = ConversationRepository(client=db.client)
    try:
        per_day = repo.get_conversations_per_day(last_days=window_days, tenant_id=tenant_id)
    except Exception as exc:
        logger.error(f"Conversations by day error: {exc}")
        per_day = {}
    return {
        "data": [
            {"date": day, "count": count}
            for day, count in sorted((per_day or {}).items())
        ]
    }


def get_handoff_rate(
    *,
    tenant_id: str,
    window_days: int,
    db: SupabaseClient,
) -> Dict[str, Any]:
    # Calcular la fecha de inicio según la ventana de días
    date_from = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()

    result = db.client.from_("conversations") \
        .select("id, handoff") \
        .eq("tenant_id", tenant_id) \
        .gte("created_at", date_from) \
        .execute()

    total = len(result.data or [])
    transferred = sum(1 for c in (result.data or []) if c.get("handoff") is True)
    rate = round(transferred / total, 4) if total > 0 else 0.0

    return {
        "rate": rate,
        "transferred": transferred,
        "total": total,
    }


def get_conversations_by_week(
    *,
    tenant_id: str,
    weeks: int,
    db: SupabaseClient,
) -> Dict[str, Any]:
    window_days = weeks * 7
    repo = ConversationRepository(client=db.client)
    per_day = repo.get_conversations_per_day(last_days=window_days)
    buckets = _aggregate_to_buckets(per_day, mode="week")
    return {
        "tenant_id": tenant_id,
        "buckets": buckets,
        "window_days": window_days,
        "calculated_at": datetime.utcnow().isoformat(),
    }


def get_conversations_by_month(
    *,
    tenant_id: str,
    months: int,
    db: SupabaseClient,
) -> Dict[str, Any]:
    window_days = months * 31  # ventana amplia para abarcar meses completos
    repo = ConversationRepository(client=db.client)
    per_day = repo.get_conversations_per_day(last_days=window_days)
    buckets = _aggregate_to_buckets(per_day, mode="month")
    return {
        "tenant_id": tenant_id,
        "buckets": buckets,
        "window_days": window_days,
        "calculated_at": datetime.utcnow().isoformat(),
    }


def get_intent_distribution(
    *,
    tenant_id: str,
    window_days: int,
    db: SupabaseClient,
) -> Dict[str, Any]:
    repo = ConversationRepository(client=db.client)
    try:
        distribution = repo.get_intent_distribution(last_days=window_days)
    except Exception as exc:  # Defensa: evita 500 por errores de datastore
        logger.error(f"Intent distribution error: {exc}")
        distribution = {}
    buckets = sorted(
        [{"name": intent, "total": total} for intent, total in distribution.items()],
        key=lambda x: x["total"],
        reverse=True,
    )
    return {"data": buckets}


def get_top_products_consulted(
    *,
    tenant_id: str,
    window_days: int,
    limit: int,
    db: SupabaseClient,
) -> Dict[str, Any]:
    repo = ProductRepository(client=db.client)
    try:
        items = repo.get_top_consulted_products(last_days=window_days, limit=limit)
    except Exception as exc:  # Defensa: evita 500 por errores de datastore
        logger.error(f"Top consulted products error: {exc}")
        items = []
    return {
        "tenant_id": tenant_id,
        "items": items,
        "window_days": window_days,
        "limit": limit,
        "calculated_at": datetime.utcnow().isoformat(),
    }


def get_hourly_activity(
    *,
    tenant_id: str,
    window_days: int,
    db: SupabaseClient,
) -> Dict[str, Any]:
    """
    Devuelve la distribución de conversaciones por hora del día (0-23).
    Siempre retorna 24 buckets ordenados, incluso si alguna hora tiene 0.
    """
    repo = ConversationRepository(client=db.client)
    try:
        hourly = repo.get_hourly_activity(last_days=window_days)
    except Exception as exc:
        logger.error(f"Hourly activity error: {exc}")
        hourly = {h: 0 for h in range(24)}

    buckets = [
        {"hour": h, "label": f"{h:02d}:00", "total": hourly.get(h, 0)}
        for h in range(24)
    ]
    return {
        "tenant_id": tenant_id,
        "buckets": buckets,
        "window_days": window_days,
        "calculated_at": datetime.utcnow().isoformat(),
    }


def get_top_products_sold(
    *,
    tenant_id: str,
    window_days: int,
    limit: int,
    db: SupabaseClient,
) -> Dict[str, Any]:
    repo = SaleRepository(client=db.client)
    try:
        items = repo.get_top_selling_products(last_days=window_days, limit=limit)
    except Exception as exc:  # Defensa: evita 500 por errores de datastore
        logger.error(f"Top sold products error: {exc}")
        items = []
    return {
        "tenant_id": tenant_id,
        "items": items,
        "window_days": window_days,
        "limit": limit,
        "calculated_at": datetime.utcnow().isoformat(),
    }
