# -*- coding: utf-8 -*-
"""
test_intent_analytics.py - Tests de Métricas de Intents
=========================================================
Ejecutar: pytest tests/analytics/test_intent_analytics.py -v
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from src.services.analytics.intent_analytics import (
    IntentAnalytics,
    IntentMetrics,
    IntentStat,
)


# ── Helpers ───────────────────────────────────────────────────

def make_msg(
    intent:     str   = "greeting",
    confidence: float = 0.9,
    created_at: datetime = None,
) -> MagicMock:
    msg = MagicMock()
    msg.metadata   = {"intent": intent, "confidence": confidence}
    msg.created_at = created_at or datetime(2024, 1, 15, tzinfo=timezone.utc)
    msg.strategy_used = None
    return msg


def make_msg_sin_intent(created_at: datetime = None) -> MagicMock:
    msg = MagicMock()
    msg.metadata   = {}
    msg.created_at = created_at or datetime(2024, 1, 15, tzinfo=timezone.utc)
    msg.strategy_used = None
    msg.intent     = None
    msg.confidence = None
    return msg


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def analytics() -> IntentAnalytics:
    return IntentAnalytics(low_confidence_threshold=0.6)


@pytest.fixture
def mensajes_mixtos():
    return [
        make_msg("greeting",  0.95),
        make_msg("greeting",  0.90),
        make_msg("purchase",  0.85),
        make_msg("inquiry",   0.40),  # baja confianza
        make_msg("inquiry",   0.45),  # baja confianza
        make_msg("farewell",  0.80),
        make_msg_sin_intent(),         # sin intent
    ]


# ── Tests: IntentStat ─────────────────────────────────────────

class TestIntentStat:

    def test_repr_contiene_intent(self):
        s = IntentStat(intent="greeting", count=5, avg_confidence=0.9)
        assert "greeting" in repr(s)

    def test_repr_contiene_count(self):
        s = IntentStat(intent="greeting", count=5)
        assert "5" in repr(s)


# ── Tests: IntentMetrics ──────────────────────────────────────

class TestIntentMetrics:

    def test_coverage_rate_cien(self):
        m = IntentMetrics(total_messages=3, messages_with_intent=3)
        assert m.coverage_rate == 100.0

    def test_coverage_rate_parcial(self):
        m = IntentMetrics(total_messages=4, messages_with_intent=2)
        assert m.coverage_rate == 50.0

    def test_coverage_rate_cero(self):
        m = IntentMetrics(total_messages=0)
        assert m.coverage_rate == 0.0

    def test_summary_contiene_unique(self):
        m = IntentMetrics(
            unique_intents=3,
            top_intents=[IntentStat("greeting", 5)],
            avg_confidence_global=0.85,
        )
        assert "3" in m.summary()


# ── Tests: lista vacía ────────────────────────────────────────

class TestListaVacia:

    def test_vacio_retorna_metrics_default(self, analytics):
        result = analytics.calculate([])
        assert result.total_messages == 0
        assert result.unique_intents == 0

    def test_vacio_top_intents_vacio(self, analytics):
        result = analytics.calculate([])
        assert result.top_intents == []

    def test_vacio_coverage_cero(self, analytics):
        result = analytics.calculate([])
        assert result.coverage_rate == 0.0


# ── Tests: cálculos generales ─────────────────────────────────

class TestCalculosGenerales:

    def test_total_messages_correcto(self, analytics, mensajes_mixtos):
        result = analytics.calculate(mensajes_mixtos)
        assert result.total_messages == 7

    def test_messages_with_intent(self, analytics, mensajes_mixtos):
        result = analytics.calculate(mensajes_mixtos)
        assert result.messages_with_intent == 6

    def test_unique_intents(self, analytics, mensajes_mixtos):
        result = analytics.calculate(mensajes_mixtos)
        assert result.unique_intents == 4

    def test_top_intent_es_greeting(self, analytics, mensajes_mixtos):
        result = analytics.calculate(mensajes_mixtos)
        assert result.top_intents[0].intent == "greeting"

    def test_top_intents_ordenados_por_frecuencia(self, analytics, mensajes_mixtos):
        result = analytics.calculate(mensajes_mixtos)
        counts = [s.count for s in result.top_intents]
        assert counts == sorted(counts, reverse=True)

    def test_distribution_suma_100(self, analytics, mensajes_mixtos):
        result  = analytics.calculate(mensajes_mixtos)
        total   = sum(result.distribution.values())
        assert abs(total - 100.0) < 0.1


# ── Tests: confianza ──────────────────────────────────────────

class TestConfianza:

    def test_avg_confidence_correcto(self, analytics):
        msgs = [
            make_msg("greeting", 0.8),
            make_msg("greeting", 0.6),
        ]
        result = analytics.calculate(msgs)
        greeting = next(s for s in result.top_intents if s.intent == "greeting")
        assert greeting.avg_confidence == pytest.approx(0.7, abs=0.01)

    def test_low_confidence_detectado(self, analytics, mensajes_mixtos):
        result = analytics.calculate(mensajes_mixtos)
        low_names = [s.intent for s in result.low_confidence]
        assert "inquiry" in low_names

    def test_high_confidence_no_en_low(self, analytics, mensajes_mixtos):
        result = analytics.calculate(mensajes_mixtos)
        low_names = [s.intent for s in result.low_confidence]
        assert "greeting" not in low_names

    def test_avg_confidence_global(self, analytics):
        msgs = [
            make_msg("greeting", 1.0),
            make_msg("farewell", 0.0),
        ]
        result = analytics.calculate(msgs)
        assert result.avg_confidence_global == pytest.approx(0.5, abs=0.01)

    def test_umbral_personalizado(self, analytics):
        msgs = [make_msg("inquiry", 0.55)]
        result = analytics.low_confidence_intents(msgs, threshold=0.6)
        assert len(result) == 1
        result2 = analytics.low_confidence_intents(msgs, threshold=0.5)
        assert len(result2) == 0


# ── Tests: métodos individuales ───────────────────────────────

class TestMetodosIndividuales:

    def test_top_intents_limita_n(self, analytics, mensajes_mixtos):
        result = analytics.top_intents(mensajes_mixtos, n=2)
        assert len(result) == 2

    def test_distribution_retorna_dict(self, analytics, mensajes_mixtos):
        result = analytics.distribution(mensajes_mixtos)
        assert isinstance(result, dict)
        assert "greeting" in result

    def test_coverage_rate_directo(self, analytics, mensajes_mixtos):
        rate = analytics.coverage_rate(mensajes_mixtos)
        assert rate == pytest.approx(85.71, abs=0.1)


# ── Tests: extracción de intent ───────────────────────────────

class TestExtraccionIntent:

    def test_desde_metadata_dict(self, analytics):
        msg = MagicMock()
        msg.metadata   = {"intent": "greeting", "confidence": 0.9}
        msg.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        msg.strategy_used = None
        msg.intent     = None
        msg.confidence = None
        intent, conf = analytics._extract_intent(msg)
        assert intent == "greeting"
        assert conf   == 0.9

    def test_desde_atributo_directo(self, analytics):
        msg = MagicMock()
        msg.metadata      = {}
        msg.intent        = "purchase"
        msg.confidence    = 0.75
        msg.strategy_used = None
        intent, conf = analytics._extract_intent(msg)
        assert intent == "purchase"

    def test_desde_strategy_used_fallback(self, analytics):
        msg = MagicMock()
        msg.metadata      = {}
        msg.intent        = None
        msg.confidence    = None
        msg.strategy_used = "consultivo"
        intent, conf = analytics._extract_intent(msg)
        assert intent == "consultivo"

    def test_sin_intent_retorna_none(self, analytics):
        msg = make_msg_sin_intent()
        intent, conf = analytics._extract_intent(msg)
        assert intent is None

    def test_normaliza_a_minusculas(self, analytics):
        msg = MagicMock()
        msg.metadata      = {"intent": "GREETING", "confidence": 0.9}
        msg.strategy_used = None
        intent, _ = analytics._extract_intent(msg)
        assert intent == "greeting"


# ── Tests: agrupación por día ─────────────────────────────────

class TestAgrupacionDia:

    def test_by_day_retorna_lista(self, analytics):
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        msgs = [
            make_msg("greeting", created_at=base),
            make_msg("purchase", created_at=base + timedelta(days=1)),
        ]
        result = analytics.by_day(msgs)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_by_day_contiene_top_intent(self, analytics):
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        msgs = [make_msg("greeting", created_at=base)]
        result = analytics.by_day(msgs)
        assert result[0]["top_intent"] == "greeting"

    def test_by_day_ordenado(self, analytics):
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        msgs = [
            make_msg(created_at=base + timedelta(days=2)),
            make_msg(created_at=base),
            make_msg(created_at=base + timedelta(days=1)),
        ]
        result  = analytics.by_day(msgs)
        periods = [r["period"] for r in result]
        assert periods == sorted(periods)