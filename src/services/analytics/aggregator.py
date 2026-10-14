# -*- coding: utf-8 -*-
"""
aggregator.py - Agregador de Métricas
======================================
Agrupa y combina métricas de los 4 módulos de analytics
en períodos: diario → semanal → mensual.

Uso:
    aggregator = MetricsAggregator()
    daily   = aggregator.aggregate_daily(conversations, messages, sales, events)
    weekly  = aggregator.aggregate_weekly(daily_list)
    monthly = aggregator.aggregate_monthly(weekly_list)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.services.analytics.conversation_analytics import ConversationAnalytics
from src.services.analytics.intent_analytics import IntentAnalytics
from src.services.analytics.performance_analytics import PerformanceAnalytics
from src.services.analytics.product_analytics import ProductAnalytics


# ── Value Object ─────────────────────────────────────────────


@dataclass
class AggregatedMetrics:
    """
    Métricas agregadas de un período completo.

    Attributes:
        period:              Etiqueta del período (ej: "2024-01-15")
        period_type:         "day" | "week" | "month"
        tenant_id:           Tenant al que pertenecen las métricas

        # Conversaciones
        total_conversations: Total de conversaciones
        completed_conv:      Conversaciones completadas
        abandoned_conv:      Conversaciones abandonadas
        avg_messages:        Promedio de mensajes por conversación
        avg_duration_min:    Duración promedio en minutos
        completion_rate:     % completadas

        # Intents
        top_intent:          Intent más frecuente
        unique_intents:      Intents únicos detectados
        intent_coverage:     % mensajes con intent detectado
        avg_confidence:      Confianza promedio

        # Productos
        total_views:         Total de vistas de productos
        total_sales:         Total de ventas
        total_revenue:       Revenue total
        conversion_rate:     % consultas → ventas
        top_product:         Producto más visto

        # Performance
        total_requests:      Total de requests
        success_rate:        % exitosos
        avg_response_ms:     Tiempo de respuesta promedio
        total_errors:        Total de errores
    """

    period: str = ""
    period_type: str = "day"
    tenant_id: str = ""
    generated_at: str = ""

    # Conversaciones
    total_conversations: int = 0
    completed_conv: int = 0
    abandoned_conv: int = 0
    avg_messages: float = 0.0
    avg_duration_min: float = 0.0
    completion_rate: float = 0.0

    # Intents
    top_intent: str = ""
    unique_intents: int = 0
    intent_coverage: float = 0.0
    avg_confidence: float = 0.0

    # Productos
    total_views: int = 0
    total_sales: int = 0
    total_revenue: float = 0.0
    conversion_rate: float = 0.0
    top_product: str = ""

    # Performance
    total_requests: int = 0
    success_rate: float = 0.0
    avg_response_ms: float = 0.0
    total_errors: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario para guardar en BD o generar reporte."""
        return {
            "period": self.period,
            "period_type": self.period_type,
            "tenant_id": self.tenant_id,
            "generated_at": self.generated_at,
            "conversations": {
                "total": self.total_conversations,
                "completed": self.completed_conv,
                "abandoned": self.abandoned_conv,
                "avg_messages": self.avg_messages,
                "avg_duration_min": self.avg_duration_min,
                "completion_rate": self.completion_rate,
            },
            "intents": {
                "top_intent": self.top_intent,
                "unique": self.unique_intents,
                "coverage": self.intent_coverage,
                "avg_confidence": self.avg_confidence,
            },
            "products": {
                "total_views": self.total_views,
                "total_sales": self.total_sales,
                "total_revenue": self.total_revenue,
                "conversion_rate": self.conversion_rate,
                "top_product": self.top_product,
            },
            "performance": {
                "total_requests": self.total_requests,
                "success_rate": self.success_rate,
                "avg_response_ms": self.avg_response_ms,
                "total_errors": self.total_errors,
            },
        }

    def summary(self) -> str:
        return (
            f"[{self.period_type.upper()}] {self.period} | "
            f"convs={self.total_conversations} | "
            f"revenue=${self.total_revenue:,.0f} | "
            f"success={self.success_rate:.1f}%"
        )

    def __repr__(self) -> str:
        return (
            f"AggregatedMetrics("
            f"period='{self.period}', "
            f"type='{self.period_type}', "
            f"convs={self.total_conversations})"
        )


# ── Agregador principal ──────────────────────────────────────


