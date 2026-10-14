import base64
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from io import StringIO
from typing import Any, Dict, List

from src.repositories.sale_repository import SaleRepository
from src.models import SaleStatus
from src.core.database import SupabaseClient
from src.core.logger import logger


def _filter_sales_by_tenant(sales: List[Any], tenant_id: str) -> List[Any]:
    return [s for s in sales if str(getattr(s, "tenant_id", "")) == str(tenant_id)]


def _compute_buckets_daily(sales: List[Any]) -> List[Dict[str, Any]]:
    buckets: Dict[str, Dict[str, Any]] = {}
    for sale in sales:
        day_key = sale.created_at.date().isoformat()
        if day_key not in buckets:
            buckets[day_key] = {"total_sales": 0, "total_revenue": Decimal("0")}
        buckets[day_key]["total_sales"] += 1
        buckets[day_key]["total_revenue"] += Decimal(str(sale.total))
    return [
        {"bucket_date": k, "total_sales": v["total_sales"], "total_revenue": v["total_revenue"]}
        for k, v in sorted(buckets.items())
    ]


def _build_csv_from_buckets(period: str, buckets: List[Dict[str, Any]]) -> str:
    output = StringIO()
    if period == "weekly":
        output.write("date,total_sales,total_revenue\n")
        for b in buckets:
            output.write(f"{b['bucket_date']},{b['total_sales']},{b['total_revenue']}\n")
    else:
        output.write("day,total_sales,total_revenue\n")
        for b in buckets:
            output.write(f"{b['day']},{b['total_sales']},{b['total_revenue']}\n")
    return output.getvalue()


def get_weekly_report(*, tenant_id: str, db: SupabaseClient) -> Dict[str, Any]:
    repo = SaleRepository(client=db.client)
    today = date.today()
    start_date = today - timedelta(days=6)
    sales = repo.get_sales_by_date_range(
        start_date,
        today,
        tenant_id=tenant_id,
        status=SaleStatus.COMPLETED.value,
    )
    sales = _filter_sales_by_tenant(sales, tenant_id)

    total_sales = len(sales)
    total_revenue = sum(Decimal(str(s.total)) for s in sales)
    avg_sale = total_revenue / total_sales if total_sales else Decimal("0")
    buckets = _compute_buckets_daily(sales)

    return {
        "tenant_id": tenant_id,
        "start_date": start_date,
        "end_date": today,
        "total_sales": total_sales,
        "total_revenue": total_revenue,
        "average_sale": avg_sale,
        "buckets": buckets,
        "calculated_at": datetime.now(timezone.utc),
    }


def get_monthly_report(*, tenant_id: str, year: int = None, month: int = None, db: SupabaseClient) -> Dict[str, Any]:
    repo = SaleRepository(client=db.client)
    if not year or not month:
        today = date.today()
        year = today.year
        month = today.month

    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(year, month + 1, 1) - timedelta(days=1)

    sales = repo.get_sales_by_date_range(
        start_date,
        end_date,
        tenant_id=tenant_id,
        status=SaleStatus.COMPLETED.value,
    )
    sales = _filter_sales_by_tenant(sales, tenant_id)

    total_sales = len(sales)
    total_revenue = sum(Decimal(str(s.total)) for s in sales)
    avg_sale = total_revenue / total_sales if total_sales else Decimal("0")
    unique_customers = len(set(s.customer_phone for s in sales))

    daily_totals: Dict[int, Dict[str, Any]] = {}
    for sale in sales:
        day = sale.created_at.day
        if day not in daily_totals:
            daily_totals[day] = {"total_sales": 0, "total_revenue": Decimal("0")}
        daily_totals[day]["total_sales"] += 1
        daily_totals[day]["total_revenue"] += Decimal(str(sale.total))

    best_day = None
    best_day_revenue = None
    if daily_totals:
        best = max(daily_totals.items(), key=lambda x: x[1]["total_revenue"])
        best_day = f"{year}-{month:02d}-{best[0]:02d}"
        best_day_revenue = best[1]["total_revenue"]

    buckets = [
        {"day": day, "total_sales": data["total_sales"], "total_revenue": data["total_revenue"]}
        for day, data in sorted(daily_totals.items())
    ]

    return {
        "tenant_id": tenant_id,
        "year": year,
        "month": month,
        "total_sales": total_sales,
        "total_revenue": total_revenue,
        "average_sale": avg_sale,
        "unique_customers": unique_customers,
        "best_day": best_day,
        "best_day_revenue": best_day_revenue,
        "buckets": buckets,
        "calculated_at": datetime.now(timezone.utc),
    }


def export_report(*, tenant_id: str, period: str, fmt: str, db: SupabaseClient) -> Dict[str, Any]:
    period = period.lower()
    fmt = fmt.lower()
    if period not in {"weekly", "monthly"}:
        raise ValueError("period debe ser weekly o monthly")
    if fmt not in {"csv", "pdf"}:
        raise ValueError("format debe ser csv o pdf")

    if period == "weekly":
        report = get_weekly_report(tenant_id=tenant_id, db=db)
        buckets = report["buckets"]
    else:
        report = get_monthly_report(tenant_id=tenant_id, db=db)
        buckets = report["buckets"]

    if fmt == "csv":
        csv_data = _build_csv_from_buckets(period, buckets)
        content = base64.b64encode(csv_data.encode()).decode()
    else:
        # Placeholder simple PDF content
        pdf_bytes = f"PDF report for {period} {report['calculated_at']}".encode()
        content = base64.b64encode(pdf_bytes).decode()

    return {
        "tenant_id": tenant_id,
        "period": period,
        "format": fmt,
        "content": content,
        "calculated_at": datetime.now(timezone.utc),
    }
