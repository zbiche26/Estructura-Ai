from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from ..deps import CurrentUser, get_current_user, get_tenant_id
from src.schemas.inventory_schemas import (
    InventoryAlert,
    InventoryAlertLevel,
    InventoryAlertsResponse,
    InventoryProductStock,
    InventoryStockResponse,
    StockAdjustRequest,
    StockAdjustResponse,
    StockHistoryResponse,
    StockMovementEntry,
)

router = APIRouter(prefix="/plugins/inventory", tags=["Inventory"])


def current_user_dep(
    tenant_id: str = Depends(get_tenant_id),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> CurrentUser:
    """Aísla el tenant real antes de resolver al usuario."""
    return get_current_user(tenant_id=tenant_id, authorization=authorization)


# ==================== DATA MOCKS ====================

def _base_products(tenant_id: str) -> List[InventoryProductStock]:
    # Fecha fija para mocks; facilita tests y respuestas determinísticas
    base_time = datetime(2024, 3, 6, tzinfo=timezone.utc)
    products = [
        {
            "product_id": "prod-001",
            "name": "Silla Ergonómica",
            "sku": "SLL-ERG-001",
            "stock": 0,
            "min_stock": 20,
        },
        {
            "product_id": "prod-002",
            "name": "Escritorio Elevable",
            "sku": "ESC-ELV-002",
            "stock": 8,
            "min_stock": 15,
        },
        {
            "product_id": "prod-003",
            "name": "Monitor 27''",
            "sku": "MON-27-003",
            "stock": 2,
            "min_stock": 10,
        },
        {
            "product_id": "prod-004",
            "name": "Kit Teclado + Mouse",
            "sku": "KIT-TM-004",
            "stock": 120,
            "min_stock": 40,
        },
    ]
    return [
        InventoryProductStock(
            updated_at=base_time - timedelta(minutes=idx * 5),
            **payload,
        )
        for idx, payload in enumerate(products)
    ]


def _mock_alerts(tenant_id: str) -> List[InventoryAlert]:
    alerts = []
    for product in _base_products(tenant_id):
        if product.stock <= product.min_stock:
            if product.stock == 0:
                level = InventoryAlertLevel.urgent
                message = "Producto agotado. Urge reabastecer."
                recommended = product.min_stock * 3
            elif product.stock <= product.min_stock // 2:
                level = InventoryAlertLevel.critical
                message = "Stock crítico. Planifica reorden inmediato."
                recommended = product.min_stock * 2
            else:
                level = InventoryAlertLevel.warning
                message = "Stock bajo. Considera reorden."
                recommended = product.min_stock
            alerts.append(
                InventoryAlert(
                    product_id=product.product_id,
                    product_name=product.name,
                    level=level,
                    current_stock=product.stock,
                    min_stock=product.min_stock,
                    recommended_order=recommended,
                    message=message,
                    created_at=product.updated_at,
                )
            )
    return alerts


def _mock_movements(tenant_id: str) -> List[StockMovementEntry]:
    base_time = datetime.now(timezone.utc) - timedelta(days=2)
    movements: List[StockMovementEntry] = []
    for idx, product in enumerate(_base_products(tenant_id)):
        for shift in range(3):
            change = (-5 + shift * 3)
            movements.append(
                StockMovementEntry(
                    movement_id=f"mov-{product.product_id}-{idx}-{shift}",
                    product_id=product.product_id,
                    product_name=product.name,
                    change=change,
                    balance_after=max(product.stock + change, 0),
                    reason="Ajuste automático" if change < 0 else "Recepción",
                    performed_by="system@estructura.ai",
                    occurred_at=base_time + timedelta(hours=idx * 3 + shift),
                )
            )
    movements.sort(key=lambda m: m.occurred_at, reverse=True)
    return movements


# ==================== ENDPOINTS ====================


@router.get(
    "/stock",
    response_model=InventoryStockResponse,
    summary="Ver stock de productos",
)
def get_inventory_stock(
    low_stock_only: bool = Query(False, description="Solo productos con stock <= mínimo"),
    search: Optional[str] = Query(None, description="Filtra por nombre o SKU"),
    current: CurrentUser = Depends(current_user_dep),
) -> InventoryStockResponse:
    """Devuelve stock actual del tenant autenticado."""
    items = _base_products(current.tenant.id)
    if low_stock_only:
        items = [p for p in items if p.stock <= p.min_stock]
    if search:
        needle = search.lower()
        items = [
            p for p in items
            if needle in p.name.lower() or needle in p.sku.lower()
        ]
    return InventoryStockResponse(items=items, total=len(items))


@router.post(
    "/adjust",
    response_model=StockAdjustResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ajustar stock manualmente",
)
def adjust_inventory_stock(
    payload: StockAdjustRequest,
    current: CurrentUser = Depends(current_user_dep),
) -> StockAdjustResponse:
    """Permite ajustes manuales controlados."""
    products = _base_products(current.tenant.id)
    product = next((p for p in products if p.product_id == payload.product_id), None)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "product_not_found", "message": "Producto inexistente"},
        )
    if payload.adjustment == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "no_op", "message": "El ajuste debe ser distinto de cero"},
        )

    stock_before = product.stock
    stock_after = stock_before + payload.adjustment
    if stock_after < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "insufficient_stock",
                "message": "El ajuste dejaría el stock en negativo",
            },
        )

    # TODO: Persistir ajuste en repositorio de inventario
    return StockAdjustResponse(
        product_id=payload.product_id,
        stock_before=stock_before,
        stock_after=stock_after,
        movement_id=f"mov-{uuid.uuid4()}",
        applied_by=current.user.email,
        processed_at=datetime.now(timezone.utc),
    )


@router.get(
    "/alerts",
    response_model=InventoryAlertsResponse,
    summary="Alertas de stock",
)
def list_inventory_alerts(
    level: Optional[InventoryAlertLevel] = Query(None, description="Filtrar por nivel"),
    current: CurrentUser = Depends(current_user_dep),
) -> InventoryAlertsResponse:
    alerts = _mock_alerts(current.tenant.id)
    if level:
        alerts = [a for a in alerts if a.level == level]
    return InventoryAlertsResponse(alerts=alerts, total=len(alerts))


@router.get(
    "/history",
    response_model=StockHistoryResponse,
    summary="Historial de movimientos",
)
def list_inventory_history(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    product_id: Optional[str] = Query(None, description="Filtra por producto"),
    current: CurrentUser = Depends(current_user_dep),
) -> StockHistoryResponse:
    movements = _mock_movements(current.tenant.id)
    if product_id:
        movements = [m for m in movements if m.product_id == product_id]
    start = (page - 1) * limit
    slice_ = movements[start:start + limit]
    next_page = page + 1 if start + limit < len(movements) else None
    return StockHistoryResponse(
        items=slice_,
        total=len(movements),
        page=page,
        limit=limit,
        next_page=next_page,
    )
