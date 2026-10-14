# -*- coding: utf-8 -*-
"""
product_analytics.py - Métricas de Productos
=============================================
Calcula métricas sobre productos consultados y vendidos
por el agente Alex en cada tenant.

Métricas calculadas:
    - Top 10 productos más consultados
    - Top 10 productos más vendidos
    - Tasa de conversión (consultas → ventas)
    - Productos sin conversión
    - Revenue total y por producto
    - Ticket promedio

Uso:
    analytics = ProductAnalytics()
    metrics = analytics.calculate(messages, sales)
    print(metrics.top_viewed)
    print(metrics.conversion_rate)
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ── Value Objects ────────────────────────────────────────────


@dataclass
class ProductStat:
    """
    Estadísticas de un producto específico.

    Attributes:
        product_id:       ID del producto
        product_name:     Nombre del producto
        views:            Veces consultado
        sales:            Unidades vendidas
        revenue:          Revenue total generado
        conversion_rate:  % consultas que resultaron en venta
    """

    product_id: str
    product_name: str
    views: int = 0
    sales: int = 0
    revenue: float = 0.0
    conversion_rate: float = 0.0

    def __repr__(self) -> str:
        return (
            f"ProductStat(name='{self.product_name}', "
            f"views={self.views}, sales={self.sales}, "
            f"conv={self.conversion_rate:.1f}%)"
        )


@dataclass
class ProductMetrics:
    """
    Métricas completas de productos.

    Attributes:
        total_views:        Total de consultas de productos
        total_sales:        Total de unidades vendidas
        total_revenue:      Revenue total generado
        avg_ticket:         Ticket promedio por venta
        conversion_rate:    % global consultas → ventas
        top_viewed:         Top 10 más consultados
        top_sold:           Top 10 más vendidos
        top_revenue:        Top 10 por revenue
        no_conversion:      Productos consultados pero no vendidos
        unique_products_viewed: Productos únicos consultados
        unique_products_sold:   Productos únicos vendidos
    """

    total_views: int = 0
    total_sales: int = 0
    total_revenue: float = 0.0
    avg_ticket: float = 0.0
    conversion_rate: float = 0.0
    top_viewed: List[ProductStat] = field(default_factory=list)
    top_sold: List[ProductStat] = field(default_factory=list)
    top_revenue: List[ProductStat] = field(default_factory=list)
    no_conversion: List[ProductStat] = field(default_factory=list)
    unique_products_viewed: int = 0
    unique_products_sold: int = 0

    def summary(self) -> str:
        top = self.top_viewed[0].product_name if self.top_viewed else "ninguno"
        return (
            f"Productos: {self.unique_products_viewed} consultados | "
            f"{self.unique_products_sold} vendidos | "
            f"conv={self.conversion_rate:.1f}% | "
            f"revenue=${self.total_revenue:,.0f} | "
            f"top='{top}'"
        )

    def __repr__(self) -> str:
        return (
            f"ProductMetrics("
            f"views={self.total_views}, "
            f"sales={self.total_sales}, "
            f"conv={self.conversion_rate:.1f}%)"
        )


# ── Analizador principal ─────────────────────────────────────


class ProductAnalytics:
    """
    Calcula métricas de productos consultados y vendidos.

    Fuentes de datos:
        - messages: Mensajes del agente con metadata de producto visto
        - sales:    Objetos Sale/SaleItem con productos vendidos

    Uso:
        analytics = ProductAnalytics()
        metrics   = analytics.calculate(messages, sales)

        # Top 5 más consultados
        for p in metrics.top_viewed[:5]:
            print(f"{p.product_name}: {p.views} consultas")

        # Productos sin conversión
        for p in metrics.no_conversion:
            print(f"{p.product_name}: {p.views} consultas, 0 ventas")
    """

    def __init__(self, top_n: int = 10) -> None:
        """
        Args:
            top_n: Número de productos en los rankings (default: 10).
        """
        self._top_n = top_n

    # ── API pública ──────────────────────────────────────────

    def calculate(
        self,
        messages: List[Any],
        sales: List[Any],
    ) -> ProductMetrics:
        """
        Calcula métricas completas de productos.

        Args:
            messages: Lista de mensajes con metadata de producto visto.
            sales:    Lista de objetos Sale o SaleItem.

        Returns:
            ProductMetrics con todas las métricas.
        """
        metrics = ProductMetrics()

        # ── Acumular vistas desde mensajes ───────────────────
        view_counts: Counter = Counter()
        view_names: Dict[str, str] = {}

        for msg in messages:
            product_id, product_name = self._extract_product_view(msg)
            if product_id:
                view_counts[product_id] += 1
                if product_name:
                    view_names[product_id] = product_name

        # ── Acumular ventas desde sales ──────────────────────
        sale_counts: Counter = Counter()
        sale_revenue: Dict[str, float] = defaultdict(float)
        sale_names: Dict[str, str] = {}
        total_revenue = 0.0
        total_sales_n = 0

        for sale in sales:
            items = self._extract_sale_items(sale)
            for item in items:
                pid = item.get("product_id")
                pname = item.get("product_name", "")
                qty = item.get("quantity", 1)
                rev = item.get("revenue", 0.0)

                if pid:
                    sale_counts[pid] += qty
                    sale_revenue[pid] += rev
                    total_revenue += rev
                    total_sales_n += qty
                    if pname:
                        sale_names[pid] = pname

        # ── Construir ProductStat por producto ───────────────
        all_product_ids = set(view_counts.keys()) | set(sale_counts.keys())
        stats: Dict[str, ProductStat] = {}

        for pid in all_product_ids:
            views = view_counts.get(pid, 0)
            sold = sale_counts.get(pid, 0)
            revenue = sale_revenue.get(pid, 0.0)
            name = view_names.get(pid) or sale_names.get(pid) or pid

            conv = 0.0
            if views > 0 and sold > 0:
                conv = round(min((sold / views) * 100, 100.0), 2)

            stats[pid] = ProductStat(
                product_id=pid,
                product_name=name,
                views=views,
                sales=sold,
                revenue=round(revenue, 2),
                conversion_rate=conv,
            )

        # ── Llenar métricas ──────────────────────────────────
        metrics.total_views = sum(view_counts.values())
        metrics.total_sales = total_sales_n
        metrics.total_revenue = round(total_revenue, 2)
        metrics.unique_products_viewed = len(view_counts)
        metrics.unique_products_sold = len(sale_counts)

        # Ticket promedio
        sale_count_n = len(sales)
        if sale_count_n > 0 and total_revenue > 0:
            metrics.avg_ticket = round(total_revenue / sale_count_n, 2)

        # Conversión global
        if metrics.total_views > 0 and metrics.total_sales > 0:
            metrics.conversion_rate = round(
                min((metrics.total_sales / metrics.total_views) * 100, 100.0), 2
            )

        # Rankings
        all_stats = list(stats.values())

        metrics.top_viewed = sorted(all_stats, key=lambda s: s.views, reverse=True)[
            : self._top_n
        ]

        metrics.top_sold = sorted(
            [s for s in all_stats if s.sales > 0],
            key=lambda s: s.sales,
            reverse=True,
        )[: self._top_n]

        metrics.top_revenue = sorted(
            [s for s in all_stats if s.revenue > 0],
            key=lambda s: s.revenue,
            reverse=True,
        )[: self._top_n]

        metrics.no_conversion = [s for s in all_stats if s.views > 0 and s.sales == 0]

        return metrics

    def top_viewed(
        self,
        messages: List[Any],
        sales: List[Any],
        n: int = 10,
    ) -> List[ProductStat]:
        """Top N productos más consultados."""
        return self.calculate(messages, sales).top_viewed[:n]

    def top_sold(
        self,
        messages: List[Any],
        sales: List[Any],
        n: int = 10,
    ) -> List[ProductStat]:
        """Top N productos más vendidos."""
        return self.calculate(messages, sales).top_sold[:n]

    def conversion_rate(
        self,
        messages: List[Any],
        sales: List[Any],
    ) -> float:
        """Tasa de conversión global (%)."""
        return self.calculate(messages, sales).conversion_rate

    def no_conversion_products(
        self,
        messages: List[Any],
        sales: List[Any],
    ) -> List[ProductStat]:
        """Productos consultados pero sin ninguna venta."""
        return self.calculate(messages, sales).no_conversion

    # ── Helpers ──────────────────────────────────────────────

    def _extract_product_view(
        self,
        msg: Any,
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Extrae product_id y product_name de un mensaje.

        Busca en:
          1. msg.metadata["product_id"] / msg.metadata["product_name"]
          2. msg.metadata["product"]["id"] / msg.metadata["product"]["name"]
        """
        metadata = getattr(msg, "metadata", None)

        if isinstance(metadata, dict):
            # Formato plano
            pid = metadata.get("product_id")
            pname = metadata.get("product_name")

            # Formato anidado
            if not pid and "product" in metadata:
                prod = metadata["product"]
                if isinstance(prod, dict):
                    pid = prod.get("id")
                    pname = prod.get("name")

            if pid:
                return str(pid), pname

        return None, None

    def _extract_sale_items(
        self,
        sale: Any,
    ) -> List[Dict]:
        """
        Extrae items de una venta.

        Soporta:
          - sale.items (lista de SaleItem)
          - sale directo con product_id, quantity, total
        """
        items = getattr(sale, "items", None)

        if items:
            result = []
            for item in items:
                pid = str(getattr(item, "product_id", "") or "")
                pname = str(getattr(item, "product_name", "") or "")
                qty = int(getattr(item, "quantity", 1) or 1)
                rev = float(getattr(item, "total", 0) or 0)

                if pid:
                    result.append(
                        {
                            "product_id": pid,
                            "product_name": pname,
                            "quantity": qty,
                            "revenue": rev,
                        }
                    )
            return result

        # Sale sin items — tratar como item único
        pid = str(getattr(sale, "product_id", "") or "")
        if pid:
            return [
                {
                    "product_id": pid,
                    "product_name": str(getattr(sale, "product_name", "") or ""),
                    "quantity": int(getattr(sale, "quantity", 1) or 1),
                    "revenue": float(getattr(sale, "total", 0) or 0),
                }
            ]

        return []
