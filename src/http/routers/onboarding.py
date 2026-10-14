# -*- coding: utf-8 -*-
"""
onboarding.py - Onboarding Router
==================================
Endpoints para el wizard de onboarding por tenant.

Endpoints:
    GET   /onboarding/status  - Leer estado actual (lee de BD, no stub)
    PATCH /onboarding/status  - Actualizar pasos completados (upsert)

Comportamiento:
    - GET: Si no existe registro, crea uno vacío y lo retorna
    - PATCH: Acepta campos parciales, hace upsert en BD
    - completed_at: Se setea automáticamente cuando los 3 pasos son true
    - locked: Se activa cuando completed_at está seteado
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from src.core.database import get_db
from src.core.logger import logger
from ..deps import CurrentUser, get_current_user, get_tenant_id

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


# ── Dependency ───────────────────────────────────────────────────────────────


def current_user_dep(
    tenant_id: str = Depends(get_tenant_id),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> CurrentUser:
    return get_current_user(tenant_id=tenant_id, authorization=authorization)


# ── Schemas ──────────────────────────────────────────────────────────────────


class OnboardingStatus(BaseModel):
    whatsapp_connected: bool
    training_done: bool
    first_conversation_done: bool


class OnboardingStatusFull(BaseModel):
    whatsapp_connected: bool
    training_done: bool
    first_conversation_done: bool
    completed_at: Optional[datetime]
    locked: bool
    v: int


class OnboardingStatusResponse(BaseModel):
    data: OnboardingStatusFull


class OnboardingStatusUpdate(BaseModel):
    """Acepta campos parciales — solo actualiza los que se envíen"""

    whatsapp_connected: Optional[bool] = None
    training_done: Optional[bool] = None
    first_conversation_done: Optional[bool] = None


# ── Helpers ──────────────────────────────────────────────────────────────────


def _get_or_create_status(tenant_id: str) -> dict:
    """
    Obtiene el estado de onboarding del tenant.
    Si no existe, crea un registro vacío y lo retorna.
    Nunca retorna 404.
    """
    db = get_db()

    try:
        result = (
            db.client.table("onboarding_status")
            .select("*")
            .eq("tenant_id", tenant_id)
            .execute()
        )
        records = result.data or []

        if records:
            return records[0]

        # No existe — crear registro vacío
        now = datetime.now(timezone.utc).isoformat()
        insert_result = (
            db.client.table("onboarding_status")
            .insert(
                {
                    "tenant_id": tenant_id,
                    "whatsapp_connected": False,
                    "training_done": False,
                    "first_conversation_done": False,
                    "completed_at": None,
                    "locked": False,
                    "v": 1,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            .execute()
        )

        new_records = insert_result.data or []
        if new_records:
            return new_records[0]

        # Fallback si el insert no retorna data
        return {
            "tenant_id": tenant_id,
            "whatsapp_connected": False,
            "training_done": False,
            "first_conversation_done": False,
            "completed_at": None,
            "locked": False,
            "v": 1,
        }

    except Exception as e:
        logger.error(f"[ONBOARDING] Error get_or_create tenant={tenant_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener el estado de onboarding",
        )


def _format_response(record: dict) -> OnboardingStatusResponse:
    """Formatea el registro de BD a la respuesta"""
    return OnboardingStatusResponse(
        data=OnboardingStatusFull(
            whatsapp_connected=record.get("whatsapp_connected", False),
            training_done=record.get("training_done", False),
            first_conversation_done=record.get("first_conversation_done", False),
            completed_at=record.get("completed_at"),
            locked=record.get("locked", False),
            v=record.get("v", 1),
        )
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get(
    "/status",
    response_model=OnboardingStatusResponse,
    summary="Get onboarding status",
    description="Retorna el estado actual del wizard de onboarding. "
    "Si no existe registro, crea uno vacío con todos los pasos en false.",
)
def get_onboarding_status(
    current_user: CurrentUser = Depends(current_user_dep),
) -> OnboardingStatusResponse:
    tenant_id = current_user.tenant.id
    record = _get_or_create_status(tenant_id)
    logger.debug(f"[ONBOARDING] GET status tenant={tenant_id}")
    return _format_response(record)


@router.patch(
    "/status",
    response_model=OnboardingStatusResponse,
    summary="Update onboarding status",
    description="Actualiza los pasos completados del wizard de onboarding. "
    "Acepta campos parciales. Hace upsert en BD. "
    "Cuando los 3 pasos son true, setea completed_at automáticamente.",
)
def update_onboarding_status(
    data: OnboardingStatusUpdate,
    current_user: CurrentUser = Depends(current_user_dep),
) -> OnboardingStatusResponse:
    tenant_id = current_user.tenant.id
    db = get_db()

    # Obtener estado actual (o crear si no existe)
    current = _get_or_create_status(tenant_id)

    # Si está locked, no permitir cambios
    if current.get("locked", False):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El onboarding ya está completado y bloqueado",
        )

    # Construir campos a actualizar (solo los que vienen en el body)
    update_fields: dict = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    if data.whatsapp_connected is not None:
        update_fields["whatsapp_connected"] = data.whatsapp_connected

    if data.training_done is not None:
        update_fields["training_done"] = data.training_done

    if data.first_conversation_done is not None:
        update_fields["first_conversation_done"] = data.first_conversation_done

    # Calcular estado final mergeando con el actual
    final_whatsapp = update_fields.get(
        "whatsapp_connected", current.get("whatsapp_connected", False)
    )
    final_training = update_fields.get(
        "training_done", current.get("training_done", False)
    )
    final_conversation = update_fields.get(
        "first_conversation_done", current.get("first_conversation_done", False)
    )

    # Si todos los pasos son true → setear completed_at y locked
    all_done = final_whatsapp and final_training and final_conversation
    if all_done and not current.get("completed_at"):
        update_fields["completed_at"] = datetime.now(timezone.utc).isoformat()
        update_fields["locked"] = True
        logger.info(f"[ONBOARDING] ✅ Onboarding completado para tenant={tenant_id}")

    try:
        result = (
            db.client.table("onboarding_status")
            .update(update_fields)
            .eq("tenant_id", tenant_id)
            .execute()
        )

        updated_records = result.data or []
        if updated_records:
            record = updated_records[0]
        else:
            # Merge manual si update no retorna data
            record = {**current, **update_fields}

        logger.info(
            f"[ONBOARDING] PATCH tenant={tenant_id} "
            f"fields={list(update_fields.keys())}"
        )

        return _format_response(record)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ONBOARDING] Error PATCH tenant={tenant_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al actualizar el estado de onboarding",
        )
