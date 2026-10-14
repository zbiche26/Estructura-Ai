from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, status

from src.core.database import SupabaseClient, get_db
from src.core.logger import logger
from src.http.deps import CurrentUser, get_current_user, get_tenant_id
from src.http.schemas.notifications import (
    NotificationItem,
    NotificationsResponse,
    NotificationType,
)

router = APIRouter(prefix="/notifications", tags=["Notifications"])

_PAGE_SIZE_MAX = 100
_PAGE_SIZE_DEFAULT = 20


def _current_user(
    tenant_id: str = Depends(get_tenant_id),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> CurrentUser:
    return get_current_user(tenant_id=tenant_id, authorization=authorization)


@router.get(
    "",
    response_model=NotificationsResponse,
    summary="Listar notificaciones del tenant",
    description=(
        "Devuelve las notificaciones del tenant autenticado ordenadas por "
        "`created_at` descendente. Incluye conteo total y de no leídas. "
        "Filtrable por `type` y `unread`."
    ),
)
def list_notifications(
    page: int = Query(1, ge=1, description="Página (inicia en 1)"),
    page_size: int = Query(
        _PAGE_SIZE_DEFAULT,
        ge=1,
        le=_PAGE_SIZE_MAX,
        description=f"Tamaño de página (máx {_PAGE_SIZE_MAX})",
    ),
    type: Optional[NotificationType] = Query(
        None,
        description="Filtro por tipo: billing | onboarding | limit | performance",
    ),
    unread: bool = Query(False, description="Solo notificaciones no leídas"),
    current_user: CurrentUser = Depends(_current_user),
    db: SupabaseClient = Depends(get_db),
) -> NotificationsResponse:
    tenant_id = str(current_user.tenant.id)
    offset = (page - 1) * page_size

    try:
        # ── Consulta principal ──────────────────────────────────────────────
        query = (
            db.client.table("notifications")
            .select("id, type, title, body, read_at, created_at", count="exact")
            .eq("tenant_id", tenant_id)
            .order("created_at", desc=True)
            .range(offset, offset + page_size - 1)
        )

        if type:
            query = query.eq("type", type)

        if unread:
            query = query.is_("read_at", "null")

        result = query.execute()

        # ── Conteo de no leídas (siempre, independiente del filtro) ────────
        unread_result = (
            db.client.table("notifications")
            .select("id", count="exact")
            .eq("tenant_id", tenant_id)
            .is_("read_at", "null")
            .limit(0)
            .execute()
        )

    except Exception as exc:
        logger.error("Error consultando notifications para tenant %s: %s", tenant_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "DB_UNAVAILABLE",
                "message": "No se pudo obtener las notificaciones.",
            },
        ) from exc

    items = [NotificationItem(**row) for row in (result.data or [])]

    return NotificationsResponse(
        data=items,
        total=int(result.count or 0),
        unread=int(unread_result.count or 0),
    )


@router.patch(
    "/{notification_id}/read",
    response_model=NotificationItem,
    summary="Marcar notificación como leída",
    description="Setea `read_at` de la notificación del tenant autenticado con timestamp actual en UTC.",
)
def mark_notification_as_read(
    notification_id: UUID = Path(..., description="ID de la notificación"),
    current_user: CurrentUser = Depends(_current_user),
    db: SupabaseClient = Depends(get_db),
) -> NotificationItem:
    tenant_id = str(current_user.tenant.id)

    try:
        result = (
            db.client.table("notifications")
            .update({"read_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", str(notification_id))
            .eq("tenant_id", tenant_id)
            .select("id, type, title, body, read_at, created_at")
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.error(
            "Error marcando notificación como leída para tenant %s, notification %s: %s",
            tenant_id,
            notification_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "DB_UNAVAILABLE",
                "message": "No se pudo actualizar la notificación.",
            },
        ) from exc

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "NOTIFICATION_NOT_FOUND",
                "message": "Notificación no encontrada.",
            },
        )

    return NotificationItem(**result.data[0])
