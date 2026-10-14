from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Header,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, JSONResponse

from src.core.database import get_db
from src.core.logger import logger
from ..deps import CurrentUser, get_current_user, get_tenant_id
from src.schemas.excel_import_schemas import (
    ExcelImportDetailResponse,
    ExcelImportListResponse,
    ExcelImportSummary,
)
from src.services.excel_import_service import (
    process_excel_upload,
    get_job_status,
    get_jobs_by_tenant,
)

ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}
ALLOWED_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "text/csv",
}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
IMPORT_STATUSES = {"processing", "completed", "failed"}
MAX_PAGE_SIZE = 100
TEMPLATE_RELATIVE_PATH = "../../../docs/productos_template.xlsx"

router = APIRouter(prefix="/plugins/excel", tags=["Excel Import"])


def current_user_dep(
    tenant_id: str = Depends(get_tenant_id),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> CurrentUser:
    return get_current_user(tenant_id=tenant_id, authorization=authorization)


@router.post(
    "/upload", summary="Subir archivo Excel o CSV", status_code=status.HTTP_202_ACCEPTED
)
async def upload_excel(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current: CurrentUser = Depends(current_user_dep),
    db=Depends(get_db),
) -> Any:
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_file_type",
                "message": "Solo se permiten archivos Excel o CSV",
            },
        )

    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_mime_type", "message": "Tipo MIME no permitido"},
        )

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"error": "file_too_large", "message": "El archivo excede 10MB"},
        )

    await file.seek(0)

    import_id = f"import-{uuid.uuid4()}"
    tenant_id = str(current.tenant.id)
    tenant_slug = (
        current.tenant.get_config("slug", "")
        if hasattr(current.tenant, "get_config")
        else ""
    )

    # ✅ Procesa en background y guarda estado real en excel_import_jobs
    background_tasks.add_task(
        process_excel_upload,
        contents=contents,
        tenant_id=tenant_id,
        tenant_slug=tenant_slug,
        import_id=import_id,
        filename=file.filename or "",
    )

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "import_id": import_id,
            "status": "pending",
            "message": "Archivo recibido. Procesando productos en segundo plano.",
        },
    )


@router.get("/template", summary="Descargar template Excel")
def download_template():
    template_path = os.path.join(os.path.dirname(__file__), TEMPLATE_RELATIVE_PATH)
    if not os.path.isfile(template_path):
        raise HTTPException(
            status_code=404, detail="Template no encontrado en el servidor"
        )
    return FileResponse(
        path=template_path,
        filename="productos_template.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=productos_template.xlsx"},
    )


@router.get(
    "/imports",
    summary="Historial de importaciones de Excel",
    response_model=ExcelImportListResponse,
)
def list_excel_imports(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=MAX_PAGE_SIZE),
    status: Optional[str] = Query(default=None),
    current: CurrentUser = Depends(current_user_dep),
):
    if status and status not in IMPORT_STATUSES:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_status",
                "message": "Use processing, completed o failed.",
            },
        )

    tenant_id = str(current.tenant.id)
    offset = (page - 1) * limit

    # ✅ Datos reales desde excel_import_jobs
    jobs = get_jobs_by_tenant(
        tenant_id=tenant_id, limit=limit, offset=offset, status_filter=status
    )

    imports = []
    for job in jobs:
        try:
            uploaded_at = (
                datetime.fromisoformat(job["created_at"])
                if job.get("created_at")
                else datetime.now(timezone.utc)
            )
            imports.append(
                ExcelImportSummary(
                    id=job["id"],
                    filename=job.get("filename") or "archivo.xlsx",
                    uploaded_at=uploaded_at,
                    status=job.get("status", "processing"),
                    total_products=job.get("total", 0),
                    successful=job.get("exitosos", 0),
                    failed=job.get("fallidos", 0),
                )
            )
        except Exception:
            continue

    return ExcelImportListResponse(
        imports=imports, total=len(imports), page=page, limit=limit
    )


@router.get(
    "/imports/{import_id}",
    summary="Detalle de una importación de Excel",
    response_model=ExcelImportDetailResponse,
)
def get_excel_import_detail(
    import_id: str,
    current: CurrentUser = Depends(current_user_dep),
    db=Depends(get_db),
):
    tenant_id = str(current.tenant.id)

    # ✅ Datos reales desde excel_import_jobs
    job = get_job_status(import_id=import_id, tenant_id=tenant_id)

    if not job:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "import_not_found",
                "message": "Importación no encontrada.",
            },
        )

    uploaded_at = (
        datetime.fromisoformat(job["created_at"])
        if job.get("created_at")
        else datetime.now(timezone.utc)
    )
    processed_at = (
        datetime.fromisoformat(job["updated_at"])
        if job.get("updated_at") and job.get("status") != "processing"
        else None
    )

    log = (
        f"Modo: {job.get('modo', 'desconocido')} — {job.get('exitosos', 0)} productos cargados exitosamente"
        if job.get("status") == "completed"
        else job.get("error") or "Procesando..."
    )

    return ExcelImportDetailResponse(
        id=job["id"],
        filename=job.get("filename") or "archivo.xlsx",
        uploaded_at=uploaded_at,
        status=job.get("status", "processing"),
        total_products=job.get("total", 0),
        successful=job.get("exitosos", 0),
        failed=job.get("fallidos", 0),
        tenant_id=tenant_id,
        initiated_by=getattr(current.tenant, "email", ""),
        processed_at=processed_at,
        processing_time_seconds=None,
        successful_products=[],
        errors_detail=[],
        log=log,
    )
