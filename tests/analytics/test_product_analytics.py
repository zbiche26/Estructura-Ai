# -*- coding: utf-8 -*-
"""
test_product_analytics.py - Tests de Métricas de Productos
===========================================================
Ejecutar: pytest tests/analytics/test_product_analytics.py -v
"""

import pytest
from unittest.mock import MagicMock

from src.services.analytics.product_analytics import (
    ProductAnalytics,
    ProductMetrics,
    ProductStat,
)


# ── Helpers ───────────────────────────────────────────────────


def make_msg_view(product_id: str, product_name: str = "") -> MagicMock:
    """Mensaje con vista de producto en metadata."""
    msg = MagicMock()
    msg.metadata = {
        "product_id": product_id,
        "product_name": product_name or f"Producto {product_id}",
    }
    return msg


def make_sale(items: list) -> MagicMock:
    """Venta con lista de items."""
    sale = MagicMock()
    sale.items = []
    sale.product_id = None

    total_rev = 0.0
    for pid, pname, qty, price in items:
        item = MagicMock()
        item.product_id = pid
        item.product_name = pname
        item.quantity = qty
        item.total = qty * price
        total_rev += qty * price
        sale.items.append(item)

    sale.total = total_rev
    return sale


def make_sale_simple(
    product_id: str,
    product_name: str = "",
    quantity: int = 1,
    price: float = 100.0,
) -> MagicMock:
    """Venta simple sin items (producto único)."""
    sale = MagicMock()
    sale.items = None
    sale.product_id = product_id
    sale.product_name = product_name or f"Producto {product_id}"
    sale.quantity = quantity
    sale.total = quantity * price
    return sale


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def analytics() -> ProductAnalytics:
    return ProductAnalytics(top_n=10)


@pytest.fixture
def mensajes_vistas():
    """5 vistas: 3 del producto A, 2 del B."""
    return [
        make_msg_view("prod-a", "Camara Domo"),
        make_msg_view("prod-a", "Camara Domo"),
        make_msg_view("prod-a", "Camara Domo"),
        make_msg_view("prod-b", "Camara Bullet"),
        make_msg_view("prod-b", "Camara Bullet"),
    ]


@pytest.fixture
def ventas_simples():
    """2 ventas del producto A, 1 del B."""
    return [
        make_sale([("prod-a", "Camara Domo", 2, 180_000)]),
        make_sale([("prod-a", "Camara Domo", 1, 180_000)]),
        make_sale([("prod-b", "Camara Bullet", 1, 320_000)]),
    ]


# ── Tests: ProductStat ────────────────────────────────────────


class TestProductStat:

    def test_repr_contiene_nombre(self):
        s = ProductStat("p1", "Camara Domo", views=5, sales=2)
        assert "Camara Domo" in repr(s)

    def test_repr_contiene_views(self):
        s = ProductStat("p1", "Camara Domo", views=5)
        assert "5" in repr(s)


# ── Tests: ProductMetrics ─────────────────────────────────────


class TestProductMetrics:

    def test_summary_contiene_revenue(self):
        m = ProductMetrics(
            total_revenue=950_000,
            top_viewed=[ProductStat("p1", "Kit DVR")],
        )
        assert "950" in m.summary()

    def test_summary_contiene_top(self):
        m = ProductMetrics(top_viewed=[ProductStat("p1", "Kit DVR")])
        assert "Kit DVR" in m.summary()


# ── Tests: lista vacía ────────────────────────────────────────


class TestListaVacia:

    def test_sin_datos_retorna_metrics_vacio(self, analytics):
        result = analytics.calculate([], [])
        assert result.total_views == 0
        assert result.total_sales == 0
        assert result.total_revenue == 0.0

    def test_sin_ventas_conversion_cero(self, analytics, mensajes_vistas):
        result = analytics.calculate(mensajes_vistas, [])
        assert result.conversion_rate == 0.0

    def test_sin_mensajes_top_viewed_vacio(self, analytics, ventas_simples):
        """Sin mensajes, top_viewed no tiene productos con vistas."""
        result = analytics.calculate([], ventas_simples)
        # top_viewed puede incluir productos del catálogo aunque no tengan vistas
        # Lo importante es que ninguno tenga views > 0
        assert all(s.views == 0 for s in result.top_viewed)


# ── Tests: vistas ─────────────────────────────────────────────


class TestVistas:

    def test_total_views_correcto(self, analytics, mensajes_vistas, ventas_simples):
        result = analytics.calculate(mensajes_vistas, ventas_simples)
        assert result.total_views == 5

    def test_unique_products_viewed(self, analytics, mensajes_vistas, ventas_simples):
        result = analytics.calculate(mensajes_vistas, ventas_simples)
        assert result.unique_products_viewed == 2

    def test_top_viewed_primer_producto(
        self, analytics, mensajes_vistas, ventas_simples
    ):
        result = analytics.calculate(mensajes_vistas, ventas_simples)
        assert result.top_viewed[0].product_id == "prod-a"
        assert result.top_viewed[0].views == 3

    def test_top_viewed_ordenado_desc(self, analytics, mensajes_vistas, ventas_simples):
        result = analytics.calculate(mensajes_vistas, ventas_simples)
        views = [s.views for s in result.top_viewed]
        assert views == sorted(views, reverse=True)


# ── Tests: ventas ─────────────────────────────────────────────


