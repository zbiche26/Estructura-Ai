from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
import io
import base64

from src.http.deps import CurrentUser, get_current_user, get_tenant_id
from src.core.database import get_db
from src.http.schemas.report_schemas import (
    WeeklyReportResponse,
    MonthlyReportResponse,
    ExportReportResponse,
)
from src.services.report_service import (
    get_weekly_report,
    get_monthly_report,
    export_report,
)
from src.core.logger import logger


def current_user_dep(
    tenant_id: str = Depends(get_tenant_id),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> CurrentUser:
    return get_current_user(tenant_id=tenant_id, authorization=authorization)


router = APIRouter(prefix="/reports", tags=["Reports"])

##este endpoint es de prueba para la descarga del archibo seleccionado, no hace parte de las tareas de la semana 
@router.get("/export/download", summary="Descargar reporte en CSV o PDF")
def export_report_download(
    period: str = Query(..., pattern="^(weekly|monthly)$", description="Periodo a exportar"),
    format: str = Query(..., pattern="^(csv|pdf)$", description="Formato de exportación"),
    current_user: CurrentUser = Depends(current_user_dep),
    db=Depends(get_db),
):
    report = export_report(
        tenant_id=current_user.tenant.id,
        period=period,
        fmt=format,
        db=db,
    )
    filename = f"report_{period}_{format}_{report['calculated_at'].date()}.{format}"
    file_bytes = base64.b64decode(report["content"])
    if format == "csv":
        return StreamingResponse(
            io.BytesIO(file_bytes),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    else:
        return StreamingResponse(
            io.BytesIO(file_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )


@router.get(
    "/weekly",
    response_model=WeeklyReportResponse,
    summary="Reporte semanal de ventas",
)
def weekly_report(
    current_user: CurrentUser = Depends(current_user_dep),
    db=Depends(get_db),
):
    try:
        return get_weekly_report(tenant_id=current_user.tenant.id, db=db)
    except Exception as exc:
        logger.error(f"/reports/weekly failed: {exc}")
        raise HTTPException(status_code=500, detail="Error interno en reporte semanal") from exc


@router.get(
    "/monthly",
    response_model=MonthlyReportResponse,
    summary="Reporte mensual de ventas",
)
def monthly_report(
    year: Optional[int] = Query(None, ge=2000, le=2100),
    month: Optional[int] = Query(None, ge=1, le=12),
    current_user: CurrentUser = Depends(current_user_dep),
    db=Depends(get_db),
):
    try:
        return get_monthly_report(tenant_id=current_user.tenant.id, year=year, month=month, db=db)
    except Exception as exc:
        logger.error(f"/reports/monthly failed: {exc}")
        raise HTTPException(status_code=500, detail="Error interno en reporte mensual") from exc


@router.get(
    "/export",
    response_model=ExportReportResponse,
    summary="Exportar reporte en PDF o CSV",
)
def export_report_endpoint(
    period: str = Query(..., pattern="^(weekly|monthly)$", description="Periodo a exportar"),
    format: str = Query(..., pattern="^(csv|pdf)$", description="Formato de exportación"),
    current_user: CurrentUser = Depends(current_user_dep),
    db=Depends(get_db),
):
    try:
        return export_report(
            tenant_id=current_user.tenant.id,
            period=period,
            fmt=format,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error(f"/reports/export failed: {exc}")
        raise HTTPException(status_code=500, detail="Error interno en exportación") from exc
