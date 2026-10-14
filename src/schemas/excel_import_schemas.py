from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ImportErrorEntry(BaseModel):
    """Detalle de un error en una fila específica del archivo importado."""

    row: int
    product: str
    error: str


class ProductImportResult(BaseModel):
    """Producto importado correctamente con información relevante."""

    name: str
    sku: str


class ExcelImportSummary(BaseModel):
    """Resumen de un proceso de importación de productos."""

    id: str
    filename: str
    uploaded_at: datetime
    status: str
    total_products: int
    successful: int
    failed: int


class ExcelImportListResponse(BaseModel):
    """Respuesta paginada para el historial de importaciones."""

    imports: List[ExcelImportSummary]
    total: int
    page: int
    limit: int


class ExcelImportDetailResponse(ExcelImportSummary):
    """Detalle extendido de una importación, listo para multi-tenant."""

    tenant_id: str
    initiated_by: Optional[str] = None
    progress: int = Field(default=0, ge=0, le=100, description="Progreso 0-100")
    processed_at: Optional[datetime] = None
    processing_time_seconds: Optional[int] = None
    successful_products: List[ProductImportResult] = Field(default_factory=list)
    errors_detail: List[ImportErrorEntry] = Field(default_factory=list)
    log: Optional[str] = None
