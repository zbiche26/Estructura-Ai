"""
Router de WhatsApp Webhooks (Multi-Tenant)
ACK inmediato + cola de procesamiento asíncrono

Cambios vs versión anterior:
- receive_webhook ya NO llama al orquestador directamente
- Solo encola el job en message_jobs y retorna 200 en < 500ms
- El worker asíncrono (message_worker.py) consume la cola
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os

from fastapi import APIRouter, BackgroundTasks, Request, status, Path
from fastapi.responses import JSONResponse, PlainTextResponse

from src.core.tenant_context import TenantContextManager
from src.core.logger import logger

router = APIRouter(tags=["whatsapp"])


# ─── Utilidades ──────────────────────────────────────────────────────────────


def verify_webhook_signature(
    body: bytes, signature_header: str | None, secret: str | None
) -> bool:
    if not secret:
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = signature_header[7:]
    computed = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, expected)


def _extract_message_id(payload: dict) -> str | None:
    """Extrae el whatsapp_message_id del primer mensaje del payload."""
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                msgs = change.get("value", {}).get("messages", [])
                if msgs:
                    return msgs[0].get("id")
    except Exception:
        pass
    return None


def _has_real_messages(payload: dict) -> bool:
    """True si el payload contiene mensajes reales (no solo status updates)."""
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                if value.get("messages") and not value.get("statuses"):
                    return True
    except Exception:
        pass
    return False


async def _enqueue_message(tenant_id: str, whatsapp_message_id: str, payload: dict):
    """
    Inserta el mensaje en message_jobs.
    El UNIQUE constraint en whatsapp_message_id maneja deduplicación automáticamente.
    """
    try:
        from src.core.database import get_db

        supabase = get_db().client
        supabase.table("message_jobs").insert(
            {
                "tenant_id": tenant_id,
                "whatsapp_message_id": whatsapp_message_id,
                "payload": payload,
                "status": "pending",
                "attempts": 0,
            }
        ).execute()
        logger.info(f"[QUEUE] Job encolado: {whatsapp_message_id}")
    except Exception as e:
        err = str(e).lower()
        if "duplicate" in err or "unique" in err:
            logger.info(f"[QUEUE] Duplicado ignorado: {whatsapp_message_id}")
        else:
            logger.error(f"[QUEUE] Error encolando job: {e}")


# ─── GET — Verificación de Meta ───────────────────────────────────────────────


@router.get("/webhook/whatsapp/{tenant_id}")
def verify_webhook(
    tenant_id: str = Path(...),
    request: Request = None,
):
    mode = request.query_params.get("hub.mode", "")
    token = request.query_params.get("hub.verify_token", "")
    challenge = request.query_params.get("hub.challenge", "")

    tenant = TenantContextManager.get_current()
    if not tenant:
        return PlainTextResponse("Tenant not found", status_code=404)

    verify_token = tenant.get_config("whatsapp_verify_token") or os.getenv(
        "WHATSAPP_VERIFY_TOKEN"
    )

    if mode == "subscribe" and verify_token and token == verify_token:
        return PlainTextResponse(str(challenge), status_code=200)
    return PlainTextResponse("Verification failed", status_code=403)


# ─── POST — Recepción de mensajes ─────────────────────────────────────────────


@router.post(
    "/webhook/whatsapp/{tenant_id}",
    summary="Recepción de mensajes de WhatsApp",
)
async def receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    tenant_id: str = Path(...),
):
    """
    ACK inmediato a Meta (< 500ms) + encola para procesamiento asíncrono.

    Meta exige HTTP 200 en menos de 5 segundos.
    Si tardamos más, reintenta el webhook y el bot responde duplicado.
    Solución: ACK inmediato + procesar en background.
    """
    body = await request.body()

    tenant = TenantContextManager.get_current()
    if not tenant:
        # Retornar 200 igual — Meta no debe reintentar por problemas nuestros
        return JSONResponse({"status": "no_tenant"}, status_code=200)
    # ✅ FIX: Respetar whatsapp_enabled desde Supabase
    if not tenant.get_config("whatsapp_enabled", True):
        logger.info(
            f"[WEBHOOK] WhatsApp desactivado para tenant {tenant_id} — ignorando mensaje"
        )
        return JSONResponse({"status": "disabled"}, status_code=200)

    # Validación HMAC (opcional — solo si el tenant tiene webhook_secret)

    # Validación HMAC (opcional — solo si el tenant tiene webhook_secret)
    webhook_secret = tenant.get_config("whatsapp_webhook_secret")
    if webhook_secret:
        signature = request.headers.get("x-hub-signature-256")
        if not verify_webhook_signature(body, signature, webhook_secret):
            logger.warning(f"[WEBHOOK] Firma inválida para tenant {tenant_id}")
            # Retornar 200 para evitar reintentos de Meta en firma inválida
            return JSONResponse({"status": "invalid_signature"}, status_code=200)

    # Parsear JSON
    try:
        payload = json.loads(body.decode("utf-8")) if body else {}
    except json.JSONDecodeError:
        return JSONResponse({"status": "invalid_json"}, status_code=200)

    # Solo procesar mensajes reales (ignorar status updates de entrega/lectura)
    if not _has_real_messages(payload):
        return JSONResponse(
            {"status": "received", "type": "status_update"}, status_code=200
        )

    # Extraer message_id para deduplicación en BD
    whatsapp_message_id = _extract_message_id(payload)
    if not whatsapp_message_id:
        return JSONResponse(
            {"status": "received", "type": "no_message_id"}, status_code=200
        )

    # Encolar en background — esto no bloquea el return
    background_tasks.add_task(
        _enqueue_message,
        tenant_id=str(tenant.tenant_id),
        whatsapp_message_id=whatsapp_message_id,
        payload=payload,
    )

    # ✅ ACK inmediato a Meta — el procesamiento ocurre después
    return JSONResponse(
        {"status": "queued", "message_id": whatsapp_message_id},
        status_code=200,
    )
