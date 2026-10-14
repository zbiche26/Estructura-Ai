# -*- coding: utf-8 -*-
"""
test_conversation_analytics.py - Tests de Métricas de Conversaciones
=====================================================================
Cubre:
  - Cálculo de totales y promedios
  - Tasa de completación y abandono
  - Agrupación por día/semana/mes
  - Horas pico
  - Distribución por plataforma
  - Casos borde (lista vacía, sin duración)

Ejecutar: pytest tests/analytics/test_conversation_analytics.py -v
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from src.services.analytics.conversation_analytics import (
    ConversationAnalytics,
    ConversationMetrics,
    PeriodMetrics,
)


# ── Helpers para crear conversaciones mock ────────────────────

def make_conv(
    status:       str      = "closed",
    message_count: int     = 5,
    duration_min:  float   = 10.0,
    platform:      str     = "whatsapp",
    created_at:    datetime = None,
) -> MagicMock:
    """Crea una conversación mock con los valores dados."""
    conv = MagicMock()
    conv.status        = MagicMock()
    conv.status.value  = status
    conv.message_count = message_count
    # duration_minutes None → el analytics intentará calcular con fechas
    # lo bloqueamos retornando None explícito
    conv.duration_minutes = duration_min
    conv.started_at    = created_at or datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
    # closed_at debe ser None real, no MagicMock
    conv.closed_at     = None
    conv.updated_at    = None
    conv.created_at    = created_at or datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
    conv.metadata      = MagicMock()
    conv.metadata.platform = platform
    return conv


def make_conv_with_dates(
    status:     str,
    started_at: datetime,
    closed_at:  datetime = None,
    messages:   int      = 3,
    platform:   str      = "whatsapp",
) -> MagicMock:
    conv = MagicMock()
    conv.status       = MagicMock()
    conv.status.value = status
    conv.message_count = messages
    conv.duration_minutes = None   # forzar cálculo manual
    conv.started_at   = started_at
    conv.created_at   = started_at
    conv.closed_at    = closed_at
    conv.updated_at   = None       # None explícito, no MagicMock
    conv.metadata     = MagicMock()
    conv.metadata.platform = platform
    return conv


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture
def analytics() -> ConversationAnalytics:
    return ConversationAnalytics()


@pytest.fixture
def conversaciones_mixtas():
    """3 completadas, 2 abandonadas, 1 activa."""
    return [
        make_conv("closed",    message_count=8,  duration_min=15.0),
        make_conv("closed",    message_count=5,  duration_min=10.0),
        make_conv("archived",  message_count=12, duration_min=20.0),
        make_conv("active",    message_count=3,  duration_min=None),
        make_conv("paused",    message_count=2,  duration_min=5.0),
        make_conv("unknown",   message_count=1,  duration_min=2.0),
    ]


@pytest.fixture
def conversaciones_por_dia():
    """Conversaciones en 3 días diferentes."""
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        make_conv_with_dates("closed", base,                          base + timedelta(minutes=10)),
        make_conv_with_dates("closed", base,                          base + timedelta(minutes=15)),
        make_conv_with_dates("closed", base + timedelta(days=1),      base + timedelta(days=1, minutes=8)),
        make_conv_with_dates("active", base + timedelta(days=2)),
        make_conv_with_dates("closed", base + timedelta(days=2),      base + timedelta(days=2, minutes=12)),
    ]


# ── Tests: ConversationMetrics ────────────────────────────────

class TestConversationMetrics:

    def test_summary_contiene_total(self):
        m = ConversationMetrics(total=10, completed=7, abandoned=3)
        assert "10" in m.summary()

    def test_summary_contiene_completion_rate(self):
        m = ConversationMetrics(total=10, completed=7, completion_rate=70.0)
        assert "70.0" in m.summary()

    def test_repr(self):
        m = ConversationMetrics(total=5, completion_rate=80.0)
        assert "5" in repr(m)


# ── Tests: lista vacía ────────────────────────────────────────

class TestListaVacia:

    def test_lista_vacia_retorna_metrics_vacio(self, analytics):
        result = analytics.calculate([])
        assert result.total == 0

    def test_lista_vacia_tasas_cero(self, analytics):
        result = analytics.calculate([])
        assert result.completion_rate  == 0.0
        assert result.abandonment_rate == 0.0

    def test_lista_vacia_promedios_cero(self, analytics):
        result = analytics.calculate([])
        assert result.avg_messages     == 0.0
        assert result.avg_duration_min == 0.0


# ── Tests: totales ────────────────────────────────────────────

class TestTotales:

    def test_total_correcto(self, analytics, conversaciones_mixtas):
        result = analytics.calculate(conversaciones_mixtas)
        assert result.total == 6

    def test_completadas_correctas(self, analytics, conversaciones_mixtas):
        result = analytics.calculate(conversaciones_mixtas)
        assert result.completed == 3  # closed + archived

    def test_activas_correctas(self, analytics, conversaciones_mixtas):
        result = analytics.calculate(conversaciones_mixtas)
        assert result.active == 1

    def test_abandonadas_correctas(self, analytics, conversaciones_mixtas):
        result = analytics.calculate(conversaciones_mixtas)
        # paused + unknown = 2
        assert result.abandoned == 2

    def test_total_mensajes(self, analytics, conversaciones_mixtas):
        result = analytics.calculate(conversaciones_mixtas)
        assert result.total_messages == 8 + 5 + 12 + 3 + 2 + 1


# ── Tests: promedios ──────────────────────────────────────────

class TestPromedios:

    def test_avg_messages_correcto(self, analytics):
        convs = [
            make_conv(message_count=4),
            make_conv(message_count=6),
        ]
        result = analytics.calculate(convs)
        assert result.avg_messages == 5.0

    def test_avg_duration_correcto(self, analytics):
        convs = [
            make_conv(duration_min=10.0),
            make_conv(duration_min=20.0),
        ]
        result = analytics.calculate(convs)
        assert result.avg_duration_min == 15.0

    def test_avg_duration_sin_duracion(self, analytics):
        convs = [make_conv(duration_min=None)]
        result = analytics.calculate(convs)
        assert result.avg_duration_min == 0.0


# ── Tests: tasas ──────────────────────────────────────────────

class TestTasas:

    def test_completion_rate_100(self, analytics):
        convs = [make_conv("closed"), make_conv("closed")]
        result = analytics.calculate(convs)
        assert result.completion_rate == 100.0

    def test_abandonment_rate_100(self, analytics):
        convs = [make_conv("paused"), make_conv("unknown")]
        result = analytics.calculate(convs)
        assert result.abandonment_rate == 100.0

    def test_tasas_suman_100(self, analytics):
        convs = [
            make_conv("closed"),
            make_conv("closed"),
            make_conv("paused"),
            make_conv("paused"),
        ]
        result = analytics.calculate(convs)
        assert abs(result.completion_rate + result.abandonment_rate - 100.0) < 0.01

    def test_activos_no_afectan_tasas(self, analytics):
        """Las conversaciones activas no cuentan para completion/abandonment."""
        convs = [
            make_conv("closed"),
            make_conv("active"),
            make_conv("active"),
        ]
        result = analytics.calculate(convs)
        assert result.completion_rate == 100.0

    def test_solo_activos_tasa_cero(self, analytics):
        convs = [make_conv("active"), make_conv("active")]
        result = analytics.calculate(convs)
        assert result.completion_rate  == 0.0
        assert result.abandonment_rate == 0.0


# ── Tests: métodos individuales ───────────────────────────────

class TestMetodosIndividuales:

    def test_abandonment_rate_directo(self, analytics):
        convs = [make_conv("closed"), make_conv("paused")]
        rate  = analytics.abandonment_rate(convs)
        assert rate == 50.0

    def test_completion_rate_directo(self, analytics):
        convs = [make_conv("closed"), make_conv("paused")]
        rate  = analytics.completion_rate(convs)
        assert rate == 50.0

    def test_avg_messages_directo(self, analytics):
        convs = [make_conv(message_count=2), make_conv(message_count=4)]
        avg   = analytics.avg_messages_per_conversation(convs)
        assert avg == 3.0

    def test_avg_duration_directo(self, analytics):
        convs = [make_conv(duration_min=5.0), make_conv(duration_min=15.0)]
        avg   = analytics.avg_duration_minutes(convs)
        assert avg == 10.0


# ── Tests: agrupación por período ────────────────────────────

class TestAgrupacionPeriodo:

    def test_by_day_retorna_lista(self, analytics, conversaciones_por_dia):
        result = analytics.by_day(conversaciones_por_dia)
        assert isinstance(result, list)

    def test_by_day_tres_dias(self, analytics, conversaciones_por_dia):
        result = analytics.by_day(conversaciones_por_dia)
        assert len(result) == 3

    def test_by_day_primer_dia_dos_convs(self, analytics, conversaciones_por_dia):
        result = analytics.by_day(conversaciones_por_dia)
        assert result[0].total == 2

    def test_by_day_ordenado_por_fecha(self, analytics, conversaciones_por_dia):
        result = analytics.by_day(conversaciones_por_dia)
        periodos = [r.period for r in result]
        assert periodos == sorted(periodos)

    def test_by_month_agrupa_mismo_mes(self, analytics):
        base = datetime(2024, 3, 1, tzinfo=timezone.utc)
        convs = [
            make_conv_with_dates("closed", base),
            make_conv_with_dates("closed", base + timedelta(days=10)),
            make_conv_with_dates("closed", base + timedelta(days=35)),  # abril
        ]
        result = analytics.by_month(convs)
        assert len(result) == 2


# ── Tests: horas pico ────────────────────────────────────────

class TestHorasPico:

    def test_peak_hours_retorna_lista(self, analytics):
        convs  = [make_conv()]
        result = analytics.peak_hours(convs)
        assert isinstance(result, list)

    def test_peak_hours_top_n(self, analytics):
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        convs = [
            make_conv(created_at=base.replace(hour=9)),
            make_conv(created_at=base.replace(hour=9)),
            make_conv(created_at=base.replace(hour=14)),
            make_conv(created_at=base.replace(hour=18)),
        ]
        result = analytics.peak_hours(convs, top_n=2)
        assert len(result) == 2
        assert result[0]["hour"] == 9   # la más frecuente


# ── Tests: plataformas ────────────────────────────────────────

class TestPlataformas:

    def test_platform_breakdown_porcentajes(self, analytics):
        convs = [
            make_conv(platform="whatsapp"),
            make_conv(platform="whatsapp"),
            make_conv(platform="web"),
        ]
        result = analytics.platform_breakdown(convs)
        assert result["whatsapp"] == pytest.approx(66.67, abs=0.1)
        assert result["web"]      == pytest.approx(33.33, abs=0.1)

    def test_platform_breakdown_vacio(self, analytics):
        result = analytics.platform_breakdown([])
        assert result == {}