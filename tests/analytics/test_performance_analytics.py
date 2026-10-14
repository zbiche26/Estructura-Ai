# -*- coding: utf-8 -*-
"""
test_performance_analytics.py - Tests de Métricas de Rendimiento
=================================================================
Ejecutar: pytest tests/analytics/test_performance_analytics.py -v
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from src.services.analytics.performance_analytics import (
    PerformanceAnalytics,
    PerformanceMetrics,
    EndpointStat,
)


# ── Helpers ───────────────────────────────────────────────────


def make_event(
    success: bool = True,
    response_ms: float = 500.0,
    endpoint: str = "/webhook/whatsapp",
    status_code: int = 200,
    error_type: str = "",
    event_type: str = "request",
    created_at: datetime = None,
) -> MagicMock:
    event = MagicMock()
    event.success = success
    event.response_ms = response_ms
    event.endpoint = endpoint
    event.status_code = status_code
    event.error_type = error_type
    event.type = event_type
    event.created_at = created_at or datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
    return event


def make_error(
    error_type: str = "timeout",
    response_ms: float = 5000.0,
    endpoint: str = "/webhook/whatsapp",
    created_at: datetime = None,
) -> MagicMock:
    return make_event(
        success=False,
        response_ms=response_ms,
        endpoint=endpoint,
        status_code=500,
        error_type=error_type,
        event_type="error",
        created_at=created_at,
    )


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def analytics() -> PerformanceAnalytics:
    return PerformanceAnalytics(slow_threshold_ms=3000.0, top_n_endpoints=5)


@pytest.fixture
def eventos_mixtos():
    """7 exitosos, 3 errores."""
    return [
        make_event(success=True, response_ms=200),
        make_event(success=True, response_ms=300),
        make_event(success=True, response_ms=500),
        make_event(success=True, response_ms=800),
        make_event(success=True, response_ms=1000),
        make_event(success=True, response_ms=1500),
        make_event(success=True, response_ms=2000),
        make_error(error_type="timeout", response_ms=5000),
        make_error(error_type="llm_error", response_ms=3500),
        make_error(error_type="timeout", response_ms=4000),
    ]


# ── Tests: EndpointStat ───────────────────────────────────────


class TestEndpointStat:

    def test_repr_contiene_endpoint(self):
        s = EndpointStat(endpoint="/api/chat", calls=10, avg_ms=300)
        assert "/api/chat" in repr(s)

    def test_repr_contiene_calls(self):
        s = EndpointStat(endpoint="/api", calls=42, avg_ms=100)
        assert "42" in repr(s)


# ── Tests: PerformanceMetrics ─────────────────────────────────


class TestPerformanceMetrics:

    def test_summary_contiene_requests(self):
        m = PerformanceMetrics(
            total_requests=100, success_rate=95.0, avg_response_ms=300
        )
        assert "100" in m.summary()

    def test_summary_contiene_success_rate(self):
        m = PerformanceMetrics(total_requests=10, success_rate=90.0)
        assert "90.0" in m.summary()

    def test_repr(self):
        m = PerformanceMetrics(total_requests=50, success_rate=80.0)
        assert "50" in repr(m)


# ── Tests: lista vacía ────────────────────────────────────────


class TestListaVacia:

    def test_vacio_retorna_metrics_default(self, analytics):
        result = analytics.calculate([])
        assert result.total_requests == 0

    def test_vacio_success_rate_cero(self, analytics):
        result = analytics.calculate([])
        assert result.success_rate == 0.0

    def test_vacio_uptime_100(self, analytics):
        """Sin datos, uptime por defecto es 100%."""
        result = analytics.calculate([])
        assert result.uptime_pct == 100.0

    def test_vacio_sin_endpoints(self, analytics):
        result = analytics.calculate([])
        assert result.slowest_endpoints == []


# ── Tests: contadores ─────────────────────────────────────────


class TestContadores:

    def test_total_requests(self, analytics, eventos_mixtos):
        result = analytics.calculate(eventos_mixtos)
        assert result.total_requests == 10

    def test_successful_correcto(self, analytics, eventos_mixtos):
        result = analytics.calculate(eventos_mixtos)
        assert result.successful == 7

    def test_failed_correcto(self, analytics, eventos_mixtos):
        result = analytics.calculate(eventos_mixtos)
        assert result.failed == 3

    def test_total_errors(self, analytics, eventos_mixtos):
        result = analytics.calculate(eventos_mixtos)
        assert result.total_errors == 3

    def test_success_rate_correcto(self, analytics, eventos_mixtos):
        result = analytics.calculate(eventos_mixtos)
        assert result.success_rate == 70.0

    def test_error_rate_correcto(self, analytics, eventos_mixtos):
        result = analytics.calculate(eventos_mixtos)
        assert result.error_rate == 30.0

    def test_tasas_suman_100(self, analytics, eventos_mixtos):
        result = analytics.calculate(eventos_mixtos)
        assert abs(result.success_rate + result.error_rate - 100.0) < 0.01


# ── Tests: tiempos de respuesta ───────────────────────────────


class TestTiemposRespuesta:

    def test_avg_response_ms(self, analytics):
        events = [
            make_event(response_ms=100),
            make_event(response_ms=300),
        ]
        result = analytics.calculate(events)
        assert result.avg_response_ms == pytest.approx(200.0, abs=0.1)

    def test_max_response_ms(self, analytics):
        events = [
            make_event(response_ms=100),
            make_event(response_ms=5000),
            make_event(response_ms=300),
        ]
        result = analytics.calculate(events)
        assert result.max_response_ms == 5000.0

    def test_min_response_ms(self, analytics):
        events = [
            make_event(response_ms=100),
            make_event(response_ms=500),
        ]
        result = analytics.calculate(events)
        assert result.min_response_ms == 100.0

    def test_p95_con_suficientes_datos(self, analytics):
        """P95 con 20 eventos."""
        events = [make_event(response_ms=float(i * 100)) for i in range(1, 21)]
        result = analytics.calculate(events)
        # P95 de [100,200,...,2000] → índice 18 → 1900ms
        assert result.p95_response_ms >= 1800.0

    def test_sin_response_ms_no_falla(self, analytics):
        event = make_event(response_ms=None)
        result = analytics.calculate([event])
        assert result.avg_response_ms == 0.0


# ── Tests: errores por tipo ───────────────────────────────────


class TestErroresPorTipo:

    def test_errores_por_tipo_correcto(self, analytics, eventos_mixtos):
        result = analytics.calculate(eventos_mixtos)
        assert result.errors_by_type.get("timeout", 0) == 2
        assert result.errors_by_type.get("llm_error", 0) == 1

    def test_sin_errores_dict_vacio(self, analytics):
        events = [make_event(success=True) for _ in range(5)]
        result = analytics.calculate(events)
        assert result.errors_by_type == {}

    def test_errores_por_tipo_directo(self, analytics, eventos_mixtos):
        result = analytics.errors_by_type(eventos_mixtos)
        assert "timeout" in result


# ── Tests: endpoints ──────────────────────────────────────────


class TestEndpoints:

    def test_slowest_endpoints_retorna_lista(self, analytics):
        events = [
            make_event(endpoint="/api/chat", response_ms=200),
            make_event(endpoint="/webhook", response_ms=500),
            make_event(endpoint="/api/products", response_ms=1000),
        ]
        result = analytics.calculate(events)
        assert len(result.slowest_endpoints) == 3

    def test_slowest_ordenado_por_avg_ms(self, analytics):
        events = [
            make_event(endpoint="/fast", response_ms=100),
            make_event(endpoint="/slow", response_ms=2000),
            make_event(endpoint="/medium", response_ms=500),
        ]
        result = analytics.calculate(events)
        avgs = [s.avg_ms for s in result.slowest_endpoints]
        assert avgs == sorted(avgs, reverse=True)

    def test_endpoint_error_rate(self, analytics):
        events = [
            make_event(endpoint="/api", success=True, response_ms=200),
            make_event(endpoint="/api", success=True, response_ms=300),
            make_error(endpoint="/api", response_ms=500),
        ]
        result = analytics.calculate(events)
        ep = result.slowest_endpoints[0]
        assert ep.endpoint == "/api"
        assert ep.calls == 3
        assert ep.error_count == 1
        assert ep.error_rate == pytest.approx(33.33, abs=0.1)

    def test_top_n_endpoints_respetado(self):
        analytics = PerformanceAnalytics(top_n_endpoints=2)
        events = [
            make_event(endpoint="/a", response_ms=100),
            make_event(endpoint="/b", response_ms=200),
            make_event(endpoint="/c", response_ms=300),
        ]
        result = analytics.calculate(events)
        assert len(result.slowest_endpoints) == 2

    def test_slowest_directo(self, analytics):
        events = [make_event(endpoint="/test", response_ms=500)]
        result = analytics.slowest_endpoints(events, n=1)
        assert len(result) == 1


# ── Tests: uptime ─────────────────────────────────────────────


class TestUptime:

    def test_uptime_100_todos_exitosos(self, analytics):
        events = [make_event(success=True) for _ in range(10)]
        result = analytics.calculate(events)
        assert result.uptime_pct == 100.0

    def test_uptime_basado_en_success_rate(self, analytics):
        events = [
            make_event(success=True),
            make_event(success=True),
            make_error(),
            make_error(),
        ]
        result = analytics.calculate(events)
        assert result.uptime_pct == 50.0


# ── Tests: métodos individuales ───────────────────────────────


class TestMetodosIndividuales:

    def test_success_rate_directo(self, analytics, eventos_mixtos):
        rate = analytics.success_rate(eventos_mixtos)
        assert rate == 70.0

    def test_avg_response_ms_directo(self, analytics):
        events = [make_event(response_ms=400), make_event(response_ms=600)]
        avg = analytics.avg_response_ms(events)
        assert avg == pytest.approx(500.0, abs=0.1)

    def test_error_count_directo(self, analytics, eventos_mixtos):
        count = analytics.error_count(eventos_mixtos)
        assert count == 3


# ── Tests: agrupación por día ─────────────────────────────────


class TestAgrupacionDia:

    def test_by_day_retorna_lista(self, analytics):
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        events = [
            make_event(created_at=base),
            make_event(created_at=base + timedelta(days=1)),
        ]
        result = analytics.by_day(events)
        assert len(result) == 2

    def test_by_day_contiene_campos(self, analytics):
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        events = [make_event(created_at=base)]
        result = analytics.by_day(events)
        assert "date" in result[0]
        assert "requests" in result[0]
        assert "success_rate" in result[0]
        assert "avg_ms" in result[0]

    def test_by_day_ordenado(self, analytics):
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        events = [
            make_event(created_at=base + timedelta(days=2)),
            make_event(created_at=base),
            make_event(created_at=base + timedelta(days=1)),
        ]
        result = analytics.by_day(events)
        fechas = [r["date"] for r in result]
        assert fechas == sorted(fechas)
