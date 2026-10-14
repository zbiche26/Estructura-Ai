# -*- coding: utf-8 -*-
"""
performance_analytics.py - Métricas de Rendimiento
====================================================
Calcula métricas de performance del agente Alex:

    - Tiempo de respuesta promedio
    - Uptime del agente
    - Errores por día
    - Endpoints más lentos
    - % mensajes procesados exitosamente

Uso:
    analytics = PerformanceAnalytics()
    metrics = analytics.calculate(events)
    print(metrics.avg_response_ms)
    print(metrics.success_rate)
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ── Value Objects ────────────────────────────────────────────


@dataclass
class EndpointStat:
    """Estadísticas de un endpoint específico."""

    endpoint: str
    calls: int = 0
    avg_ms: float = 0.0
    max_ms: float = 0.0
    min_ms: float = 0.0
    error_count: int = 0
    error_rate: float = 0.0

    def __repr__(self) -> str:
        return (
            f"EndpointStat(endpoint='{self.endpoint}', "
            f"calls={self.calls}, avg_ms={self.avg_ms:.0f})"
        )


@dataclass
class PerformanceMetrics:
    """
    Métricas completas de rendimiento.

    Attributes:
        total_requests:     Total de requests procesados
        successful:         Requests exitosos
        failed:             Requests con error
        success_rate:       % exitosos (0-100)
        error_rate:         % fallidos (0-100)
        avg_response_ms:    Tiempo de respuesta promedio (ms)
        p95_response_ms:    Percentil 95 de respuesta (ms)
        max_response_ms:    Tiempo máximo de respuesta (ms)
        min_response_ms:    Tiempo mínimo de respuesta (ms)
        total_errors:       Total de errores registrados
        errors_by_type:     Distribución de errores por tipo
        slowest_endpoints:  Endpoints más lentos
        uptime_pct:         % de uptime estimado
        period_label:       Etiqueta del período
    """

    total_requests: int = 0
    successful: int = 0
    failed: int = 0
    success_rate: float = 0.0
    error_rate: float = 0.0
    avg_response_ms: float = 0.0
    p95_response_ms: float = 0.0
    max_response_ms: float = 0.0
    min_response_ms: float = 0.0
    total_errors: int = 0
    errors_by_type: Dict[str, int] = field(default_factory=dict)
    slowest_endpoints: List[EndpointStat] = field(default_factory=list)
    uptime_pct: float = 100.0
    period_label: str = ""

    def summary(self) -> str:
        return (
            f"Performance: {self.total_requests} requests | "
            f"success={self.success_rate:.1f}% | "
            f"avg={self.avg_response_ms:.0f}ms | "
            f"uptime={self.uptime_pct:.1f}%"
        )

    def __repr__(self) -> str:
        return (
            f"PerformanceMetrics("
            f"requests={self.total_requests}, "
            f"success={self.success_rate:.1f}%, "
            f"avg_ms={self.avg_response_ms:.0f})"
        )


# ── Analizador principal ─────────────────────────────────────


class PerformanceAnalytics:
    """
    Calcula métricas de rendimiento del agente.

    Los eventos se leen desde objetos con estructura:
        event.type          → "request" | "error" | "health_check"
        event.endpoint      → "/webhook/whatsapp/{tenant_id}"
        event.response_ms   → tiempo de respuesta en ms
        event.status_code   → 200, 400, 500, etc.
        event.error_type    → "timeout", "validation", "llm_error", etc.
        event.success       → True/False
        event.created_at    → datetime

    Uso:
        analytics = PerformanceAnalytics(slow_threshold_ms=2000)
        metrics   = analytics.calculate(events)
    """

    def __init__(
        self,
        slow_threshold_ms: float = 3000.0,
        top_n_endpoints: int = 5,
    ) -> None:
        """
        Args:
            slow_threshold_ms: Umbral para considerar un endpoint lento (ms).
            top_n_endpoints:   Número de endpoints en el ranking de lentos.
        """
        self._slow_threshold = slow_threshold_ms
        self._top_n = top_n_endpoints

    # ── API pública ──────────────────────────────────────────

    def calculate(
        self,
        events: List[Any],
        period_label: str = "",
    ) -> PerformanceMetrics:
        """
        Calcula métricas completas de rendimiento.

        Args:
            events:       Lista de eventos de request/error.
            period_label: Etiqueta del período analizado.

        Returns:
            PerformanceMetrics con todas las métricas.
        """
        metrics = PerformanceMetrics(period_label=period_label)

        if not events:
            return metrics

        response_times: List[float] = []
        error_types: Counter = Counter()
        endpoint_data: Dict[str, Dict] = defaultdict(
            lambda: {"calls": 0, "times": [], "errors": 0}
        )
        successful = 0
        failed = 0
        total_errors = 0

        for event in events:
            event_type = self._get_str(event, "type", "request")
            endpoint = self._get_str(event, "endpoint", "unknown")
            response_ms = self._get_float(event, "response_ms")
            status_code = self._get_int(event, "status_code", 200)
            success = self._get_bool(event, "success", status_code < 400)
            error_type = self._get_str(event, "error_type", "")

            # Contadores de éxito/fallo
            if success:
                successful += 1
            else:
                failed += 1

            # Tiempos de respuesta
            if response_ms is not None and response_ms >= 0:
                response_times.append(response_ms)

            # Por endpoint
            ep = endpoint_data[endpoint]
            ep["calls"] += 1
            if response_ms is not None:
                ep["times"].append(response_ms)
            if not success:
                ep["errors"] += 1

            # Errores
            if event_type == "error" or not success:
                total_errors += 1
                if error_type:
                    error_types[error_type] += 1

        # ── Llenar métricas ──────────────────────────────────
        metrics.total_requests = len(events)
        metrics.successful = successful
        metrics.failed = failed
        metrics.total_errors = total_errors
        metrics.errors_by_type = dict(error_types)

        if metrics.total_requests > 0:
            metrics.success_rate = round((successful / metrics.total_requests) * 100, 2)
            metrics.error_rate = round((failed / metrics.total_requests) * 100, 2)

        # Tiempos de respuesta
        if response_times:
            sorted_times = sorted(response_times)
            metrics.avg_response_ms = round(
                sum(response_times) / len(response_times), 2
            )
            metrics.max_response_ms = round(max(response_times), 2)
            metrics.min_response_ms = round(min(response_times), 2)
            # Percentil 95
            p95_idx = max(0, int(len(sorted_times) * 0.95) - 1)
            metrics.p95_response_ms = round(sorted_times[p95_idx], 2)

        # Uptime estimado basado en tasa de éxito
        metrics.uptime_pct = round(max(metrics.success_rate, 0.0), 2)

        # Endpoints más lentos
        endpoint_stats = []
        for ep_name, data in endpoint_data.items():
            times = data["times"]
            avg = round(sum(times) / len(times), 2) if times else 0.0
            stat = EndpointStat(
                endpoint=ep_name,
                calls=data["calls"],
                avg_ms=avg,
                max_ms=round(max(times), 2) if times else 0.0,
                min_ms=round(min(times), 2) if times else 0.0,
                error_count=data["errors"],
                error_rate=(
                    round((data["errors"] / data["calls"]) * 100, 2)
                    if data["calls"] > 0
                    else 0.0
                ),
            )
            endpoint_stats.append(stat)

        metrics.slowest_endpoints = sorted(
            endpoint_stats,
            key=lambda s: s.avg_ms,
            reverse=True,
        )[: self._top_n]

        return metrics

    def success_rate(self, events: List[Any]) -> float:
        """% de requests exitosos."""
        return self.calculate(events).success_rate

    def avg_response_ms(self, events: List[Any]) -> float:
        """Tiempo de respuesta promedio en ms."""
        return self.calculate(events).avg_response_ms

    def error_count(self, events: List[Any]) -> int:
        """Total de errores."""
        return self.calculate(events).total_errors

    def slowest_endpoints(
        self,
        events: List[Any],
        n: int = 5,
    ) -> List[EndpointStat]:
        """Top N endpoints más lentos."""
        return self.calculate(events).slowest_endpoints[:n]

    def errors_by_type(self, events: List[Any]) -> Dict[str, int]:
        """Distribución de errores por tipo."""
        return self.calculate(events).errors_by_type

    def by_day(self, events: List[Any]) -> List[Dict[str, Any]]:
        """Agrupa métricas por día."""
        groups: Dict[str, List[Any]] = defaultdict(list)
        for event in events:
            created_at = self._get_datetime(event, "created_at")
            if created_at:
                key = created_at.strftime("%Y-%m-%d")
                groups[key].append(event)

        result = []
        for day in sorted(groups.keys()):
            m = self.calculate(groups[day], period_label=day)
            result.append(
                {
                    "date": day,
                    "requests": m.total_requests,
                    "success_rate": m.success_rate,
                    "avg_ms": m.avg_response_ms,
                    "errors": m.total_errors,
                }
            )
        return result

    # ── Helpers ──────────────────────────────────────────────

    def _get_str(self, obj: Any, key: str, default: str = "") -> str:
        val = getattr(obj, key, None)
        if val is None and isinstance(getattr(obj, "__dict__", None), dict):
            val = obj.__dict__.get(key)
        return str(val).strip() if val is not None else default

    def _get_float(self, obj: Any, key: str) -> Optional[float]:
        val = getattr(obj, key, None)
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    def _get_int(self, obj: Any, key: str, default: int = 0) -> int:
        val = getattr(obj, key, None)
        try:
            return int(val) if val is not None else default
        except (ValueError, TypeError):
            return default

    def _get_bool(self, obj: Any, key: str, default: bool = True) -> bool:
        val = getattr(obj, key, None)
        if val is None:
            return default
        if isinstance(val, bool):
            return val
        return str(val).lower() in ("true", "1", "yes", "ok")

    def _get_datetime(self, obj: Any, key: str) -> Optional[datetime]:
        return getattr(obj, key, None)
