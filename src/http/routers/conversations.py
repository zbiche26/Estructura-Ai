from __future__ import annotations

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, status
from fastapi.responses import JSONResponse

from src.core.database import get_db
from src.http.deps import CurrentUser, get_current_user, get_tenant_id
from src.http.schemas.conversations import (
    ConversationListItem,
    ConversationsListResponse,
    ConversationUpdate,
)
from src.http.schemas.messages import (
    ConversationMessageItem,
    ConversationMessagesResponse,
    MessageCreate,
    ReactivateConversationRequest,
    ReactivateConversationResponse,
)
from src.repositories.conversation_repo import ConversationRepo
from src.repositories.message_repo import MessageRepo
from src.services import whatsapp_service
from src.core.logger import logger

router = APIRouter(prefix="/conversations", tags=["Conversations"])


def current_user_dep(
    tenant_id: str = Depends(get_tenant_id),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> CurrentUser:
    return get_current_user(tenant_id=tenant_id, authorization=authorization)


@router.get(
    "",
    response_model=ConversationsListResponse,
    summary="Listado de conversaciones",
)
def list_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    contact_type: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(current_user_dep),
    db=Depends(get_db),
) -> ConversationsListResponse:
    repo = ConversationRepo(client=db.client)
    payload = repo.list_conversations(
        tenant_id=current_user.tenant.id,
        page=page,
        page_size=page_size,
        status=status.strip() if isinstance(status, str) and status.strip() else None,
        contact_type=(
            contact_type.strip()
            if isinstance(contact_type, str) and contact_type.strip()
            else None
        ),
    )
    return ConversationsListResponse(**payload)


