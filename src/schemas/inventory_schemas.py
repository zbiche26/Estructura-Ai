from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, constr


class InventoryAlertLevel(str, Enum):
    info = "info"
    warning = "warning"
    critical = "critical"
    urgent = "urgent"


class InventoryProductStock(BaseModel):
    product_id: str
    name: str
    sku: constr(strip_whitespace=True, min_length=1)
    stock: int = Field(ge=0)
    min_stock: int = Field(ge=0)
    updated_at: datetime


class InventoryStockResponse(BaseModel):
    items: List[InventoryProductStock]
    total: int


class StockAdjustRequest(BaseModel):
    product_id: str
    adjustment: int = Field(gt=-1000, lt=1000)
    reason: constr(strip_whitespace=True, min_length=3)


class StockAdjustResponse(BaseModel):
    product_id: str
    stock_before: int
    stock_after: int
    movement_id: str
    applied_by: str
    processed_at: datetime


class InventoryAlert(BaseModel):
    product_id: str
    product_name: str
    level: InventoryAlertLevel
    current_stock: int
    min_stock: int
    recommended_order: int
    message: str
    created_at: datetime


class InventoryAlertsResponse(BaseModel):
    alerts: List[InventoryAlert]
    total: int


class StockMovementEntry(BaseModel):
    movement_id: str
    product_id: str
    product_name: str
    change: int
    balance_after: int
    reason: str
    performed_by: str
    occurred_at: datetime


class StockHistoryResponse(BaseModel):
    items: List[StockMovementEntry]
    total: int
    page: int
    limit: int
    next_page: Optional[int] = None
