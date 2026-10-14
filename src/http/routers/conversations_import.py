# -*- coding: utf-8 -*-
"""
conversations_import.py - Import de historial de conversaciones
================================================================
Endpoints para importar historial de WhatsApp al sistema.

Endpoints:
    POST /conversations/import           - Iniciar importación (async)
    GET  /conversations/import/{job_id}  - Consultar progreso

Formatos soportados:
    - .zip  — Exportación nativa de WhatsApp Business
    - .csv  — CSV personalizado con columnas: date, phone, sender, message

CSV esperado:
    date,phone,sender,message
    2024-01-15 10:30:00,+573001234567,user,Hola buenas
    2024-01-15 10:30:05,+573001234567,assistant,Bienvenido!

ZIP WhatsApp (exportación nativa):
    El ZIP contiene un archivo .txt con el formato:
    [15/01/2024, 10:30:00] +573001234567: Hola buenas
"""

from __future__ import annotations

import asyncio
import csv
import io
import re
import zipfile
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from pydantic import BaseModel

from src.core.database import get_db
from src.core.logger import logger
from src.http.deps import CurrentUser, get_current_user, get_tenant_id

router = APIRouter(prefix="/conversations", tags=["Conversations"])

# ── Límites ───────────────────────────────────────────────────────────────────
MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
ALLOWED_EXTENSIONS = {".zip", ".csv"}

# ── Jobs en memoria (para dev — en prod usar Redis o tabla BD) ────────────────
_import_jobs: Dict[str, dict] = {}


# ── Dependency ────────────────────────────────────────────────────────────────