class TestVentas:

    def test_total_sales_correcto(self, analytics, mensajes_vistas, ventas_simples):
        result = analytics.calculate(mensajes_vistas, ventas_simples)
        # 2 + 1 + 1 = 4 unidades
        assert result.total_sales == 4

    def test_unique_products_sold(self, analytics, mensajes_vistas, ventas_simples):
        result = analytics.calculate(mensajes_vistas, ventas_simples)
        assert result.unique_products_sold == 2

    def test_top_sold_primer_producto(self, analytics, mensajes_vistas, ventas_simples):
        result = analytics.calculate(mensajes_vistas, ventas_simples)
        assert result.top_sold[0].product_id == "prod-a"

    def test_top_sold_solo_con_ventas(self, analytics, mensajes_vistas):
        """Top sold no incluye productos sin ventas."""
        result = analytics.calculate(mensajes_vistas, [])
        assert result.top_sold == []


# ── Tests: revenue ────────────────────────────────────────────


class TestRevenue:

    def test_total_revenue_correcto(self, analytics, mensajes_vistas, ventas_simples):
        result = analytics.calculate(mensajes_vistas, ventas_simples)
        # (2*180k) + (1*180k) + (1*320k) = 860k
        assert result.total_revenue == pytest.approx(860_000, abs=1)

    def test_avg_ticket_correcto(self, analytics, mensajes_vistas, ventas_simples):
        result = analytics.calculate(mensajes_vistas, ventas_simples)
        # 860k / 3 ventas = 286.666...
        assert result.avg_ticket == pytest.approx(860_000 / 3, abs=1)

    def test_top_revenue_ordenado(self, analytics, mensajes_vistas, ventas_simples):
        result = analytics.calculate(mensajes_vistas, ventas_simples)
        revs = [s.revenue for s in result.top_revenue]
        assert revs == sorted(revs, reverse=True)


# ── Tests: conversión ─────────────────────────────────────────


class TestConversion:

    def test_conversion_rate_correcto(self, analytics, mensajes_vistas, ventas_simples):
        result = analytics.calculate(mensajes_vistas, ventas_simples)
        # 4 ventas / 5 vistas * 100 = 80%
        assert result.conversion_rate == pytest.approx(80.0, abs=0.1)

    def test_no_conversion_productos(self, analytics):
        """Producto visto pero no vendido aparece en no_conversion."""
        msgs = [make_msg_view("prod-c", "Camara PTZ")]
        sales = []
        result = analytics.calculate(msgs, sales)
        assert len(result.no_conversion) == 1
        assert result.no_conversion[0].product_id == "prod-c"

    def test_producto_vendido_no_en_no_conversion(
        self, analytics, mensajes_vistas, ventas_simples
    ):
        result = analytics.calculate(mensajes_vistas, ventas_simples)
        no_conv_ids = [s.product_id for s in result.no_conversion]
        assert "prod-a" not in no_conv_ids
        assert "prod-b" not in no_conv_ids

    def test_conversion_no_supera_100(self, analytics):
        """Si hay más ventas que vistas, conversión tope en 100%."""
        msgs = [make_msg_view("prod-a")]
        sales = [make_sale([("prod-a", "X", 5, 100)])]
        result = analytics.calculate(msgs, sales)
        assert result.conversion_rate <= 100.0


# ── Tests: métodos individuales ───────────────────────────────


class TestMetodosIndividuales:

    def test_top_viewed_directo(self, analytics, mensajes_vistas, ventas_simples):
        result = analytics.top_viewed(mensajes_vistas, ventas_simples, n=1)
        assert len(result) == 1
        assert result[0].product_id == "prod-a"

    def test_top_sold_directo(self, analytics, mensajes_vistas, ventas_simples):
        result = analytics.top_sold(mensajes_vistas, ventas_simples, n=1)
        assert len(result) == 1

    def test_conversion_rate_directo(self, analytics, mensajes_vistas, ventas_simples):
        rate = analytics.conversion_rate(mensajes_vistas, ventas_simples)
        assert rate > 0.0

    def test_no_conversion_directo(self, analytics):
        msgs = [make_msg_view("prod-z", "Sin ventas")]
        result = analytics.no_conversion_products(msgs, [])
        assert len(result) == 1


# ── Tests: extracción de datos ────────────────────────────────


class TestExtraccion:

    def test_extrae_product_id_de_metadata(self, analytics):
        msg = MagicMock()
        msg.metadata = {"product_id": "abc123", "product_name": "Test"}
        pid, pname = analytics._extract_product_view(msg)
        assert pid == "abc123"
        assert pname == "Test"

    def test_extrae_product_anidado(self, analytics):
        msg = MagicMock()
        msg.metadata = {"product": {"id": "nested-id", "name": "Nested"}}
        pid, pname = analytics._extract_product_view(msg)
        assert pid == "nested-id"
        assert pname == "Nested"

    def test_sin_product_retorna_none(self, analytics):
        msg = MagicMock()
        msg.metadata = {}
        pid, pname = analytics._extract_product_view(msg)
        assert pid is None

    def test_extrae_items_de_sale(self, analytics):
        sale = make_sale([("p1", "Prod 1", 2, 100.0)])
        items = analytics._extract_sale_items(sale)
        assert len(items) == 1
        assert items[0]["product_id"] == "p1"
        assert items[0]["quantity"] == 2

    def test_sale_simple_sin_items(self, analytics):
        sale = make_sale_simple("p2", "Prod 2", 3, 50.0)
        items = analytics._extract_sale_items(sale)
        assert len(items) == 1
        assert items[0]["product_id"] == "p2"
        assert items[0]["quantity"] == 3
