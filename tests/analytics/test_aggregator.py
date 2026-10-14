# -*- coding: utf-8 -*-
"""
test_aggregator.py - Tests del MetricsAggregator
=================================================
Ejecutar: pytest tests/analytics/test_aggregator.py -v
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.services.analytics.aggregator import (
    MetricsAggregator,
    AggregatedMetrics,
)


# ── Helpers ───────────────────────────────────────────────────


def make_daily(
    period: str = "2024-01-15",
    tenant_id: str = "tenant_a",
    total_conversations: int = 10,
    completed_conv: int = 7,
    abandoned_conv: int = 3,
    avg_messages: float = 5.0,
    avg_duration_min: float = 12.0,
    completion_rate: float = 70.0,
    top_intent: str = "greeting",
    unique_intents: int = 4,
    intent_coverage: float = 85.0,
    avg_confidence: float = 0.85,
    total_views: int = 20,
    total_sales: int = 5,
    total_revenue: float = 900_000.0,
    conversion_rate: float = 25.0,
    top_product: str = "Camara Domo",
    total_requests: int = 100,
    success_rate: float = 95.0,
    avg_response_ms: float = 400.0,
    total_errors: int = 5,
) -> AggregatedMetrics:
    return AggregatedMetrics(
        period=period,
        period_type="day",
        tenant_id=tenant_id,
        total_conversations=total_conversations,
        completed_conv=completed_conv,
        abandoned_conv=abandoned_conv,
        avg_messages=avg_messages,
        avg_duration_min=avg_duration_min,
        completion_rate=completion_rate,
        top_intent=top_intent,
        unique_intents=unique_intents,
        intent_coverage=intent_coverage,
        avg_confidence=avg_confidence,
        total_views=total_views,
        total_sales=total_sales,
        total_revenue=total_revenue,
        conversion_rate=conversion_rate,
        top_product=top_product,
        total_requests=total_requests,
        success_rate=success_rate,
        avg_response_ms=avg_response_ms,
        total_errors=total_errors,
    )


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def aggregator() -> MetricsAggregator:
    return MetricsAggregator()


@pytest.fixture
def tres_dias():
    return [
        make_daily(
            "2024-01-01",
            total_conversations=10,
            total_revenue=300_000,
            success_rate=90.0,
            top_intent="greeting",
            top_product="Domo",
        ),
        make_daily(
            "2024-01-02",
            total_conversations=15,
            total_revenue=500_000,
            success_rate=95.0,
            top_intent="greeting",
            top_product="Domo",
        ),
        make_daily(
            "2024-01-03",
            total_conversations=5,
            total_revenue=200_000,
            success_rate=80.0,
            top_intent="purchase",
            top_product="Kit",
        ),
    ]


# ── Tests: AggregatedMetrics ──────────────────────────────────


class TestAggregatedMetrics:

    def test_to_dict_retorna_dict(self):
        m = make_daily()
        d = m.to_dict()
        assert isinstance(d, dict)

    def test_to_dict_tiene_secciones(self):
        m = make_daily()
        d = m.to_dict()
        assert "conversations" in d
        assert "intents" in d
        assert "products" in d
        assert "performance" in d

    def test_to_dict_values_correctos(self):
        m = make_daily(total_conversations=42)
        d = m.to_dict()
        assert d["conversations"]["total"] == 42

    def test_summary_contiene_period(self):
        m = make_daily(period="2024-01-15")
        assert "2024-01-15" in m.summary()

    def test_summary_contiene_revenue(self):
        m = make_daily(total_revenue=900_000)
        assert "900" in m.summary()

    def test_repr_contiene_period(self):
        m = make_daily(period="2024-01-15")
        assert "2024-01-15" in repr(m)


# ── Tests: aggregate_daily con datos vacíos ───────────────────


class TestAggregateDaily:

    def test_daily_vacio_retorna_metrics(self, aggregator):
        result = aggregator.aggregate_daily([], [], [], [], "2024-01-15", "t1")
        assert isinstance(result, AggregatedMetrics)
        assert result.period == "2024-01-15"
        assert result.period_type == "day"
        assert result.tenant_id == "t1"

    def test_daily_vacio_zeros(self, aggregator):
        result = aggregator.aggregate_daily([], [], [], [], "2024-01-15")
        assert result.total_conversations == 0
        assert result.total_revenue == 0.0
        assert result.total_requests == 0

    def test_daily_tiene_generated_at(self, aggregator):
        result = aggregator.aggregate_daily([], [], [], [])
        assert result.generated_at != ""

    def test_daily_period_type_es_day(self, aggregator):
        result = aggregator.aggregate_daily([], [], [], [], "2024-01-15")
        assert result.period_type == "day"


# ── Tests: aggregate_weekly ───────────────────────────────────


class TestAggregateWeekly:

    def test_weekly_suma_conversaciones(self, aggregator, tres_dias):
        result = aggregator.aggregate_weekly(tres_dias, "2024-W01", "tenant_a")
        assert result.total_conversations == 10 + 15 + 5

    def test_weekly_suma_revenue(self, aggregator, tres_dias):
        result = aggregator.aggregate_weekly(tres_dias, "2024-W01", "tenant_a")
        assert result.total_revenue == pytest.approx(1_000_000.0, abs=1)

    def test_weekly_promedia_success_rate(self, aggregator, tres_dias):
        result = aggregator.aggregate_weekly(tres_dias, "2024-W01", "tenant_a")
        expected = (90.0 + 95.0 + 80.0) / 3
        assert result.success_rate == pytest.approx(expected, abs=0.1)

    def test_weekly_period_type(self, aggregator, tres_dias):
        result = aggregator.aggregate_weekly(tres_dias, "2024-W01")
        assert result.period_type == "week"

    def test_weekly_top_intent_mas_frecuente(self, aggregator, tres_dias):
        result = aggregator.aggregate_weekly(tres_dias)
        # "greeting" aparece 2 veces vs "purchase" 1 vez
        assert result.top_intent == "greeting"

    def test_weekly_top_product_mas_frecuente(self, aggregator, tres_dias):
        result = aggregator.aggregate_weekly(tres_dias)
        # "Domo" aparece 2 veces vs "Kit" 1 vez
        assert result.top_product == "Domo"

    def test_weekly_suma_errores(self, aggregator, tres_dias):
        result = aggregator.aggregate_weekly(tres_dias)
        assert result.total_errors == sum(d.total_errors for d in tres_dias)

    def test_weekly_vacio_retorna_default(self, aggregator):
        result = aggregator.aggregate_weekly([], "2024-W01", "t1")
        assert result.total_conversations == 0
        assert result.period_type == "week"


# ── Tests: aggregate_monthly ──────────────────────────────────


class TestAggregateMonthly:

    def test_monthly_suma_conversaciones(self, aggregator, tres_dias):
        result = aggregator.aggregate_monthly(tres_dias, "2024-01", "tenant_a")
        assert result.total_conversations == 30

    def test_monthly_suma_revenue(self, aggregator, tres_dias):
        result = aggregator.aggregate_monthly(tres_dias, "2024-01")
        assert result.total_revenue == pytest.approx(1_000_000.0, abs=1)

    def test_monthly_period_type(self, aggregator, tres_dias):
        result = aggregator.aggregate_monthly(tres_dias, "2024-01")
        assert result.period_type == "month"

    def test_monthly_vacio(self, aggregator):
        result = aggregator.aggregate_monthly([], "2024-01")
        assert result.total_conversations == 0

    def test_monthly_max_unique_intents(self, aggregator):
        dias = [
            make_daily(unique_intents=3),
            make_daily(unique_intents=7),
            make_daily(unique_intents=5),
        ]
        result = aggregator.aggregate_monthly(dias, "2024-01")
        assert result.unique_intents == 7


# ── Tests: inferencia de período ──────────────────────────────


class TestInferPeriod:

    def test_infer_week_desde_dia(self, aggregator):
        dias = [make_daily("2024-01-15")]
        result = aggregator.aggregate_weekly(dias)
        assert "W" in result.period

    def test_infer_month_desde_dia(self, aggregator):
        dias = [make_daily("2024-01-15")]
        result = aggregator.aggregate_monthly(dias)
        assert result.period == "2024-01"

    def test_period_explicito_respetado(self, aggregator, tres_dias):
        result = aggregator.aggregate_weekly(tres_dias, "2024-W99")
        assert result.period == "2024-W99"


# ── Tests: aggregate_range ────────────────────────────────────


class TestAggregateRange:

    def test_range_retorna_metrics(self, aggregator):
        result = aggregator.aggregate_range(
            [], [], [], [], period="2024-Q1", period_type="custom", tenant_id="t1"
        )
        assert result.period_type == "custom"
        assert result.period == "2024-Q1"
        assert result.tenant_id == "t1"