class MetricsAggregator:
    """
    Agrega métricas de todos los módulos de analytics.

    Flujo:
        1. aggregate_daily()   → métricas de un día específico
        2. aggregate_weekly()  → combina 7 días en una semana
        3. aggregate_monthly() → combina semanas en un mes

    Uso:
        aggregator = MetricsAggregator()

        # Métricas del día con datos reales
        daily = aggregator.aggregate_daily(
            conversations = convs_hoy,
            messages      = msgs_hoy,
            sales         = ventas_hoy,
            events        = events_hoy,
            period        = "2024-01-15",
            tenant_id     = "cliente_a",
        )

        # Combinar días en semana
        weekly = aggregator.aggregate_weekly(daily_list)
    """

    def __init__(self) -> None:
        self._conv_analytics = ConversationAnalytics()
        self._intent_analytics = IntentAnalytics()
        self._product_analytics = ProductAnalytics()
        self._perf_analytics = PerformanceAnalytics()

    # ── API pública ──────────────────────────────────────────

    def aggregate_daily(
        self,
        conversations: List[Any],
        messages: List[Any],
        sales: List[Any],
        events: List[Any],
        period: str = "",
        tenant_id: str = "",
    ) -> AggregatedMetrics:
        """
        Calcula métricas agregadas de un día.

        Args:
            conversations: Lista de conversaciones del día.
            messages:      Lista de mensajes del día.
            sales:         Lista de ventas del día.
            events:        Lista de eventos de performance del día.
            period:        Etiqueta del período (ej: "2024-01-15").
            tenant_id:     ID del tenant.

        Returns:
            AggregatedMetrics con todas las métricas del día.
        """
        if not period:
            period = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        metrics = AggregatedMetrics(
            period=period,
            period_type="day",
            tenant_id=tenant_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        # ── Conversaciones ────────────────────────────────────
        conv_m = self._conv_analytics.calculate(conversations, period)
        metrics.total_conversations = conv_m.total
        metrics.completed_conv = conv_m.completed
        metrics.abandoned_conv = conv_m.abandoned
        metrics.avg_messages = conv_m.avg_messages
        metrics.avg_duration_min = conv_m.avg_duration_min
        metrics.completion_rate = conv_m.completion_rate

        # ── Intents ───────────────────────────────────────────
        intent_m = self._intent_analytics.calculate(messages, period)
        metrics.top_intent = (
            intent_m.top_intents[0].intent if intent_m.top_intents else ""
        )
        metrics.unique_intents = intent_m.unique_intents
        metrics.intent_coverage = intent_m.coverage_rate
        metrics.avg_confidence = intent_m.avg_confidence_global

        # ── Productos ─────────────────────────────────────────
        product_m = self._product_analytics.calculate(messages, sales)
        metrics.total_views = product_m.total_views
        metrics.total_sales = product_m.total_sales
        metrics.total_revenue = product_m.total_revenue
        metrics.conversion_rate = product_m.conversion_rate
        metrics.top_product = (
            product_m.top_viewed[0].product_name
            if product_m.top_viewed and product_m.top_viewed[0].views > 0
            else ""
        )

        # ── Performance ───────────────────────────────────────
        perf_m = self._perf_analytics.calculate(events, period)
        metrics.total_requests = perf_m.total_requests
        metrics.success_rate = perf_m.success_rate
        metrics.avg_response_ms = perf_m.avg_response_ms
        metrics.total_errors = perf_m.total_errors

        return metrics

    def aggregate_weekly(
        self,
        daily_metrics: List[AggregatedMetrics],
        period: str = "",
        tenant_id: str = "",
    ) -> AggregatedMetrics:
        """
        Combina métricas diarias en una semana.

        Args:
            daily_metrics: Lista de AggregatedMetrics diarios.
            period:        Etiqueta de la semana (ej: "2024-W03").
            tenant_id:     ID del tenant.

        Returns:
            AggregatedMetrics semanal.
        """
        return self._combine(daily_metrics, "week", period, tenant_id)

    def aggregate_monthly(
        self,
        weekly_or_daily: List[AggregatedMetrics],
        period: str = "",
        tenant_id: str = "",
    ) -> AggregatedMetrics:
        """
        Combina métricas semanales (o diarias) en un mes.

        Args:
            weekly_or_daily: Lista de AggregatedMetrics.
            period:          Etiqueta del mes (ej: "2024-01").
            tenant_id:       ID del tenant.

        Returns:
            AggregatedMetrics mensual.
        """
        return self._combine(weekly_or_daily, "month", period, tenant_id)

    def aggregate_range(
        self,
        conversations: List[Any],
        messages: List[Any],
        sales: List[Any],
        events: List[Any],
        period: str = "",
        period_type: str = "custom",
        tenant_id: str = "",
    ) -> AggregatedMetrics:
        """
        Calcula métricas para un rango de fechas arbitrario.
        Útil para reportes ad-hoc sin agrupar por día.
        """
        daily = self.aggregate_daily(
            conversations, messages, sales, events, period=period, tenant_id=tenant_id
        )
        daily.period_type = period_type
        return daily

    # ── Combinación de períodos ──────────────────────────────

    def _combine(
        self,
        metrics_list: List[AggregatedMetrics],
        period_type: str,
        period: str,
        tenant_id: str,
    ) -> AggregatedMetrics:
        """
        Combina una lista de AggregatedMetrics en uno solo.
        Suma acumulables y promedia los porcentajes/tasas.
        """
        if not metrics_list:
            return AggregatedMetrics(
                period=period,
                period_type=period_type,
                tenant_id=tenant_id,
                generated_at=datetime.now(timezone.utc).isoformat(),
            )

        combined = AggregatedMetrics(
            period=period or self._infer_period(metrics_list, period_type),
            period_type=period_type,
            tenant_id=tenant_id or metrics_list[0].tenant_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        n = len(metrics_list)

        # ── Acumular sumas ────────────────────────────────────
        combined.total_conversations = sum(m.total_conversations for m in metrics_list)
        combined.completed_conv = sum(m.completed_conv for m in metrics_list)
        combined.abandoned_conv = sum(m.abandoned_conv for m in metrics_list)
        combined.total_views = sum(m.total_views for m in metrics_list)
        combined.total_sales = sum(m.total_sales for m in metrics_list)
        combined.total_revenue = round(sum(m.total_revenue for m in metrics_list), 2)
        combined.total_requests = sum(m.total_requests for m in metrics_list)
        combined.total_errors = sum(m.total_errors for m in metrics_list)
        combined.unique_intents = max(
            (m.unique_intents for m in metrics_list), default=0
        )

        # ── Promediar tasas y tiempos ─────────────────────────
        combined.avg_messages = round(sum(m.avg_messages for m in metrics_list) / n, 2)
        combined.avg_duration_min = round(
            sum(m.avg_duration_min for m in metrics_list) / n, 2
        )
        combined.completion_rate = round(
            sum(m.completion_rate for m in metrics_list) / n, 2
        )
        combined.intent_coverage = round(
            sum(m.intent_coverage for m in metrics_list) / n, 2
        )
        combined.avg_confidence = round(
            sum(m.avg_confidence for m in metrics_list) / n, 4
        )
        combined.conversion_rate = round(
            sum(m.conversion_rate for m in metrics_list) / n, 2
        )
        combined.success_rate = round(sum(m.success_rate for m in metrics_list) / n, 2)
        combined.avg_response_ms = round(
            sum(m.avg_response_ms for m in metrics_list) / n, 2
        )

        # ── Top intent y top producto (el más frecuente) ──────
        intent_counter: dict = {}
        product_counter: dict = {}

        for m in metrics_list:
            if m.top_intent:
                intent_counter[m.top_intent] = intent_counter.get(m.top_intent, 0) + 1
            if m.top_product:
                product_counter[m.top_product] = (
                    product_counter.get(m.top_product, 0) + 1
                )

        if intent_counter:
            combined.top_intent = max(intent_counter, key=intent_counter.get)
        if product_counter:
            combined.top_product = max(product_counter, key=product_counter.get)

        return combined

    def _infer_period(
        self,
        metrics_list: List[AggregatedMetrics],
        period_type: str,
    ) -> str:
        """Infiere la etiqueta del período desde la primera métrica."""
        if not metrics_list:
            return ""
        first = metrics_list[0].period
        if period_type == "week" and first:
            try:
                dt = datetime.strptime(first, "%Y-%m-%d")
                return dt.strftime("%Y-W%W")
            except ValueError:
                pass
        if period_type == "month" and first:
            return first[:7]  # "2024-01-15" → "2024-01"
        return first
