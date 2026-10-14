from __future__ import annotations

import secrets
import requests
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Response, status
from typing import Optional
from uuid import UUID

from src.core.logger import logger
from src.http.deps import CurrentUser, get_current_user, get_tenant_id
from src.models import DeliveryStatus
from src.repositories.webhook_repository import WebhookDeliveryRepository, WebhookRepository
from src.schemas.webhook_schemas import (
    WebhookCreateRequest,
    WebhookDeliveryResponse,
    WebhookListResponse,
    WebhookResponse,
    WebhookTestRequest,
    WebhookUpdateRequest,
)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

webhook_repo = WebhookRepository()
delivery_repo = WebhookDeliveryRepository()


def current_user_dep(
    tenant_id: str = Depends(get_tenant_id),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> CurrentUser:
    """Dependency que autentica y popula el TenantContextManager."""
    return get_current_user(tenant_id=tenant_id, authorization=authorization)


@router.post("/", response_model=WebhookResponse, status_code=status.HTTP_201_CREATED)
def create_webhook(
    payload: WebhookCreateRequest,
    current_user: CurrentUser = Depends(current_user_dep),
):
    """Crea un webhook para el tenant actual."""
    webhook_data = payload.model_dump(mode="json")
    webhook_data["secret"] = f"whsec_{secrets.token_hex(16)}"
    webhook_data["tenant_id"] = current_user.tenant.id
    webhook = webhook_repo.create(webhook_data)
    return webhook


@router.get("/", response_model=WebhookListResponse)
def list_webhooks(
    current_user: CurrentUser = Depends(current_user_dep),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    items = webhook_repo.get_all(limit=limit, offset=offset)
    total = webhook_repo.count()
    return {"items": items, "total": total}


@router.get("/{webhook_id}", response_model=WebhookResponse)
def get_webhook(
    webhook_id: UUID = Path(..., description="ID del webhook"),
    current_user: CurrentUser = Depends(current_user_dep),
):
    webhook = webhook_repo.get_by_id(webhook_id)
    if not webhook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    return webhook


@router.put("/{webhook_id}", response_model=WebhookResponse)
def update_webhook(
    webhook_id: UUID,
    payload: WebhookUpdateRequest,
    current_user: CurrentUser = Depends(current_user_dep),
):
    changes = payload.model_dump(mode="json", exclude_unset=True)
    webhook = webhook_repo.update(webhook_id, changes)
    if not webhook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    return webhook


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_webhook(
    webhook_id: UUID,
    current_user: CurrentUser = Depends(current_user_dep),
):
    deleted = webhook_repo.delete(webhook_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{webhook_id}/deliveries", response_model=list[WebhookDeliveryResponse])
def get_webhook_deliveries(
    webhook_id: UUID,
    current_user: CurrentUser = Depends(current_user_dep),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    webhook = webhook_repo.get_by_id(webhook_id)
    if not webhook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    deliveries = delivery_repo.list_for_webhook(webhook_id, limit=limit, offset=offset)
    return deliveries


@router.post(
    "/{webhook_id}/test",
    response_model=WebhookDeliveryResponse,
    status_code=status.HTTP_200_OK,
    summary="Envía un webhook de prueba manualmente",
)
def test_webhook_delivery(
    webhook_id: UUID,
    payload: WebhookTestRequest,
    current_user: CurrentUser = Depends(current_user_dep),
):
    webhook = webhook_repo.get_by_id(webhook_id)
    if not webhook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")

    headers = {"X-Webhook-Id": str(webhook_id)}
    headers.update(webhook.headers or {})
    headers.update(payload.headers or {})
    if webhook.secret and "X-Webhook-Secret" not in headers:
        headers["X-Webhook-Secret"] = webhook.secret

    try:
        resp = requests.post(webhook.url, json=payload.payload, headers=headers, timeout=5)
        status_value = DeliveryStatus.SUCCESS if resp.status_code < 400 else DeliveryStatus.FAILED
        delivery = delivery_repo.log(
            {
                "webhook_id": webhook.id,
                "tenant_id": webhook.tenant_id,
                "delivery_status": status_value,
                "response_status_code": resp.status_code,
                "response_body": resp.text,
                "request_payload": payload.payload,
                "event_type": payload.payload.get("event", "test"),
            }
        )
        if status_value == DeliveryStatus.FAILED:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Remote endpoint returned an error",
            )
        return delivery
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error enviando webhook {webhook_id}: {exc}")
        delivery = delivery_repo.log(
            {
                "webhook_id": webhook.id,
                "tenant_id": webhook.tenant_id,
                "delivery_status": DeliveryStatus.FAILED,
                "error_message": str(exc),
                "request_payload": payload.payload,
                "event_type": payload.payload.get("event", "test"),
            }
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Webhook delivery failed") from exc