@router.patch(
    "/{conversation_id}",
    response_model=ConversationListItem,
    summary="Actualización parcial de conversación",
)
def patch_conversation(
    payload: ConversationUpdate,
    conversation_id: str = Path(...),
    current_user: CurrentUser = Depends(current_user_dep),
    db=Depends(get_db),
) -> ConversationListItem:
    repo = ConversationRepo(client=db.client)
    changes = payload.model_dump(mode="json", exclude_unset=True)
    updated = repo.update_conversation(
        tenant_id=current_user.tenant.id,
        conversation_id=conversation_id,
        updates=changes,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationListItem(**updated)


@router.post("/{conversation_id}/read", summary="Marcar conversación como leída")
def mark_conversation_as_read(
    conversation_id: str = Path(...),
    current_user: CurrentUser = Depends(current_user_dep),
    db=Depends(get_db),
) -> dict[str, bool]:
    repo = ConversationRepo(client=db.client)
    ok = repo.mark_as_read(
        tenant_id=current_user.tenant.id,
        conversation_id=conversation_id,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"ok": True}


@router.get(
    "/{conversation_id}/messages",
    response_model=ConversationMessagesResponse,
    summary="Listado de mensajes por conversación",
)
def get_conversation_messages(
    conversation_id: str = Path(...),
    limit: int = Query(50, ge=1, le=100),
    before: Optional[datetime] = Query(None),
    current_user: CurrentUser = Depends(current_user_dep),
    db=Depends(get_db),
) -> ConversationMessagesResponse:
    repo = MessageRepo(client=db.client)
    payload = repo.get_messages_by_conversation(
        tenant_id=current_user.tenant.id,
        conversation_id=conversation_id,
        limit=limit,
        before=before,
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationMessagesResponse(**payload)


@router.post(
    "/{conversation_id}/messages",
    response_model=ConversationMessageItem,
    summary="Envío manual de mensaje por agente",
)
def post_manual_conversation_message(
    payload: MessageCreate,
    conversation_id: str = Path(...),
    current_user: CurrentUser = Depends(current_user_dep),
    db=Depends(get_db),
) -> ConversationMessageItem:
    repo = MessageRepo(client=db.client)

    conversation = repo.get_conversation_for_tenant(
        tenant_id=current_user.tenant.id,
        conversation_id=conversation_id,
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if repo.is_bot_active(conversation):
        logger.warning(
            f"[POST /messages] 409 — bot activo en conversación {conversation_id}, "
            f"tenant={current_user.tenant.id}"
        )
        raise HTTPException(
            status_code=409,
            detail="El bot debe estar desactivado para enviar mensajes manuales",
        )

    last_contact_at = repo.get_last_contact_message_at(conversation_id=conversation_id)
    if not repo.is_manual_window_open(last_contact_at):
        return JSONResponse(
            status_code=422,
            content={
                "error": "ventana_expirada",
                "templates_disponibles": [],
            },
        )

    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Message content cannot be empty")

    destination_phone = repo.extract_conversation_phone(conversation)
    if not destination_phone:
        raise HTTPException(
            status_code=422, detail="Conversation has no destination phone"
        )

    duplicate = repo._find_recent_duplicate(
        conversation_id=conversation_id,
        content=content,
        sender="agent",
        window_seconds=3,
    )
    if duplicate is not None:
        logger.debug(
            f"[POST /messages] Petición duplicada — conversation={conversation_id}"
        )
        mapped = repo._map_row(duplicate)
        mapped["sender"] = "agent"
        mapped["status"] = "sent"
        return ConversationMessageItem(**mapped)

    try:
        whatsapp_service.send_text_message(to=destination_phone, content=content)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    try:
        stored = repo.persist_manual_agent_message(
            tenant_id=current_user.tenant.id,
            conversation_id=conversation_id,
            content=content,
        )
    except Exception as persist_exc:
        logger.error(
            f"[POST /messages] Error persistiendo — conversation={conversation_id}, error={persist_exc}"
        )
        stored = {
            "id": "",
            "content": content,
            "sender": "agent",
            "status": "sent",
            "sent_at": datetime.utcnow().isoformat() + "Z",
        }

    return ConversationMessageItem(**stored)


@router.post(
    "/{conversation_id}/reactivate",
    response_model=ReactivateConversationResponse,
    summary="Reactivar conversación con plantilla WhatsApp",
    status_code=status.HTTP_200_OK,
)
def reactivate_conversation(
    payload: ReactivateConversationRequest,
    conversation_id: str = Path(..., description="ID de la conversación"),
    current_user: CurrentUser = Depends(current_user_dep),
    db=Depends(get_db),
) -> ReactivateConversationResponse:
    """
    Envía una plantilla de WhatsApp para reactivar una conversación
    cuya ventana de 24h ha expirado.

    - Requiere que el bot esté desactivado (bot_active = false)
    - Usa la API de plantillas de Meta (sin restricción de 24h)
    - El template_name debe estar aprobado en Meta Business Manager
    """
    repo = MessageRepo(client=db.client)

    conversation = repo.get_conversation_for_tenant(
        tenant_id=current_user.tenant.id,
        conversation_id=conversation_id,
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if repo.is_bot_active(conversation):
        raise HTTPException(
            status_code=409,
            detail="Desactiva el bot antes de reactivar manualmente la conversación",
        )

    destination_phone = repo.extract_conversation_phone(conversation)
    if not destination_phone:
        raise HTTPException(
            status_code=422,
            detail="La conversación no tiene número de teléfono destino",
        )

    try:
        whatsapp_service.send_template_message(
            to=destination_phone,
            template_name=payload.template_name,
            language=payload.language,
            params=payload.params,
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=502, detail=f"Error enviando plantilla a Meta: {str(e)}"
        )

    logger.info(
        f"[REACTIVATE] Plantilla '{payload.template_name}' enviada a {destination_phone} "
        f"en conversación {conversation_id} por tenant {current_user.tenant.id}"
    )

    return ReactivateConversationResponse(
        conversation_id=conversation_id,
        template_name=payload.template_name,
        status="sent",
        message=f"Plantilla '{payload.template_name}' enviada exitosamente",
    )
