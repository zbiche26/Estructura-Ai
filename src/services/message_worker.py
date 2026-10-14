"""
Message Worker — Procesa jobs de la cola message_jobs
======================================================
Consume mensajes de forma asíncrona sin presión de tiempo.

Flujo:
  1. Lee jobs con status='pending' de message_jobs
  2. Marca como 'processing'
  3. Llama al WhatsAppHandler + AgentOrchestrator
  4. Marca como 'done' o 'failed' (max 3 intentos)
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from src.core.logger import logger
from src.core.process_identity import get_process_identity

# Variables que Railway documenta como siempre inyectadas a un deployment
# (docs.railway.com/variables/reference). Se usan varias -- no solo una --
# para que la detección de "estoy en Railway" no dependa de una sola
# variable; si Railway deja de inyectar alguna, las otras cubren.
_RAILWAY_ENV_MARKERS = (
    "RAILWAY_ENVIRONMENT_NAME",
    "RAILWAY_PROJECT_ID",
    "RAILWAY_SERVICE_ID",
)


def should_run_worker() -> bool:
    """
    Decide si este proceso debe correr el worker loop de message_jobs.

    WORKER_ENABLED explícito manda. Si no está seteado, el default es
    correr solo cuando se detecta que el proceso vive en Railway -- evita
    que un uvicorn local (con el .env de producción) reclame jobs en
    paralelo al worker real, sospechoso de causar mensajes duplicados
    (ver spec/07-investigacion-mensajes-duplicados-2026-07-07.md).
    """
    explicit = os.getenv("WORKER_ENABLED")
    if explicit is not None:
        return explicit.strip().lower() in ("1", "true", "yes", "on")
    return any(os.getenv(var) for var in _RAILWAY_ENV_MARKERS)


async def process_pending_jobs(max_jobs: int = 10):
    """
    Procesa jobs pendientes de la cola.
    Llamar periódicamente desde el startup loop.
    """
    try:
        from src.core.database import get_db

        supabase = get_db().client

        result = (
            supabase.table("message_jobs")
            .select("*")
            .eq("status", "pending")
            .order("created_at")
            .limit(max_jobs)
            .execute()
        )

        jobs = result.data or []
        if not jobs:
            return

        logger.info(f"[WORKER] {len(jobs)} jobs pendientes")

        for job in jobs:
            await _process_job(job, supabase)

    except Exception as e:
        logger.error(f"[WORKER] Error leyendo cola: {e}")


async def _process_job(job: dict, supabase):
    """Procesa un job con retry automático (max 3 intentos)."""
    job_id = job["id"]
    attempts = job.get("attempts", 0) + 1

    # Claim atómico: el UPDATE solo afecta la fila si seguía 'pending'.
    # Sin el AND status='pending', dos procesos leyendo el mismo job
    # pendiente (p.ej. un worker local corriendo en paralelo al de
    # Railway) podían procesarlo ambos -- ver
    # spec/07-investigacion-mensajes-duplicados-2026-07-07.md.
    try:
        claim = (
            supabase.table("message_jobs")
            .update(
                {
                    "status": "processing",
                    "attempts": attempts,
                    "replied_by": get_process_identity(),
                }
            )
            .eq("id", job_id)
            .eq("status", "pending")
            .execute()
        )
    except Exception as e:
        logger.error(f"[WORKER] No se pudo marcar job {job_id} como processing: {e}")
        return

    if not claim.data:
        logger.warning(f"[WORKER] Job {job_id} ya reclamado por otro proceso")
        return

    try:
        payload = job["payload"]
        tenant_id = job["tenant_id"]

        await _handle_with_tenant(tenant_id, payload)

        # Marcar como done
        supabase.table("message_jobs").update(
            {
                "status": "done",
                "processed_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", job_id).execute()

        logger.info(f"[WORKER] Job {job_id} completado (intento {attempts})")

    except Exception as e:
        logger.error(f"[WORKER] Error en job {job_id} (intento {attempts}): {e}")

        new_status = "failed" if attempts >= 3 else "pending"
        supabase.table("message_jobs").update(
            {
                "status": new_status,
                "last_error": str(e)[:500],
                "attempts": attempts,
            }
        ).eq("id", job_id).execute()

        if new_status == "failed":
            logger.error(f"[WORKER] Job {job_id} marcado como FAILED tras 3 intentos")


async def _handle_with_tenant(tenant_id: str, payload: dict):
    """Carga el tenant context y procesa el mensaje."""
    from src.core.tenant_context import TenantContextManager
    from src.services.tenant_service import load_tenant_context
    from src.core.whatsapp_handler import WhatsAppHandler

    tenant = load_tenant_context(tenant_id)
    if not tenant:
        raise ValueError(f"Tenant no encontrado: {tenant_id}")

    TenantContextManager.set_current(tenant)
    try:
        handler = WhatsAppHandler()
        handler.handle_webhook(payload)
    finally:
        TenantContextManager.clear()