def current_user_dep(
    tenant_id: str = Depends(get_tenant_id),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> CurrentUser:
    return get_current_user(tenant_id=tenant_id, authorization=authorization)


# ── Schemas ───────────────────────────────────────────────────────────────────


class ImportJobStarted(BaseModel):
    job_id: str
    status: str = "pending"
    message: str


class ImportError(BaseModel):
    row: Optional[int]
    phone: Optional[str]
    reason: str


class ImportJobStatus(BaseModel):
    job_id: str
    status: str  # pending | processing | completed | failed
    progress_pct: int = 0
    imported_count: int = 0
    failed_count: int = 0
    errors: List[ImportError] = []
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


# ── Parsers ───────────────────────────────────────────────────────────────────


def _parse_csv(content: bytes) -> List[dict]:
    """
    Parsea CSV con columnas: date, phone, sender, message
    Retorna lista de filas parseadas.
    """
    rows = []
    text = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))

    required = {"date", "phone", "sender", "message"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        raise ValueError(
            f"CSV inválido. Columnas requeridas: {required}. "
            f"Columnas encontradas: {set(reader.fieldnames or [])}"
        )

    for i, row in enumerate(reader, start=2):
        rows.append(
            {
                "row_number": i,
                "date": row.get("date", "").strip(),
                "phone": row.get("phone", "").strip(),
                "sender": row.get("sender", "").strip().lower(),
                "message": row.get("message", "").strip(),
            }
        )

    return rows


def _parse_whatsapp_zip(content: bytes) -> List[dict]:
    """
    Parsea exportación nativa de WhatsApp (.zip con .txt).
    Formato: [DD/MM/YYYY, HH:MM:SS] PHONE: message
    """
    rows = []

    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        txt_files = [f for f in zf.namelist() if f.endswith(".txt")]
        if not txt_files:
            raise ValueError(
                "El ZIP no contiene archivos .txt de exportación de WhatsApp"
            )

        for txt_file in txt_files:
            with zf.open(txt_file) as f:
                text = f.read().decode("utf-8", errors="replace")

            # Patrón: [DD/MM/YYYY, HH:MM:SS] SENDER: message
            pattern = re.compile(
                r"\[(\d{1,2}/\d{1,2}/\d{4}),\s*(\d{1,2}:\d{2}:\d{2})\]\s*([^:]+):\s*(.*)"
            )

            for i, line in enumerate(text.splitlines(), start=1):
                match = pattern.match(line.strip())
                if not match:
                    continue

                date_str, time_str, sender, message = match.groups()
                phone = sender.strip()
                # Detectar si es el agente (asistente) o usuario
                sender_role = (
                    "assistant"
                    if any(
                        x in phone.lower() for x in ["bot", "agente", "sistema", "ai"]
                    )
                    else "user"
                )

                rows.append(
                    {
                        "row_number": i,
                        "date": f"{date_str} {time_str}",
                        "phone": phone,
                        "sender": sender_role,
                        "message": message.strip(),
                    }
                )

    return rows


# ── Procesador async ──────────────────────────────────────────────────────────


async def _process_import(
    job_id: str,
    tenant_id: str,
    rows: List[dict],
) -> None:
    """
    Procesa las filas de importación en background.
    Crea conversaciones y mensajes en Supabase.
    """
    job = _import_jobs[job_id]
    job["status"] = "processing"
    job["started_at"] = datetime.now(timezone.utc).isoformat()

    db = get_db()
    imported = 0
    failed = 0
    errors = []

    # Agrupar filas por teléfono
    conversations: Dict[str, List[dict]] = {}
    for row in rows:
        phone = row.get("phone", "").strip()
        if not phone:
            failed += 1
            errors.append(
                {
                    "row": row.get("row_number"),
                    "phone": None,
                    "reason": "Teléfono vacío",
                }
            )
            continue
        if phone not in conversations:
            conversations[phone] = []
        conversations[phone].append(row)

    total = len(rows)
    processed = 0

    for phone, msgs in conversations.items():
        try:
            # Buscar o crear conversación
            existing = (
                db.client.table("conversations")
                .select("id")
                .eq("tenant_id", tenant_id)
                .eq("phone", phone)
                .limit(1)
                .execute()
            )

            if existing.data:
                conv_id = existing.data[0]["id"]
            else:
                now = datetime.now(timezone.utc).isoformat()
                created = (
                    db.client.table("conversations")
                    .insert(
                        {
                            "tenant_id": tenant_id,
                            "phone": phone,
                            "status": "archived",
                            "context": {},
                            "metadata": {"imported": True},
                            "started_at": now,
                            "last_message_at": now,
                            "created_at": now,
                            "updated_at": now,
                        }
                    )
                    .execute()
                )
                conv_id = created.data[0]["id"] if created.data else None

            if not conv_id:
                raise ValueError("No se pudo crear la conversación")

            # Insertar mensajes en batch
            message_rows = []
            for msg in msgs:
                message_rows.append(
                    {
                        "tenant_id": tenant_id,
                        "conversation_id": conv_id,
                        "sender": msg.get("sender", "user"),
                        "content": msg.get("message", ""),
                        "message_type": "text",
                        "metadata": {
                            "imported": True,
                            "original_date": msg.get("date"),
                        },
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                )

            if message_rows:
                db.client.table("messages").insert(message_rows).execute()

            imported += len(msgs)

        except Exception as e:
            failed += len(msgs)
            errors.append(
                {
                    "row": None,
                    "phone": phone,
                    "reason": str(e),
                }
            )
            logger.error(f"[IMPORT] Error procesando {phone}: {e}")

        processed += len(msgs)
        job["progress_pct"] = int((processed / total) * 100) if total > 0 else 100
        job["imported_count"] = imported
        job["failed_count"] = failed
        job["errors"] = errors

        # Yield para no bloquear el event loop
        await asyncio.sleep(0)

    job["status"] = "completed"
    job["progress_pct"] = 100
    job["completed_at"] = datetime.now(timezone.utc).isoformat()

    logger.info(
        f"[IMPORT] job={job_id} tenant={tenant_id} "
        f"imported={imported} failed={failed}"
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/import",
    response_model=ImportJobStarted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Importar historial de conversaciones",
    description=(
        "Importa historial de conversaciones desde un archivo .zip (exportación nativa "
        "de WhatsApp) o .csv personalizado. El procesamiento es asíncrono — retorna un "
        "job_id que puede usarse para consultar el progreso."
    ),
)
async def import_conversations(
    file: UploadFile = File(..., description="Archivo .zip o .csv con el historial"),
    current_user: CurrentUser = Depends(current_user_dep),
) -> ImportJobStarted:
    tenant_id = current_user.tenant.id

    # Validar extensión
    filename = file.filename or ""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Formato no soportado. Usa .zip o .csv. Recibido: '{ext or filename}'",
        )

    # Leer contenido
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Archivo demasiado grande. Máximo {MAX_FILE_SIZE_MB}MB.",
        )

    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El archivo está vacío",
        )

    # Parsear
    try:
        if ext == ".csv":
            rows = _parse_csv(content)
        else:
            rows = _parse_whatsapp_zip(content)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"[IMPORT] Error parseando archivo: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Error al leer el archivo: {str(e)}",
        )

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El archivo no contiene filas válidas",
        )

    # Crear job
    job_id = str(uuid4())
    _import_jobs[job_id] = {
        "job_id": job_id,
        "tenant_id": tenant_id,
        "status": "pending",
        "progress_pct": 0,
        "imported_count": 0,
        "failed_count": 0,
        "errors": [],
        "started_at": None,
        "completed_at": None,
    }

    # Lanzar proceso en background
    asyncio.create_task(_process_import(job_id, tenant_id, rows))

    logger.info(
        f"[IMPORT] Job iniciado: job={job_id} tenant={tenant_id} "
        f"rows={len(rows)} format={ext}"
    )

    return ImportJobStarted(
        job_id=job_id,
        status="pending",
        message=f"Importación iniciada. {len(rows)} filas encontradas. Usa job_id para consultar el progreso.",
    )


@router.get(
    "/import/{job_id}",
    response_model=ImportJobStatus,
    summary="Consultar progreso de importación",
    description="Retorna el estado actual del job de importación.",
)
def get_import_status(
    job_id: str,
    current_user: CurrentUser = Depends(current_user_dep),
) -> ImportJobStatus:
    tenant_id = current_user.tenant.id

    job = _import_jobs.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' no encontrado",
        )

    # Verificar que el job pertenece al tenant
    if job.get("tenant_id") != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este job",
        )

    return ImportJobStatus(
        job_id=job["job_id"],
        status=job["status"],
        progress_pct=job["progress_pct"],
        imported_count=job["imported_count"],
        failed_count=job["failed_count"],
        errors=[ImportError(**e) for e in job["errors"]],
        started_at=job.get("started_at"),
        completed_at=job.get("completed_at"),
    )
