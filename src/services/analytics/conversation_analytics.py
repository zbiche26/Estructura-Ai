# -*- coding: utf-8 -*-
"""
conversation_analytics.py - Métricas de Conversaciones
=======================================================
Calcula métricas de engagement y comportamiento de conversaciones
del agente Alex por tenant.

Métricas calculadas:
    - Total conversaciones por período
    - Mensajes promedio por conversación
    - Duración promedio en minutos
    - Tasa de abandono
    - Conversaciones completadas vs incompletas
    - Distribución por plataforma
    - Horas pico de actividad

Uso:
    analytics = ConversationAnalytics()
    metrics = analytics.calculate(conversations)
    print(metrics.completion_rate)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from collections import Counter


# ── Value Objects ────────────────────────────────────────────

@dataclass
class ConversationMetrics:
    """
    Métricas completas de un conjunto de conversaciones.

    Attributes:
        total:               Total de conversaciones analizadas
        completed:           Conversaciones cerradas/completadas
        abandoned:           Conversaciones abandonadas (sin cierre)
        active:              Conversaciones actualmente activas
        avg_messages:        Promedio de mensajes por conversación
        avg_duration_min:    Duración promedio en minutos
        completion_rate:     % conversaciones completadas (0-100)
        abandonment_rate:    % conversaciones abandonadas (0-100)
        total_messages:      Total de mensajes en el período
        platform_breakdown:  Distribución por plataforma
        hourly_distribution: Mensajes por hora del día (0-23)
        period_label:        Etiqueta del período analizado
    """
    total:               int             = 0
    completed:           int             = 0
    abandoned:           int             = 0
    active:              int             = 0
    avg_messages:        float           = 0.0
    avg_duration_min:    float           = 0.0
    completion_rate:     float           = 0.0
    abandonment_rate:    float           = 0.0
    total_messages:      int             = 0
    platform_breakdown:  Dict[str, int]  = field(default_factory=dict)
    hourly_distribution: Dict[int, int]  = field(default_factory=dict)
    period_label:        str             = ""

    def summary(self) -> str:
        return (
            f"Conversaciones: {self.total} total | "
            f"{self.completed} completadas | "
            f"{self.abandoned} abandonadas | "
            f"completion_rate={self.completion_rate:.1f}%"
        )

    def __repr__(self) -> str:
        return (
            f"ConversationMetrics("
            f"total={self.total}, "
            f"completion_rate={self.completion_rate:.1f}%)"
        )


@dataclass
class PeriodMetrics:
    """Métricas agrupadas por período (día, semana, mes)."""
    period:      str
    total:       int   = 0
    completed:   int   = 0
    abandoned:   int   = 0
    messages:    int   = 0
    avg_duration: float = 0.0

    def __repr__(self) -> str:
        return f"PeriodMetrics(period='{self.period}', total={self.total})"


# ── Analizador principal ─────────────────────────────────────

class ConversationAnalytics:
    """
    Calcula métricas de engagement de conversaciones.

    Trabaja sobre listas de objetos Conversation del modelo
    de dominio (src.models.models.Conversation).

    Uso:
        analytics = ConversationAnalytics()

        # Calcular métricas generales
        metrics = analytics.calculate(conversations)

        # Métricas por día
        daily = analytics.by_day(conversations)

        # Tasa de abandono
        rate = analytics.abandonment_rate(conversations)
    """

    # Estados que se consideran "completados"
    COMPLETED_STATUSES = {"closed", "archived", "completed"}
    # Estados que se consideran "activos"
    ACTIVE_STATUSES    = {"active"}

    def __init__(self, min_messages_completed: int = 2) -> None:
        """
        Args:
            min_messages_completed: Mínimo de mensajes para considerar
                                    una conversación como completada
                                    (no solo abierta y cerrada).
        """
        self._min_messages = min_messages_completed

    # ── API pública ──────────────────────────────────────────

    def calculate(
        self,
        conversations: List[Any],
        period_label:  str = "",
    ) -> ConversationMetrics:
        """
        Calcula métricas completas de un conjunto de conversaciones.

        Args:
            conversations: Lista de objetos Conversation.
            period_label:  Etiqueta descriptiva del período.

        Returns:
            ConversationMetrics con todas las métricas calculadas.
        """
        metrics = ConversationMetrics(period_label=period_label)

        if not conversations:
            return metrics

        metrics.total = len(conversations)

        # Contadores
        completed_count  = 0
        abandoned_count  = 0
        active_count     = 0
        total_messages   = 0
        total_duration   = 0.0
        duration_count   = 0
        platform_counter = Counter()
        hourly_counter   = Counter()

        for conv in conversations:
            status        = self._get_status(conv)
            msg_count     = self._get_message_count(conv)
            duration_min  = self._get_duration_minutes(conv)
            platform      = self._get_platform(conv)
            created_at    = self._get_created_at(conv)

            # Clasificar estado
            if status in self.COMPLETED_STATUSES:
                completed_count += 1
            elif status in self.ACTIVE_STATUSES:
                active_count += 1
            else:
                abandoned_count += 1

            # Acumular mensajes
            total_messages += msg_count

            # Acumular duración
            if duration_min is not None and duration_min >= 0:
                total_duration += duration_min
                duration_count += 1

            # Plataforma
            if platform:
                platform_counter[platform] += 1

            # Distribución horaria
            if created_at:
                hourly_counter[created_at.hour] += 1

        metrics.completed  = completed_count
        metrics.abandoned  = abandoned_count
        metrics.active     = active_count
        metrics.total_messages = total_messages

        # Promedios
        metrics.avg_messages = round(total_messages / metrics.total, 2)

        if duration_count > 0:
            metrics.avg_duration_min = round(total_duration / duration_count, 2)

        # Tasas
        non_active = metrics.total - active_count
        if non_active > 0:
            metrics.completion_rate  = round(
                (completed_count / non_active) * 100, 2
            )
            metrics.abandonment_rate = round(
                (abandoned_count / non_active) * 100, 2
            )

        metrics.platform_breakdown  = dict(platform_counter)
        metrics.hourly_distribution = dict(hourly_counter)

        return metrics

    def abandonment_rate(self, conversations: List[Any]) -> float:
        """
        Calcula solo la tasa de abandono.

        Returns:
            Porcentaje de abandono (0.0 - 100.0)
        """
        metrics = self.calculate(conversations)
        return metrics.abandonment_rate

    def completion_rate(self, conversations: List[Any]) -> float:
        """
        Calcula solo la tasa de completación.

        Returns:
            Porcentaje de completación (0.0 - 100.0)
        """
        metrics = self.calculate(conversations)
        return metrics.completion_rate

    def avg_messages_per_conversation(
        self,
        conversations: List[Any],
    ) -> float:
        """Promedio de mensajes por conversación."""
        metrics = self.calculate(conversations)
        return metrics.avg_messages

    def avg_duration_minutes(self, conversations: List[Any]) -> float:
        """Duración promedio en minutos."""
        metrics = self.calculate(conversations)
        return metrics.avg_duration_min

    def by_day(self, conversations: List[Any]) -> List[PeriodMetrics]:
        """
        Agrupa métricas por día.

        Returns:
            Lista de PeriodMetrics ordenada por fecha.
        """
        return self._group_by_period(conversations, "day")

    def by_week(self, conversations: List[Any]) -> List[PeriodMetrics]:
        """Agrupa métricas por semana (ISO week)."""
        return self._group_by_period(conversations, "week")

    def by_month(self, conversations: List[Any]) -> List[PeriodMetrics]:
        """Agrupa métricas por mes."""
        return self._group_by_period(conversations, "month")

    def peak_hours(
        self,
        conversations: List[Any],
        top_n: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Retorna las horas pico de actividad.

        Args:
            conversations: Lista de conversaciones.
            top_n:         Número de horas a retornar.

        Returns:
            Lista de dicts {hour, count} ordenados por count desc.
        """
        metrics = self.calculate(conversations)
        sorted_hours = sorted(
            metrics.hourly_distribution.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        return [
            {"hour": h, "count": c}
            for h, c in sorted_hours[:top_n]
        ]

    def platform_breakdown(
        self,
        conversations: List[Any],
    ) -> Dict[str, float]:
        """
        Distribución porcentual por plataforma.

        Returns:
            Dict {plataforma: porcentaje}
        """
        metrics = self.calculate(conversations)
        total = sum(metrics.platform_breakdown.values())
        if total == 0:
            return {}
        return {
            platform: round((count / total) * 100, 2)
            for platform, count in metrics.platform_breakdown.items()
        }

    # ── Agrupación por período ───────────────────────────────

    def _group_by_period(
        self,
        conversations: List[Any],
        period: str,
    ) -> List[PeriodMetrics]:
        """Agrupa conversaciones por período y calcula métricas."""
        groups: Dict[str, List[Any]] = {}

        for conv in conversations:
            created_at = self._get_created_at(conv)
            if not created_at:
                continue

            if period == "day":
                key = created_at.strftime("%Y-%m-%d")
            elif period == "week":
                key = created_at.strftime("%Y-W%W")
            elif period == "month":
                key = created_at.strftime("%Y-%m")
            else:
                key = created_at.strftime("%Y-%m-%d")

            groups.setdefault(key, []).append(conv)

        result = []
        for period_key in sorted(groups.keys()):
            group = groups[period_key]
            m     = self.calculate(group, period_label=period_key)
            result.append(PeriodMetrics(
                period       = period_key,
                total        = m.total,
                completed    = m.completed,
                abandoned    = m.abandoned,
                messages     = m.total_messages,
                avg_duration = m.avg_duration_min,
            ))

        return result

    # ── Helpers para acceder a propiedades del modelo ────────

    def _get_status(self, conv: Any) -> str:
        """Extrae el status como string."""
        status = getattr(conv, "status", None)
        if status is None:
            return "unknown"
        # Puede ser un Enum o un string
        return str(status.value if hasattr(status, "value") else status).lower()

    def _get_message_count(self, conv: Any) -> int:
        """Número de mensajes de la conversación."""
        # El modelo Conversation de models.py no tiene messages directo
        # pero puede tener message_count o messages list
        if hasattr(conv, "message_count"):
            return int(conv.message_count or 0)
        if hasattr(conv, "messages") and conv.messages is not None:
            return len(conv.messages)
        return 0

    def _get_duration_minutes(self, conv: Any) -> Optional[float]:
        """Duración en minutos de la conversación."""
        # Usar property duration_minutes si existe
        if hasattr(conv, "duration_minutes") and conv.duration_minutes is not None:
            return float(conv.duration_minutes)

        # Calcular manualmente con started_at / closed_at
        started  = getattr(conv, "started_at",  None) or getattr(conv, "created_at",  None)
        closed   = getattr(conv, "closed_at",   None) or getattr(conv, "updated_at",  None)

        if started and closed and closed > started:
            delta = closed - started
            return round(delta.total_seconds() / 60, 2)

        return None

    def _get_platform(self, conv: Any) -> str:
        """Plataforma de la conversación."""
        # Puede estar en metadata.platform o directo
        metadata = getattr(conv, "metadata", None)
        if metadata:
            if isinstance(metadata, dict):
                return metadata.get("platform", "unknown")
            if hasattr(metadata, "platform"):
                return metadata.platform or "unknown"
        return getattr(conv, "platform", "unknown") or "unknown"

    def _get_created_at(self, conv: Any) -> Optional[datetime]:
        """Fecha de creación de la conversación."""
        return (
            getattr(conv, "started_at",  None)
            or getattr(conv, "created_at", None)
        )